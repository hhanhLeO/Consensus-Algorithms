import grpc
import argparse
from block import Block
import pbft_pb2
import pbft_pb2_grpc
import time
import os


NUM_NODES = 5

if os.path.exists("cluster.conf"):
    try:
        with open("cluster.conf") as fconf:
            NUM_NODES = int(fconf.read().strip())
    except Exception:
        pass  # If there is an error, the default settings will remain.

F = (NUM_NODES - 1) // 3
PRIMARY_ADDR = "localhost:50050"
PEERS = {i: f"localhost:{50050+i}" for i in range(NUM_NODES)}


def send_block(block):
    with grpc.insecure_channel(PRIMARY_ADDR) as ch:
        stub = pbft_pb2_grpc.PBFTNodeStub(ch)
        reply = stub.ClientRequest(pbft_pb2.ClientBlockRequest(
            block=pbft_pb2.Block(
                height=block.height,
                prev_hash=block.prev_hash,
                hash=block.hash
            )
        ))
        print("Primary reply:", reply.message)


def get_status(addr=PRIMARY_ADDR):
    with grpc.insecure_channel(addr) as ch:
        stub = pbft_pb2_grpc.PBFTNodeStub(ch)
        return stub.NodeStatus(pbft_pb2.NodeStatusRequest())


def print_status(status):
    print("\nBlockchain:")
    for b in status.blockchain:
        print(f"Height: {b.height}, Hash: {b.hash}, Prev: {b.prev_hash}")

    print("\nPrepares:")
    for pm in status.prepares:
        counts = ", ".join([f"{bc.block_hash}({bc.count})" for bc in pm.block_counts])
        print(f"View {pm.view}, Seq {pm.seq}: [{counts}]")

    print("\nBlackList:")
    for bl in status.blacklist:
        print(f" - Node {bl}")

    print("\nCommits:")
    for cm in status.commits:
        counts = ", ".join([f"{bc.block_hash}({bc.count})" for bc in cm.block_counts])
        print(f"View {cm.view}, Seq {cm.seq}: [{counts}]")


def wait_quorum_for_block(target_hash, timeout_sec=20, poll_interval=0.5):
    deadline = time.time() + timeout_sec
    needed = 2 * F + 1
    while time.time() < deadline:
        count = 0
        for _, addr in PEERS.items():
            try:
                status = get_status(addr)
                if status.blockchain and status.blockchain[-1].hash == target_hash:
                    count += 1
            except Exception:
                pass
        if count >= needed:
            return True
        time.sleep(poll_interval)
    return False


def menu():
    while True:
        print("\nMenu:")
        print("1. Create block")
        print("2. Create multiple blocks")
        print("3. View node status (blockchain, quorum, blacklist)")
        print("4. Exit")
        choice = input("Select: ")

        if choice == "1":
            status = get_status(PRIMARY_ADDR)
            last_hash = "_XMAS_" if len(status.blockchain) == 0 else status.blockchain[-1].hash
            height = len(status.blockchain) + 1
            block = Block(height, last_hash)
            print(f"Proposed: Block(height={block.height}, prev={block.prev_hash[:6]}, hash={block.hash[:6]})")
            send_block(block)
            ok = wait_quorum_for_block(block.hash, timeout_sec=20)
            print("Client quorum:", "achieved" if ok else "not achieved")

        elif choice == "2":
            n = int(input("Number of blocks to create: "))
            status = get_status(PRIMARY_ADDR)
            if status.blockchain:
                prev_hash = status.blockchain[-1].hash
                start_height = status.blockchain[-1].height + 1
            else:
                prev_hash = "_XMAS_"
                start_height = 1

            for i in range(start_height, start_height + n):
                block = Block(i, prev_hash)
                print(f"Proposed: Block(height={block.height}, prev={block.prev_hash[:6]}, hash={block.hash[:6]})")
                send_block(block)
                ok = wait_quorum_for_block(block.hash, timeout_sec=20)
                print(f"Block {i} quorum:", "achieved" if ok else "not achieved")
                if not ok:
                    print("Stopping batch: previous block did not reach quorum.")
                    break
                prev_hash = block.hash

        elif choice == "3":
            status = get_status(PRIMARY_ADDR)
            print_status(status)

        elif choice == "4":
            print("Exiting.")
            break

        else:
            print("Invalid choice!")


if __name__ == "__main__":
    menu()