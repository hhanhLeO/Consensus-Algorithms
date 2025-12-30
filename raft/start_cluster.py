import subprocess
import sys
import time
import argparse

# Default configuration
DEFAULT_NUM_NODES = 5
DEFAULT_BASE_PORT = 50050

def start_cluster(num_nodes, base_port):
    """Start RAFT cluster with specified number of nodes"""
    
    # Validation
    if num_nodes < 1:
        print("Error: Number of nodes must be at least 1")
        sys.exit(1)
    
    print(f"{'='*60}")
    print(f"Starting RAFT cluster with {num_nodes} nodes")
    print(f"{'='*60}")
    
    # Generate gRPC code (optional, comment out if already done)
    print("\n[1/3] Generating gRPC code...")
    try:
        subprocess.run([
            sys.executable, "-m", "grpc_tools.protoc",
            "-I.", "--python_out=.", "--grpc_python_out=.", "raft.proto"
        ], check=True, capture_output=True)
        print("gRPC code generated")
    except subprocess.CalledProcessError as e:
        print(f"Warning: gRPC generation failed (may already exist)")
    
    # Start nodes
    print(f"\n[2/3] Starting {num_nodes} nodes...")
    processes = []
    
    for i in range(num_nodes):
        # Start node
        p = subprocess.Popen(
            [sys.executable, "-u", "raft_node.py", "--id", str(i), "--num_nodes", str(num_nodes), "--base_port", str(base_port)],
            stdout=open(f"node_{i}.log", "w"),
            stderr=subprocess.STDOUT
        )
        processes.append(p)
        
        port = base_port + i
        print(f"Node {i} started | PID={p.pid} | Port={port}")
        time.sleep(0.5)  # Small delay between starts
    
    # Print cluster info
    print(f"\n[3/3] Cluster started successfully!")
    print(f"\n{'='*60}")
    print(f"CLUSTER INFO:")
    print(f"{'='*60}")
    print(f"  Nodes:     {num_nodes}")
    print(f"  Ports:     {base_port}-{base_port + num_nodes - 1}")
    print(f"  Quorum:    {num_nodes // 2 + 1} nodes")
    print(f"  Log files: node_0.log - node_{num_nodes-1}.log")
    print(f"{'='*60}")
    
    # Keep running until Ctrl+C
    print("Press Ctrl+C to stop cluster...")
    try:
        while True:
            # Check if any process died
            for i, p in enumerate(processes):
                if p.poll() is not None:
                    print(f"\nWarning: Node {i} died (exit code: {p.returncode})")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\nStopping cluster...")
        for i, p in enumerate(processes):
            if p.poll() is None:  # Still running
                p.terminate()
                print(f"  Stopped Node {i}")
        
        # Wait for all to terminate
        time.sleep(1)
        
        # Force kill if needed
        for p in processes:
            if p.poll() is None:
                p.kill()
        
        print("\nCluster stopped")

def main():
    """Parse arguments and start cluster"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--num_nodes", type=int, default=DEFAULT_NUM_NODES)
    parser.add_argument("--base_port", type=int, default=DEFAULT_BASE_PORT)

    args = parser.parse_args()

    start_cluster(args.num_nodes, args.base_port)

if __name__ == "__main__":
    main()