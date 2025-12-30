from concurrent import futures
import grpc
import raft_pb2
import raft_pb2_grpc
import random
import time
import threading
import sys
import os
import json
import argparse
from enum import Enum

# Default configuration
DEFAULT_NUM_NODES = 5
DEFAULT_BASE_PORT = 50050

class NodeState(Enum):
    FOLLOWER = 1
    CANDIDATE = 2
    LEADER = 3

class Raft(raft_pb2_grpc.RaftServicer):
    def __init__(self, node_id, peers, port):
        self.node_id = node_id
        self.peers = peers
        self.port = port

        # Time configurations
        self.ELECTION_TIMEOUT_MIN = 8.0
        self.ELECTION_TIMEOUT_MAX = 10.0
        self.TICK_RATE = random.uniform(0.1, 0.5)
        self.HEARTBEAT_INTERVAL = 2.0
        self.RPC_TIMEOUT = 1.0

        # Persistence file path
        self.persist_file = f"raft_state_{node_id}.json"
        # Load persistent state or initialize
        self.load_persistent_state()

        # Volatile state
        self.commit_index = -1
        self.last_applied = -1
        self.state = NodeState.FOLLOWER

        # Leader state
        self.next_index = {}
        self.match_index = {}
        self.last_heartbeat_sent = 0

        # Timing
        self.last_heartbeat = time.time()
        self.election_timeout = self.random_election_timeout()

        # Network partition simulation
        self.blocked_peers = set()

        # Locks
        self.lock = threading.Lock()

        print(f"[Node {self.node_id}] initialized on port {self.port}")

    def load_persistent_state(self):
        """Load persistent state from disk or initialize fresh"""
        if os.path.exists(self.persist_file):
            try:
                with open(self.persist_file, "r") as f:
                    data = json.load(f)

                self.current_term = data.get("current_term", 0)
                self.voted_for = data.get("voted_for", None)

                # Restore log
                self.log = []
                for entry_data in data.get("log", []):
                    entry = raft_pb2.LogEntry(
                        term=entry_data["term"],
                        index=entry_data["index"],
                        command=entry_data["command"]
                    )
                    self.log.append(entry)

                # Restore state machine
                self.storage = data.get("storage", {})
                
                print(f"[Node {self.node_id}] restored state: term={self.current_term}, log_size={len(self.log)}")
            except Exception as e:
                print(f"[Node {self.node_id}] failed to load state: {e}")
                self.initialize_fresh_state()
        else:
            self.initialize_fresh_state()

    def initialize_fresh_state(self):
        """Initialize fresh state"""
        self.current_term = 0
        self.voted_for = None
        self.log = []
        self.storage = {}
        print(f"[Node {self.node_id}] initialize fresh state")

    def save_persistent_state(self):
        """Save persistent state to disk"""
        try:
            data = {
                "current_term": self.current_term,
                "voted_for": self.voted_for,
                "log": [
                    {
                        "term": entry.term,
                        "index": entry.index,
                        "command": entry.command
                    }
                    for entry in self.log
                ],
                "storage": self.storage
            }

            with open(self.persist_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[Node {self.node_id}] failed to save persistent state: {e}")

    def random_election_timeout(self):
        """Generate election timeout between 150ms and 300ms"""
        return random.uniform(self.ELECTION_TIMEOUT_MIN, self.ELECTION_TIMEOUT_MAX)
    
    def reset_election_timer(self):
        """Reset the election timer"""
        self.last_heartbeat = time.time()
        self.election_timeout = self.random_election_timeout()
    
    def get_last_log_index(self):
        """Get the index of the last log entry"""
        return len(self.log) - 1 if self.log else -1
    
    def get_last_log_term(self):
        """Get the term of the last log entry"""
        return self.log[-1].term if self.log else 0
    
    def get_peer_stub(self, peer_id):
        """Get gRPC stub"""
        if peer_id == self.node_id or peer_id in self.blocked_peers:
            return None
        try:
            channel = grpc.insecure_channel(self.peers[peer_id])
            return raft_pb2_grpc.RaftStub(channel)
        except:
            return None
    
    def RequestVote(self, request, context):
        """Handle RequestVote RPC"""
        with self.lock:
            print(f"[Node {self.node_id}] received RequestVote from Node {request.candidate_id}")

            # Reject if term is older than current term
            if request.term < self.current_term:
                return raft_pb2.VoteResponse(
                    term=self.current_term,
                    vote_granted=False
                )

            # Update term if necessary
            if request.term > self.current_term:
                self.current_term = request.term
                self.voted_for = None
                self.state = NodeState.FOLLOWER
                self.save_persistent_state()

            # Grant vote if:
            # 1. Candidate's term >= current term
            vote_granted = False
            # 2. Haven't voted or already voted for this candidate
            if self.voted_for is None or self.voted_for == request.candidate_id:
                last_log_term = self.get_last_log_term()
                last_log_index = self.get_last_log_index()
                # 3. Candidate's log is at least as up-to-date as this node
                if request.last_log_term > last_log_term or (request.last_log_term == last_log_term and request.last_log_index >= last_log_index):
                    vote_granted = True
                    self.voted_for = request.candidate_id
                    self.save_persistent_state()
                    self.reset_election_timer()
                    print(f"[Node {self.node_id}] granted vote to Node {request.candidate_id}")

            return raft_pb2.VoteResponse(
                term=self.current_term,
                vote_granted=vote_granted
            )
                             
    def AppendEntries(self, request, context):
        """Handle AppendEntries RPC (Heartbeat and Log replication)"""
        with self.lock:            
            # Reject if term is old
            if request.term < self.current_term:
                return raft_pb2.AppendEntriesResponse(
                    term=self.current_term,
                    success=False
                )
            
            # Update term and reset election timer (received valid heartbeat)
            if request.term > self.current_term:
                self.current_term = request.term
                self.voted_for = None
                self.save_persistent_state()

            self.state = NodeState.FOLLOWER
            self.reset_election_timer()
            print(f"[Node {self.node_id}] received heartbeat from {request.leader_id}")

            # Check if log matches
            if request.prev_log_index >= len(self.log) or \
                  (request.prev_log_index >= 0 and self.log[request.prev_log_index].term != request.prev_log_term):
                    return raft_pb2.AppendEntriesResponse(
                        term=self.current_term,
                        success=False
                    )
            
            # Append new entries
            for i, entry in enumerate(request.entries):
                index = request.prev_log_index + 1 + i
                if index < len(self.log):
                    if self.log[index].term != entry.term:
                        self.log = self.log[:index]
                        self.log.append(entry)
                else:
                    self.log.append(entry)
            self.save_persistent_state()
                
            if request.entries:
                print(f"[Node {self.node_id}] appended {len(request.entries)} entries")

            # Update commit index
            if request.leader_commit > self.commit_index:
                self.commit_index = min(request.leader_commit, len(self.log) - 1)
                self.apply_committed_entries()

            return raft_pb2.AppendEntriesResponse(
                term=self.current_term,
                success=True
            )
        
    def apply_committed_entries(self):
        """Apply committed log entries to state machine"""
        while self.last_applied < self.commit_index:
            self.last_applied += 1
            entry = self.log[self.last_applied]

            # Parse command (format: "SET key value")
            parts = entry.command.split()
            if len(parts) >= 3 and parts[0] == "SET":
                key = parts[1]
                value = " ".join(parts[2:])
                self.storage[key] = value
                self.save_persistent_state()
                print(f"[Node {self.node_id}] applied: {entry.command}")

    def ClientRequest(self, request, context):
        """Handle client requests"""
        with self.lock:
            # Redirect to leader if known
            if self.state != NodeState.LEADER:
                return raft_pb2.ClientResponse(
                    success=False,
                    message="Not leader",
                    leader_id=self.voted_for if self.voted_for else -1
                )
            
            # Append to log
            entry = raft_pb2.LogEntry(
                term=self.current_term,
                index=len(self.log),
                command=request.command
            )
            self.log.append(entry)
            self.save_persistent_state()
            print(f"[Node {self.node_id}] received client request: {request.command}")

            return raft_pb2.ClientResponse(
                success=True,
                message="Request received",
                leader_id=self.node_id
            )

    def NetworkPartition(self, request, context):
        """Handle network partition simulation"""
        with self.lock:
            self.blocked_peers = set()

            for addr in request.blocked_addresses:
                for peer_id, peer_addr in self.peers.items():
                    if peer_addr == addr:
                        self.blocked_peers.add(peer_id)
            print(f"[Node {self.node_id}] Network partition: blocked {self.blocked_peers}")
            return raft_pb2.PartitionResponse(success=True)  

    def start_election(self):
        """Start leader election"""
        with self.lock:
            self.state = NodeState.CANDIDATE
            self.current_term += 1
            self.voted_for = self.node_id
            self.save_persistent_state()
            self.reset_election_timer()

            print(f"[Node {self.node_id}] starting election for term {self.current_term}")

            votes_received = 1
            term = self.current_term
            last_log_index = self.get_last_log_index()
            last_log_term = self.get_last_log_term()

        for peer_id in self.peers:
            if peer_id == self.node_id or peer_id in self.blocked_peers:
                continue

            try:
                stub = self.get_peer_stub(peer_id)
                if stub:
                    request = raft_pb2.VoteRequest(
                        term=term,
                        candidate_id=self.node_id,
                        last_log_index=last_log_index,
                        last_log_term=last_log_term
                    )
                    response = stub.RequestVote(request, timeout=self.RPC_TIMEOUT)

                    with self.lock:
                        # Update term if response has higher term
                        if response.term > self.current_term:
                            self.current_term = response.term
                            self.state = NodeState.FOLLOWER
                            self.voted_for = None
                            return
                        
                        if response.vote_granted and response.term == term:
                            votes_received += 1
            except Exception as e:
                pass
        
        with self.lock:
            if self.state == NodeState.CANDIDATE and votes_received > len(self.peers) // 2:
                self.become_leader()

    def become_leader(self):
        """Transition to leader state"""
        print(f"[Node {self.node_id}] becomes leader for term {self.current_term}")
        self.state = NodeState.LEADER

        # Initialize leader state
        for peer_id in self.peers:
            if peer_id != self.node_id:
                self.next_index[peer_id] = len(self.log)
                self.match_index[peer_id] = -1

        # Send initial heartbeat
        self.send_heartbeat()

    def send_heartbeat(self):
        """Send heartbeats to all followers"""
        if self.state != NodeState.LEADER:
            return
        
        for peer_id in self.peers:
            if peer_id == self.node_id or peer_id in self.blocked_peers:
                continue

            threading.Thread(target=self.replicate_log, args=(peer_id,), daemon=True).start()

    def replicate_log(self, peer_id):
        """Replicate log to a specific follower"""
        with self.lock:
            if self.state != NodeState.LEADER:
                return
            
            next_idx = self.next_index.get(peer_id, 0)
            prev_log_index = next_idx - 1
            prev_log_term = self.log[prev_log_index].term if prev_log_index >= 0 else 0

            entries = []
            if next_idx < len(self.log):
                entries = self.log[next_idx:]

            request = raft_pb2.AppendEntriesRequest(
                term=self.current_term,
                leader_id=self.node_id,
                prev_log_index=prev_log_index,
                prev_log_term=prev_log_term,
                entries=entries,
                leader_commit=self.commit_index
            )
        
        try:
            stub = self.get_peer_stub(peer_id)
            if stub:
                response = stub.AppendEntries(request, timeout=self.RPC_TIMEOUT)

                with self.lock:
                    if response.term > self.current_term:
                        self.current_term = response.term
                        self.state = NodeState.FOLLOWER
                        self.voted_for = None
                        return
                    
                    if response.success:
                        self.match_index[peer_id] = prev_log_index + len(entries)
                        self.next_index[peer_id] = self.match_index[peer_id] + 1
                        self.update_commit_index()
                    else:
                        self.next_index[peer_id] = max(0, self.next_index[peer_id] - 1)
        except Exception as e:
            pass

    def update_commit_index(self):
        """Update commit index in leader based on majority replication"""
        if self.state != NodeState.LEADER:
            return
        
        for n in range(self.commit_index + 1, len(self.log)):
            if self.log[n].term != self.current_term:
                continue

            replicated_count = 1
            for peer_id in self.peers:
                if peer_id != self.node_id and self.match_index.get(peer_id, -1) >= n:
                    replicated_count += 1

                if replicated_count > len(self.peers) // 2:
                    self.commit_index = n
                    self.apply_committed_entries()

    def run(self):
        """Main loop for the Raft node"""
        while True:
            time.sleep(self.TICK_RATE)

            with self.lock:
                current_time = time.time()
                elapsed = current_time - self.last_heartbeat

                if self.state == NodeState.LEADER:
                    if current_time - self.last_heartbeat_sent >= self.HEARTBEAT_INTERVAL:
                        self.send_heartbeat()
                        self.last_heartbeat_sent = current_time

                elif elapsed > self.election_timeout:
                    threading.Thread(target=self.start_election, daemon=True).start()

def get_cluster_config(num_nodes=5, base_port=50050):
    """Generate cluster configuration dynamically"""
    peers = {}
    for i in range(num_nodes):
        peers[i] = f'localhost:{base_port + i}'
    return peers

def start_server(node_id, num_nodes=5, base_port=50050):
    """Start the gRPC server for a Raft node"""
    peers = get_cluster_config(num_nodes, base_port)
    port = base_port + node_id

    node = Raft(node_id, peers, port)

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    raft_pb2_grpc.add_RaftServicer_to_server(node, server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()

    print(f"[Node {node_id}] server started on port {port}")

    threading.Thread(target=node.run, daemon=True).start()

    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        print(f"\n[Node {node_id}] shutting down...")
        server.stop(0)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=int, required=True)
    parser.add_argument("--num_nodes", type=int, default=DEFAULT_NUM_NODES)
    parser.add_argument("--base_port", type=int, default=DEFAULT_BASE_PORT)

    args = parser.parse_args()

    start_server(args.id, args.num_nodes, args.base_port)