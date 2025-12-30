import grpc
import argparse
from concurrent import futures
from collections import defaultdict
import logging

import pbft_pb2
import pbft_pb2_grpc
from block import Block


NUM_NODES = 5
F = 1


class PBFTNode(pbft_pb2_grpc.PBFTNodeServicer):
    def __init__(self, node_id, peers, f, is_byzantine=False):
        self.id = node_id
        self.peers = peers                      
        self.f = f
        self.is_byzantine = is_byzantine

        # View/sequence for current leader
        self.view = 0
        self.seq = 0

        # Blockchain and safety structures
        self.blockchain = []
        self.blacklist = set()

        # Track pre-prepare seen: key -> (view, seq), value -> Block
        self.pre_prepares = {}

        # Prepared flags: set of (view, seq, block_hash)
        self.prepared = set()

        # Prepare/Commit maps keyed by (view, seq) then block_hash
        self.prepares = defaultdict(lambda: defaultdict(set))  # {(v,s): {hash: set(sender_ids)}}
        self.commits  = defaultdict(lambda: defaultdict(set))  # {(v,s): {hash: set(sender_ids)}}

        # Track highest committed seq (simple sequential guard)
        self.last_committed_seq = 0

        self.logger = self.setup_logger(self.id)
        self.logger.info(f"[INITIALIZE]: Node {self.id}. Byzantine={self.is_byzantine}. Peers={list(self.peers.keys())}")

    def log_tag(self, view=None, seq=None, block_hash=None, client=False):
        if client:
            return "[CLIENT]"
        if view is not None and seq is not None and block_hash is not None:
            return f"[View {view} | Seq {seq} | {block_hash[:6]}]"
        if seq is not None and block_hash is not None:
            return f"[Seq {seq} | {block_hash[:6]}]"
        return ""

    def setup_logger(self, node_id):
        logger = logging.getLogger(f"Node{node_id}")
        logger.setLevel(logging.INFO)
        fh = logging.FileHandler(f"node_{node_id}.log")
        fh.setLevel(logging.INFO)
        formatter = logging.Formatter('[%(asctime)s] - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        fh.setFormatter(formatter)
        if not logger.hasHandlers():
            logger.addHandler(fh)
        return logger

    def primary(self):
        return self.view % len(self.peers)

    def broadcast(self, func, msg):
        """
        Broadcast to all peers and process locally (including this node).
        Ensure that the primary node records its own Prepare/Commit.
        """
        for pid, addr in self.peers.items():
            try:
                if pid == self.id:
                    getattr(self, func)(msg, context=None)  # local processing
                else:
                    with grpc.insecure_channel(addr) as ch:
                        stub = pbft_pb2_grpc.PBFTNodeStub(ch)
                        getattr(stub, func)(msg)
            except Exception as e:
                self.logger.warning(f"Failed to send {func} to node {pid}: {e}")

    # ========== Client Request ==========
    def ClientRequest(self, request, context):
        tag = self.log_tag(client=True)
        self.logger.info(f"{tag}: ClientRequest block_height={request.block.height}, block_hash={request.block.hash[:6]}")

        if self.id != self.primary():
            self.logger.warning(f"{tag}: Not primary, rejecting client request")
            return pbft_pb2.ClientReply(success=False, message="Not primary")

        # Enforce chain continuity on primary
        expected_prev = "_XMAS_" if not self.blockchain else self.blockchain[-1].hash
        if request.block.prev_hash != expected_prev:
            self.logger.warning(f"{tag}: Rejecting request due to prev_hash mismatch")
            return pbft_pb2.ClientReply(success=False, message="Invalid prev_hash")

        # Assign sequence in current view
        self.seq += 1
        pre = pbft_pb2.PrePrepareMsg(
            view=self.view,
            seq=self.seq,
            block=request.block,
            sender_id=self.id
        )
        tag_seq = self.log_tag(view=self.view, seq=self.seq, block_hash=request.block.hash)
        self.logger.info(f"{tag_seq}: Broadcasting PrePrepare (including self)")
        self.broadcast("PrePrepare", pre)
        return pbft_pb2.ClientReply(success=True, message="PrePrepare sent")

    # ========== Pre-Prepare ==========
    def PrePrepare(self, msg, context):
        tag_seq = self.log_tag(view=msg.view, seq=msg.seq, block_hash=msg.block.hash)

        if msg.sender_id in self.blacklist:
            self.logger.warning(f"{tag_seq} - [blocked]: Node {msg.sender_id} in BlackList")
            return pbft_pb2.Ack(success=False)

        # Only accept pre-prepare from current primary
        if msg.sender_id != self.primary():
            self.logger.warning(f"{tag_seq} - [ignored]: PrePrepare from non-primary")
            return pbft_pb2.Ack(success=False)

        # Validate chain continuity
        prev = "_XMAS_" if not self.blockchain else self.blockchain[-1].hash
        if msg.block.prev_hash != prev:
            self.logger.error(f"{tag_seq}: Invalid block prev_hash from Node {msg.sender_id}")
            return pbft_pb2.Ack(success=False)

        key = (msg.view, msg.seq)
        # Record pre-prepare proposal
        self.pre_prepares[key] = msg.block

        # Byzantine behavior (only alters hash in prepare)
        block_hash = msg.block.hash
        if self.is_byzantine:
            block_hash = "_FAKE_"
            self.logger.warning(f"{tag_seq} - [byzantine]: Altering block hash on Prepare!")

        # All replicas (including primary) send Prepare
        prepare = pbft_pb2.PrepareMsg(
            view=msg.view,
            seq=msg.seq,
            block_hash=block_hash,
            sender_id=self.id
        )
        self.logger.info(f"{tag_seq}: Broadcasting Prepare (including self)")
        self.broadcast("Prepare", prepare)
        return pbft_pb2.Ack(success=True)

    # ========== Prepare ==========
    def Prepare(self, msg, context):
        tag_seq = self.log_tag(view=msg.view, seq=msg.seq, block_hash=msg.block_hash)

        if msg.sender_id in self.blacklist:
            self.logger.warning(f"{tag_seq} - [blocked]: Node {msg.sender_id} in BlackList")
            return pbft_pb2.Ack(success=False)

        key = (msg.view, msg.seq)

        # Must have seen a valid pre-prepare for this (view, seq)
        if key not in self.pre_prepares:
            self.logger.warning(f"{tag_seq} - [ignored]: No PrePrepare recorded yet")
            return pbft_pb2.Ack(success=False)

        # Prepare must match the digest in pre-prepare
        proposed_block = self.pre_prepares[key]
        if proposed_block.hash != msg.block_hash:
            self.logger.warning(f"{tag_seq} - [mismatch]: Prepare hash != PrePrepare hash")
            # Only record mismatches; blacklist will be created after a majority is determined.
            # Record the sender in the incorrect hash group.
            wrong_set = self.prepares[key][msg.block_hash]
            wrong_set.add(msg.sender_id)
            self._try_blacklist_after_majority(key)
            return pbft_pb2.Ack(success=False)

        # Add sender to prepare set (correct hash)
        sender_set = self.prepares[key][msg.block_hash]
        if msg.sender_id in sender_set:
            self.logger.warning(f"{tag_seq} - [ignored]: Duplicate Prepare from Node {msg.sender_id}")
            return pbft_pb2.Ack(success=False)

        sender_set.add(msg.sender_id)
        self.logger.info(f"{tag_seq} - [PREPARE]: Count={len(sender_set)}")

        # After adding, try to identify the majority and blacklist the incorrect hashes.
        self._try_blacklist_after_majority(key)

        # prepared: pre-prepare + 2f prepares
        if len(sender_set) >= 2 * self.f:
            self.prepared.add((msg.view, msg.seq, msg.block_hash))

            # Immediately add self-commit locally before broadcasting
            commit_set_local = self.commits[key][msg.block_hash]
            if self.id not in commit_set_local:
                commit_set_local.add(self.id)
                self.logger.info(f"{tag_seq} - [COMMIT][local]: Self-commit recorded. Count={len(commit_set_local)}")

            # Broadcast commit (including self handler)
            commit = pbft_pb2.CommitMsg(
                view=msg.view,
                seq=msg.seq,
                block_hash=msg.block_hash,
                sender_id=self.id
            )
            self.logger.info(f"{tag_seq} - [state]: PREPARED. Broadcasting Commit (including self)")
            self.broadcast("Commit", commit)

            # Check if local commit count already reaches threshold
            if len(commit_set_local) >= (2 * self.f + 1):
                if (not self.blockchain) or (self.blockchain[-1].hash == proposed_block.prev_hash):
                    self.blockchain.append(proposed_block)
                    self.last_committed_seq = msg.seq
                    self.logger.info(f"{tag_seq} - [state]: COMMITTED-LOCAL (prepared + 2f+1 local commits)")
                else:
                    self.logger.error(f"{tag_seq} - [error]: Prev_hash mismatch at commit; not appending")

        return pbft_pb2.Ack(success=True)

    def _try_blacklist_after_majority(self, key):
        """
        After a hash reaches prepare quorum (>= 2f),
        replicas sending conflicting prepares are considered Byzantine and blacklisted.
        """
        hash_map = self.prepares[key]
        # find majority hash
        majority_hash = None
        for h, senders in hash_map.items():
            if len(senders) >= 2 * self.f:
                majority_hash = h
                break
        if majority_hash is None:
            return
        # Blacklist senders on other hashes except majority_hash
        for h, senders in hash_map.items():
            if h == majority_hash:
                continue
            for s in list(senders):
                if s not in self.blacklist:
                    self.blacklist.add(s)
                    self.logger.warning(f"[View {key[0]} | Seq {key[1]} | {h[:6]}] - [byzantine detected]: Node {s} sent wrong Prepare hash; blacklisted")

    # ========== Commit ==========
    def Commit(self, msg, context):
        tag_seq = self.log_tag(view=msg.view, seq=msg.seq, block_hash=msg.block_hash)

        if msg.sender_id in self.blacklist:
            self.logger.warning(f"{tag_seq} - [blocked]: Node {msg.sender_id} in BlackList")
            return pbft_pb2.Ack(success=False)

        key = (msg.view, msg.seq)
        if key not in self.pre_prepares:
            self.logger.warning(f"{tag_seq} - [ignored]: No PrePrepare recorded for Commit")
            return pbft_pb2.Ack(success=False)

        proposed_block = self.pre_prepares[key]
        if proposed_block.hash != msg.block_hash:
            self.logger.warning(f"{tag_seq} - [mismatch]: Commit hash != PrePrepare hash → blacklist sender")
            # False comments are strong evidence; blacklist immediately.
            self.blacklist.add(msg.sender_id)
            return pbft_pb2.Ack(success=False)

        # Record commit
        commit_set = self.commits[key][msg.block_hash]
        if msg.sender_id in commit_set:
            self.logger.warning(f"{tag_seq} - [ignored]: Duplicate Commit from Node {msg.sender_id}")
            return pbft_pb2.Ack(success=False)

        commit_set.add(msg.sender_id)
        self.logger.info(f"{tag_seq} - [COMMIT]: Count={len(commit_set)}")

        # If we reach 2f+1 commits, ensure prepared locally (auto-mark if needed) and append
        if len(commit_set) >= (2 * self.f + 1):
            if (msg.view, msg.seq, msg.block_hash) not in self.prepared:
                # Auto-mark prepared (we have pre-prepare; commits imply enough agreement)
                self.prepared.add((msg.view, msg.seq, msg.block_hash))
                self.logger.info(f"{tag_seq} - [state]: Auto-mark PREPARED due to 2f+1 commits")

            if (not self.blockchain) or (self.blockchain[-1].hash == proposed_block.prev_hash):
                self.blockchain.append(proposed_block)
                self.last_committed_seq = msg.seq
                self.logger.info(f"{tag_seq} - [state]: COMMITTED-LOCAL (2f+1 commits)")
            else:
                self.logger.error(f"{tag_seq} - [error]: Prev_hash mismatch at commit; not appending")

        return pbft_pb2.Ack(success=True)

    # ========== Node Status ==========
    def NodeStatus(self, request, context):
        blockchain_proto = [pbft_pb2.Block(
            height=b.height,
            prev_hash=b.prev_hash,
            hash=b.hash
        ) for b in self.blockchain]

        prepares_proto = []
        for (view, seq), hash_map in self.prepares.items():
            block_counts = [pbft_pb2.BlockCount(block_hash=h, count=len(s)) for h, s in hash_map.items()]
            prepares_proto.append(pbft_pb2.PrepareMap(view=view, seq=seq, block_counts=block_counts))

        commits_proto = []
        for (view, seq), hash_map in self.commits.items():
            block_counts = [pbft_pb2.BlockCount(block_hash=h, count=len(s)) for h, s in hash_map.items()]
            commits_proto.append(pbft_pb2.CommitMap(view=view, seq=seq, block_counts=block_counts))

        return pbft_pb2.NodeStatusReply(
            blockchain=blockchain_proto,
            prepares=prepares_proto,
            blacklist=list(self.blacklist),
            commits=commits_proto
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=int, required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--byzantine", action="store_true")
    args = parser.parse_args()

    # With f=F, PBFT requires N >= 3f + 1; here N=NUM_NODES
    peers = {i: f"localhost:{50050+i}" for i in range(NUM_NODES)}

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    pbft_pb2_grpc.add_PBFTNodeServicer_to_server(
        PBFTNode(args.id, peers, f=F, is_byzantine=args.byzantine),
        server
    )
    server.add_insecure_port(f"[::]:{args.port}")
    server.start()
    print(f"Node {args.id} running on port {args.port}")
    server.wait_for_termination()



if __name__ == "__main__":
    main()