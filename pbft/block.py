import hashlib

# Simplified block structure for PBFT simulation.
class Block:
    def __init__(self, height, prev_hash):
        self.height = height
        self.prev_hash = prev_hash
        self.hash = self.compute_hash()

    def compute_hash(self):
        data = f"{self.prev_hash}{self.height}".encode()
        return hashlib.sha256(data).hexdigest()