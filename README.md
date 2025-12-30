# Consensus Algorithms

## Raft

### Run code
- Generate Python gRPC code from the Raft protocol definition
```bash
python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. raft.proto
```
- Run `cluster_manager.py` with optional parameters to configure the number of nodes and the base port for the cluster.
```bash
python cluster_manager.py # run 5 nodes and base port 50050
python cluster_manager.py --num_nodes 7 --base_port 8000 # run 7 nodes and base port 8000
```
- After running, you have some guides for controlling cluster lifecycle
```bash
============================================================
Cluster Manager Initialized
Nodes: 5
Ports: 50050-50054
============================================================


        ╔══════════════════════════════════════════════════════════════╗
        ║                     RAFT CLUSTER MANAGER                     ║
        ╚══════════════════════════════════════════════════════════════╝

        Commands:
        start <id>       - Start node
        start all        - Start all nodes
        kill <id>        - Kill node (simulate crash)
        restart <id>     - Restart node
        stop <id>        - Stop node gracefully
        stop all         - Stop all nodes
        status           - Show cluster status
        wait <seconds>   - Wait for stability
        quit             - Exit

        Example:
        > start all
        > kill 0
        > wait 10
        > restart 0
        > status
        > quit


cluster>
```
- To start all the nodes in cluster, run command:
```bash
cluster>start all
```
- Now, all the nodes in cluster have started and the terminal displays some information about the nodes in cluster
```bash
============================================================
Starting all 5 nodes...
============================================================
Node 0 started | PID=22792 | Port=50050 | Log=node_0.log
Node 1 started | PID=27108 | Port=50051 | Log=node_1.log
Node 2 started | PID=11532 | Port=50052 | Log=node_2.log
Node 3 started | PID=28980 | Port=50053 | Log=node_3.log
Node 4 started | PID=21968 | Port=50054 | Log=node_4.log

All nodes started
```
- You can stop, kill, view status,... by using the commands in guides
- Run `raft_client.py` with optional parameters used when running `cluster_manager.py`, to interact with cluster
```bash
python raft_client.py # run 5 nodes and base port 50050
python raft_client.py --num_nodes 7 --base_port 8000 # run 7 nodes and base port 8000
```
- Now, you can send request to cluster, simulate network partition by choosing options in the program

## pBFT

### Run 5 nodes
```bash
cd pbft
python start_cluster.py
```

### Run client to interact with cluster
```bash
cd pbft
python pbft_client.py
```
