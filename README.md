# Consensus Algorithms

## Raft

### Run 5 nodes
```bash
cd raft
python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. raft.proto
python start_cluster.py
```

### Run client to interact with cluster
```bash
cd raft
python raft_client.py
```

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