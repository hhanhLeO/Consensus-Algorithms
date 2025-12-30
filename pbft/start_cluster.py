import subprocess
import sys
import time

NUM_NODES = 5
BYZANTINE_NODE = 3
processes = []

print("Starting PBFT cluster with 5 nodes...")

# (Optional) generate gRPC code from pbft.proto
subprocess.run([
    sys.executable, "-m", "grpc_tools.protoc",
    "-I.", "--python_out=.", "--grpc_python_out=.", "pbft.proto"
], check=True)

# Launch PBFT replica processes
for i in range(NUM_NODES):
    if i == BYZANTINE_NODE:
        cmd = [sys.executable, "-u", "pbft_node.py", "--id", str(i), "--port", str(50050+i), "--byzantine"]
    else:
        cmd = [sys.executable, "-u", "pbft_node.py", "--id", str(i), "--port", str(50050+i)]

    p = subprocess.Popen(cmd)
    processes.append(p)
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