import subprocess
import sys
import time
import argparse

# Default configuration
DEFAULT_NUM_NODES = 5
DEFAULT_BASE_PORT = 50050

class ClusterManager:
    """
    Manage RAFT cluster lifecycle
    Can start, stop, kill, restart individual nodes
    """
    
    def __init__(self, num_nodes=5, base_port=50050):
        """
        Initialize cluster manager
        
        Args:
            num_nodes: Number of nodes in cluster
            base_port: Starting port number
        """
        self.num_nodes = num_nodes
        self.base_port = base_port
        self.processes = {}  # {node_id: Process object}
        self.log_files = {}  # {node_id: log file path}
        
        print(f"{'='*60}")
        print(f"Cluster Manager Initialized")
        print(f"Nodes: {num_nodes}")
        print(f"Ports: {base_port}-{base_port + num_nodes - 1}")
        print(f"{'='*60}\n")
    
    def start_node(self, node_id):
        """
        Start a single node
        
        Args:
            node_id: Node ID to start
        
        Returns:
            bool: True if started successfully
        """
        if node_id in self.processes and self.is_alive(node_id):
            print(f"Node {node_id} is already running (PID={self.processes[node_id].pid})")
            return False
        
        # Log file path
        log_file = f"node_{node_id}.log"
        self.log_files[node_id] = log_file
        
        # Start node process
        try:
            p = subprocess.Popen(
                [sys.executable, "-u", "raft_node.py", "--id", str(node_id), "--num_nodes", str(self.num_nodes), "--base_port", str(self.base_port)],
                stdout=open(log_file, "w"),
                stderr=subprocess.STDOUT
            )
            
            self.processes[node_id] = p
            port = self.base_port + node_id
            
            print(f"Node {node_id} started | PID={p.pid} | Port={port} | Log={log_file}")
            return True
            
        except Exception as e:
            print(f"Failed to start Node {node_id}: {e}")
            return False
    
    def start_all(self, delay=0.5):
        """
        Start all nodes in the cluster
        
        Args:
            delay: Delay between starting each node (seconds)
        """
        print(f"\n{'='*60}")
        print(f"Starting all {self.num_nodes} nodes...")
        print(f"{'='*60}")
        
        for i in range(self.num_nodes):
            self.start_node(i)
            time.sleep(delay)
        
        print(f"\nAll nodes started")
        self.show_status()
    
    def kill_node(self, node_id):
        """
        Kill a node (force stop, like crash)
        
        Args:
            node_id: Node ID to kill
        
        Returns:
            bool: True if killed successfully
        """
        if node_id not in self.processes:
            print(f"Node {node_id} was never started")
            return False
        
        if not self.is_alive(node_id):
            print(f"Node {node_id} is already dead")
            return False
        
        try:
            p = self.processes[node_id]
            
            # Try graceful termination first
            p.terminate()
            time.sleep(0.5)
            
            # Force kill if still alive
            if p.poll() is None:
                p.kill()
            
            print(f"Node {node_id} killed (was PID={p.pid})")
            return True
            
        except Exception as e:
            print(f"Failed to kill Node {node_id}: {e}")
            return False
    
    def restart_node(self, node_id, delay=1.0):
        """
        Restart a node (kill if alive, then start)
        
        Args:
            node_id: Node ID to restart
            delay: Wait time between kill and start
        
        Returns:
            bool: True if restarted successfully
        """
        print(f"\nRestarting Node {node_id}...")
        
        # Kill if alive
        if self.is_alive(node_id):
            self.kill_node(node_id)
            time.sleep(delay)
        
        # Start
        return self.start_node(node_id)
    
    def stop_node(self, node_id):
        """
        Gracefully stop a node (not a crash)
        
        Args:
            node_id: Node ID to stop
        """
        if node_id not in self.processes:
            print(f"Node {node_id} was never started")
            return False
        
        if not self.is_alive(node_id):
            print(f"Node {node_id} is already stopped")
            return False
        
        try:
            p = self.processes[node_id]
            p.terminate()
            p.wait(timeout=5)
            print(f"Node {node_id} stopped gracefully (was PID={p.pid})")
            return True
        except subprocess.TimeoutExpired:
            p.kill()
            print(f"Node {node_id} force stopped (was PID={p.pid})")
            return True
        except Exception as e:
            print(f"Failed to stop Node {node_id}: {e}")
            return False
    
    def stop_all(self):
        """Stop all nodes gracefully"""
        print(f"\n{'='*60}")
        print(f"Stopping all nodes...")
        print(f"{'='*60}")
        
        for node_id in range(self.num_nodes):
            if self.is_alive(node_id):
                self.stop_node(node_id)
        
        print(f"\nAll nodes stopped")
    
    def is_alive(self, node_id):
        """
        Check if a node is alive
        
        Args:
            node_id: Node ID to check
        
        Returns:
            bool: True if alive
        """
        if node_id not in self.processes:
            return False
        
        p = self.processes[node_id]
        return p.poll() is None
    
    def get_pid(self, node_id):
        """
        Get PID of a node
        
        Args:
            node_id: Node ID
        
        Returns:
            int or None: PID if alive, None otherwise
        """
        if node_id not in self.processes:
            return None
        
        if not self.is_alive(node_id):
            return None
        
        return self.processes[node_id].pid
    
    def show_status(self):
        """Display status of all nodes"""
        print(f"\n{'='*60}")
        print(f"Cluster Status:")
        print(f"{'='*60}")
        
        alive_count = 0
        for node_id in range(self.num_nodes):
            if self.is_alive(node_id):
                pid = self.get_pid(node_id)
                port = self.base_port + node_id
                print(f"  Node {node_id}: ✓ ALIVE   | PID={pid:5d} | Port={port}")
                alive_count += 1
            else:
                port = self.base_port + node_id
                print(f"  Node {node_id}: ✗ DEAD    | Port={port}")
        
        quorum = self.num_nodes // 2 + 1
        has_quorum = alive_count >= quorum
        
        print(f"\n  Alive: {alive_count}/{self.num_nodes}")
        print(f"  Quorum: {quorum} nodes")
        print(f"  Status: {'HAS QUORUM' if has_quorum else 'NO QUORUM'}")
        print(f"{'='*60}\n")
    
    def wait_for_stability(self, seconds=5):
        """Wait for cluster to stabilize"""
        print(f"Waiting {seconds}s for cluster to stabilize...")
        time.sleep(seconds)
        print(f"Done waiting")
    
    def cleanup(self):
        """Cleanup: stop all nodes"""
        print(f"\n{'='*60}")
        print(f"Cleanup: Stopping all nodes...")
        print(f"{'='*60}")
        
        self.stop_all()
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup"""
        self.cleanup()


def main():
    """Interactive cluster management shell"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--num_nodes", type=int, default=DEFAULT_NUM_NODES)
    parser.add_argument("--base_port", type=int, default=DEFAULT_BASE_PORT)

    args = parser.parse_args()

    manager = ClusterManager(args.num_nodes, args.base_port)
    
    print("""
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
    """)
    
    while True:
        try:
            cmd = input("\ncluster> ").strip().lower()
            
            if not cmd:
                continue
            
            parts = cmd.split()
            action = parts[0]
            
            if action == "quit" or action == "exit":
                print("\nGoodbye!")
                manager.cleanup()
                break
            
            elif action == "start":
                if len(parts) < 2:
                    print("Usage: start <id> or start all")
                elif parts[1] == "all":
                    manager.start_all()
                else:
                    node_id = int(parts[1])
                    manager.start_node(node_id)
            
            elif action == "kill":
                if len(parts) < 2:
                    print("Usage: kill <id>")
                else:
                    node_id = int(parts[1])
                    manager.kill_node(node_id)
            
            elif action == "restart":
                if len(parts) < 2:
                    print("Usage: restart <id>")
                else:
                    node_id = int(parts[1])
                    manager.restart_node(node_id)
            
            elif action == "stop":
                if len(parts) < 2:
                    print("Usage: stop <id> or stop all")
                elif parts[1] == "all":
                    manager.stop_all()
                else:
                    node_id = int(parts[1])
                    manager.stop_node(node_id)
            
            elif action == "status":
                manager.show_status()
            
            elif action == "wait":
                seconds = int(parts[1]) if len(parts) > 1 else 5
                manager.wait_for_stability(seconds)
            
            else:
                print(f"Unknown command: {action}")
                print("Type 'help' for command list")
        
        except KeyboardInterrupt:
            print("\n\nInterrupted. Cleaning up...")
            manager.cleanup()
            break
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    main()