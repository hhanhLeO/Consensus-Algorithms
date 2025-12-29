import subprocess
import sys
import time

NUM_NODES = 5
processes = []

print("Starting RAFT cluster with 5 nodes...")

# (Optional) generate gRPC code
subprocess.run([
    sys.executable, "-m", "grpc_tools.protoc",
    "-I.", "--python_out=.", "--grpc_python_out=.", "raft.proto"
], check=True)

for i in range(NUM_NODES):
    p = subprocess.Popen(
        [sys.executable, "-u", "raft_node.py", str(i)],
        stdout=open(f"node_{i}.log", "w"),
        stderr=subprocess.STDOUT
    )
    processes.append(p)
    print(f"Starting node {i} | PID = {p.pid}")
    time.sleep(0.5)

print("All nodes started.")
print("Press Ctrl+C to stop cluster.")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nStopping cluster...")
    for p in processes:
        p.terminate()
