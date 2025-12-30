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

### Run nodes
- Run `start_cluster.py`
```bash
cd pbft
python start_cluster.py
```
- After running the command, the program will display a line to enter the number of nodes.
- Once entered, the program will calculate the maximum number of nodes that can perform the Byzantine behavior that the program can handle.
- Finally, enter the value of the node that we want to perform the Byzantine behavior (excluding node 0 because we chose this node as primary and in the program we haven't yet handled "view change" - a situation where the primary performs the Byzantine behavior).
- Of course, you can press "enter" to skip entering any values, and the program will run by default: a total of 5 nodes with 1 node performing the Byzantine behavior - node 3.
- Example:
```bash
=== PBFT Cluster Launcher ===
Enter number of nodes (default 5): 7
Fault tolerance f = 2
Enter Byzantine node IDs (comma separated, or Enter for default [3]): 4,5
Starting PBFT cluster with 7 nodes...
Node 0 running on port 50050 (N=7, f=2)
Node 1 running on port 50051 (N=7, f=2)
Node 2 running on port 50052 (N=7, f=2)
Node 3 running on port 50053 (N=7, f=2)
Node 4 running on port 50054 (N=7, f=2)
Node 5 running on port 50055 (N=7, f=2)
Node 6 running on port 50056 (N=7, f=2)
All nodes started. Press Ctrl+C to stop cluster.
```

### Open another terminal, run client to interact with cluster
- Run `pbft_client.py`
```bash
cd pbft
python pbft_client.py
```
- Then select the functions:
```bash
Menu:
1. Create block
2. Create multiple blocks
3. View node status (blockchain, quorum, blacklist)
4. Exit
Select:
```
- Function 1: Create 1 block
```bash
Select: 1
Proposed: Block(height=1, prev=_XMAS_, hash=3042fb)
Primary reply: PrePrepare sent
Client quorum: achieved
```

- Function 2: Create multiple blocks. After selecting this function, the user enters the number of blocks they want to create.
```bash
Select: 2
Number of blocks to create: 3
Proposed: Block(height=2, prev=3042fb, hash=370c0e)
Primary reply: PrePrepare sent
Block 2 quorum: achieved
Proposed: Block(height=3, prev=370c0e, hash=12ada9)
Primary reply: PrePrepare sent
Block 3 quorum: achieved
Proposed: Block(height=4, prev=12ada9, hash=bb5e80)
Primary reply: PrePrepare sent
Block 4 quorum: achieved
```

- Function 3: View node status: Blockchain, Quorum, Blacklist
```bash
Select: 3

Blockchain:
Height: 1, Hash: 3042fbdaead39b360c6ce1e72f171c288821e2f21c3abcc4057d4816da156268, Prev: _XMAS_       
Height: 2, Hash: 370c0e5ae9e425d0a4f9ea3dfdb800cb6b007d98cb80e1381afaa4a78d4002aa, Prev: 3042fbdaead39b360c6ce1e72f171c288821e2f21c3abcc4057d4816da156268
Height: 3, Hash: 12ada933ef08a5570a2bad4e5321f1e76222068ec2347c4293a2e2e06e0273b0, Prev: 370c0e5ae9e425d0a4f9ea3dfdb800cb6b007d98cb80e1381afaa4a78d4002aa
Height: 4, Hash: bb5e802fdc504b646d9e9a708228a2e782f8973f16e9cfe387a26080921792dd, Prev: 12ada933ef08a5570a2bad4e5321f1e76222068ec2347c4293a2e2e06e0273b0

Prepares:
View 0, Seq 1: [3042fbdaead39b360c6ce1e72f171c288821e2f21c3abcc4057d4816da156268(5), _FAKE_(2)]       
View 0, Seq 2: [370c0e5ae9e425d0a4f9ea3dfdb800cb6b007d98cb80e1381afaa4a78d4002aa(5)]
View 0, Seq 3: [12ada933ef08a5570a2bad4e5321f1e76222068ec2347c4293a2e2e06e0273b0(5)]
View 0, Seq 4: [bb5e802fdc504b646d9e9a708228a2e782f8973f16e9cfe387a26080921792dd(5)]

BlackList:
 - Node 4
 - Node 5

Commits:
View 0, Seq 1: [3042fbdaead39b360c6ce1e72f171c288821e2f21c3abcc4057d4816da156268(7)]
View 0, Seq 2: [370c0e5ae9e425d0a4f9ea3dfdb800cb6b007d98cb80e1381afaa4a78d4002aa(5)]
View 0, Seq 3: [12ada933ef08a5570a2bad4e5321f1e76222068ec2347c4293a2e2e06e0273b0(5)]
View 0, Seq 4: [bb5e802fdc504b646d9e9a708228a2e782f8973f16e9cfe387a26080921792dd(5)]
```

- Function 4: Exit
```bash
Select: 4
Exiting.
```