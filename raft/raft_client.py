import grpc
import raft_pb2
import raft_pb2_grpc
import time
import argparse

DEFAULT_NUM_NODES = 5
DEFAULT_BASE_PORT = 50050

class RaftClient:
    def __init__(self, nodes):
        """
        Initialize client with list of node addresses
        nodes: dict of {node_id: address}
        """
        self.nodes = nodes
        self.current_leader = None
    
    def get_stub(self, node_id):
        """Get gRPC stub for a node"""
        try:
            channel = grpc.insecure_channel(self.nodes[node_id])
            return raft_pb2_grpc.RaftStub(channel)
        except Exception as e:
            print(f"Error connecting to node {node_id}: {e}")
            return None

    def send_command(self, command, leader_hint=None):
        """Send a command to the cluster with optional leader hint"""
        tried_nodes = set()
        
        # Priority 1: Try leader hint if provided
        if leader_hint is not None and leader_hint in self.nodes:
            tried_nodes.add(leader_hint)
            print(f"[Hint] Trying suggested leader: Node {leader_hint}")
            
            stub = self.get_stub(leader_hint)
            if stub:
                try:
                    request = raft_pb2.ClientRequestMsg(command=command)
                    response = stub.ClientRequest(request, timeout=1.0)
                    
                    if response.success:
                        self.current_leader = leader_hint
                        print(f"Command sent to leader (Node {leader_hint}) [HINT]")
                        return True
                    elif response.leader_id >= 0:
                        # Got redirected
                        self.current_leader = response.leader_id
                        print(f"[Hint] Node {leader_hint} redirected to Node {response.leader_id}")
                except Exception as e:
                    print(f"[Hint] Node {leader_hint} error: {e}")
        
        # Priority 2: Try cached current leader
        if self.current_leader is not None and self.current_leader not in tried_nodes:
            tried_nodes.add(self.current_leader)
            print(f"[Cache] Trying cached leader: Node {self.current_leader}")
            
            stub = self.get_stub(self.current_leader)
            if stub:
                try:
                    request = raft_pb2.ClientRequestMsg(command=command)
                    response = stub.ClientRequest(request, timeout=1.0)
                    
                    if response.success:
                        print(f"Command sent to leader (Node {self.current_leader}) [CACHE]")
                        return True
                except Exception as e:
                    print(f"[Cache] Error: {e}")
                    self.current_leader = None
        
        # Priority 3: Try all remaining nodes
        print(f"[Search] Searching for leader in remaining nodes...")
        for node_id in self.nodes:
            if node_id in tried_nodes:
                continue
            
            tried_nodes.add(node_id)
            stub = self.get_stub(node_id)
            if stub:
                try:
                    request = raft_pb2.ClientRequestMsg(command=command)
                    response = stub.ClientRequest(request, timeout=1.0)
                    
                    if response.success:
                        self.current_leader = node_id
                        print(f"Command sent to leader (Node {node_id}) [SEARCH]")
                        return True
                except Exception as e:
                    continue
        
        print("Could not find leader")
        return False
    
    def partition_network(self, node_id, blocked_nodes):
        """
        Simulate network partition by blocking connections
        node_id: the node to partition
        blocked_nodes: list of node IDs to block
        """
        stub = self.get_stub(node_id)
        if stub:
            blocked_addresses = [self.nodes[n] for n in blocked_nodes if n in self.nodes]
            request = raft_pb2.PartitionRequest(blocked_addresses=blocked_addresses)
            try:
                response = stub.NetworkPartition(request, timeout=1.0)
                if response.success:
                    print(f"Network partition applied to Node {node_id}")
                    return True
            except Exception as e:
                print(f"Error applying partition: {e}")
        return False
    
    def clear_partition(self, node_id):
        """Clear network partition for a node"""
        stub = self.get_stub(node_id)
        if stub:
            request = raft_pb2.PartitionRequest(blocked_addresses=[])
            try:
                response = stub.NetworkPartition(request, timeout=1.0)
                if response.success:
                    print(f"Network partition cleared for Node {node_id}")
                    return True
            except Exception as e:
                print(f"Error clearing partition: {e}")
        return False
    
    def partition_bidirectional(self, node_a, node_b):
        """Create bidirectional partition between two nodes"""
        self.partition_network(node_a, [node_b])
        self.partition_network(node_b, [node_a])
        print(f"Bidirectional partition: {node_a} <-> {node_b}")

    def partition_groups(self, group1, group2):
        """Partition two groups of nodes"""
        for node in group1:
            self.partition_network(node, group2)
        for node in group2:
            self.partition_network(node, group1)
        print(f"Group partition: {group1} <-> {group2}")

    def isolate_node(self, node_id, all_nodes):
        """Completely isolate a node from cluster"""
        others = [n for n in all_nodes if n != node_id]
        self.partition_network(node_id, others)
        for other in others:
            self.partition_network(other, [node_id])
        print(f"Isolated node {node_id}")

    def clear_all_partitions(self):
        """Clear all partition in the entire cluster"""
        print("Clearing all partitions...")
    
        successes = []
        for node_id in self.nodes:
            successes.append(self.clear_partition(node_id))
        
        return all(successes)
    

def print_menu():
    print("\n" + "="*60)
    print("RAFT CLUSTER TEST CLIENT")
    print("="*60)
    print("1. Send SET command (SET key value)")
    print("2. Isolate a node (simulate leader/follower failure)")
    print("3. Clear network partition for a node")
    print("4. Clear all network partitions")
    print("5. Network split (partition into two groups)")
    print("6. Exit")
    print("="*60)

def get_cluster_config(num_nodes=5, base_port=50050):
    """Generate cluster configuration dynamically"""
    peers = {}
    for i in range(num_nodes):
        peers[i] = f'localhost:{base_port + i}'
    return peers

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--num_nodes", type=int, default=DEFAULT_NUM_NODES)
    parser.add_argument("--base_port", type=int, default=DEFAULT_BASE_PORT)

    args = parser.parse_args()

    nodes = get_cluster_config(args.num_nodes, args.base_port)
    print(nodes)

    client = RaftClient(nodes)
    
    while True:
        print_menu()
        choice = input("\nEnter choice: ").strip()
        
        if choice == "1":
            key = input("Enter key: ").strip()
            value = input("Enter value: ").strip()
            command = f"SET {key} {value}"
            leader_hint = input("Enter leader hint (press Enter if unknown): ").strip()
            leader_hint = int(leader_hint) if leader_hint != "" else None
            client.send_command(command, leader_hint)
        
        elif choice == "2":
            node_id = int(input(f"Enter node ID to isolate (0-{args.num_nodes - 1}): "))
            if node_id in nodes:
                others = [n for n in nodes if n != node_id]
                client.isolate_node(node_id, others)
                print(f"Node {node_id} was isolated from cluster")
        
        elif choice == "3":
            node_id = int(input(f"Enter node ID to reconnect (0-{args.num_nodes - 1}): "))
            if node_id in nodes:
                client.clear_partition(node_id)
                print(f"Node {node_id} reconnected to cluster")
                print("Waiting for log synchronization...")
                time.sleep(2)

        elif choice == "4":
            is_cleared_all = client.clear_all_partitions()
            if is_cleared_all:
                print("All partitions cleared")
            else:
                print("Some partitions failed to clear")
        
        elif choice == "5":
            print("Splitting network into two groups")
            group1_input = input("Enter Group 1 node IDs (comma-separated, e.g. 0,1,2): ").strip()
            group2_input = input("Enter Group 2 node IDs (comma-separated, e.g. 3,4): ").strip()

            try:
                group1 = [int(x.strip()) for x in group1_input.split(",") if x.strip() != ""]
                group2 = [int(x.strip()) for x in group2_input.split(",") if x.strip() != ""]
            except ValueError:
                print("Invalid input. Please enter only numbers separated by commas.")
                continue

            print(f"Group 1: {group1}")
            print(f"Group 2: {group2}")
            
            client.partition_groups(group1, group2)
            
            print("Network split complete. Waiting to observe behavior...")
            time.sleep(5)
        
        elif choice == "6":
            print("Exiting...")
            break
        
        else:
            print("Invalid choice")

if __name__ == "__main__":
    main()
