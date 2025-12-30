import subprocess
import sys
import time

NUM_NODES = 5
BYZANTINE_NODES = [3]

def main():
    print("=== PBFT Cluster Launcher ===")

    while True:
        num_nodes_in = input(f"Enter number of nodes (default {NUM_NODES}): ").strip()
        num_nodes = int(num_nodes_in) if num_nodes_in else NUM_NODES
        f = (num_nodes - 1) // 3
        print(f"Fault tolerance f = {f}")

        if num_nodes < 4:
            print("Error: PBFT requires at least 4 nodes (N >= 3f+1). Please enter again.")
            continue
        break

    with open("cluster.conf", "w") as fconf:
        fconf.write(str(num_nodes))

    while True:
        byz_input = input(
            f"Enter Byzantine node IDs (comma separated, or Enter for default {BYZANTINE_NODES}): "
        ).strip()
        if byz_input:
            try:
                byzantine_nodes = [int(x) for x in byz_input.split(",")]
            except ValueError:
                print("Error: Invalid input. Please enter integers separated by commas.")
                continue
        else:
            byzantine_nodes = BYZANTINE_NODES

        if len(byzantine_nodes) > f:
            print(f"Error: Too many Byzantine nodes! Allowed maximum = {f}. Please enter again.")
            continue

        if 0 in byzantine_nodes:
            print("Error: Node 0 is the primary and cannot be Byzantine. Please enter again.")
            continue

        if any(x < 0 or x >= num_nodes for x in byzantine_nodes):
            print(f"Error: Byzantine node IDs must be between 0 and {num_nodes-1}. Please enter again.")
            continue

        break

    processes = []
    print(f"Starting PBFT cluster with {num_nodes} nodes...")

    subprocess.run([
        sys.executable, "-m", "grpc_tools.protoc",
        "-I.", "--python_out=.", "--grpc_python_out=.", "pbft.proto"
    ], check=True)

    for i in range(num_nodes):
        port = 50050 + i
        cmd = [sys.executable, "-u", "pbft_node.py",
               "--id", str(i), "--port", str(port),
               "--num_nodes", str(num_nodes)]
        if i in byzantine_nodes:
            cmd.append("--byzantine")

        p = subprocess.Popen(cmd)
        processes.append(p)
        time.sleep(0.5)

    print("All nodes started. Press Ctrl+C to stop cluster.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping cluster...")
        for p in processes:
            p.terminate()

if __name__ == "__main__":
    main()