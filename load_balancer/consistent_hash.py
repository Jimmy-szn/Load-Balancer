
import math

def default_H(request_id: int, num_slots: int) -> int:
    """Hash function for mapping a client request onto the ring."""
    return (request_id ** 2 + 2 * request_id + 17) % num_slots


def default_Phi(server_id: int, replica_id: int, num_slots: int) -> int:
    """Hash function for mapping a virtual server replica onto the ring."""
    return (server_id ** 2 + replica_id ** 2 + 2 * replica_id + 25) % num_slots


class ConsistentHashMap:
    def __init__(self, num_slots: int = 512, num_virtual: int = None,
                 H=default_H, Phi=default_Phi):
        self.num_slots = num_slots
        # K = log2(num_slots)
        self.num_virtual = num_virtual or int(math.log2(num_slots))
        self.H = H
        self.Phi = Phi

        self.ring = [None] * num_slots          # slot -> server_id
        self.server_slots = {}                  # server_id -> [occupied slots]

   

    def _probe(self, slot: int) -> int:
        """Linear probe from `slot` until an empty slot is found."""
        start = slot
        for step in range(self.num_slots):
            candidate = (start + step) % self.num_slots
            if self.ring[candidate] is None:
                return candidate
        raise RuntimeError("Ring is full — cannot place another virtual server")


    def add_server(self, server_id: int) -> None:
        if server_id in self.server_slots:
            raise ValueError(f"Server {server_id} already present in the ring")

        occupied = []
        for j in range(self.num_virtual):
            slot = self.Phi(server_id, j, self.num_slots)
            slot = self._probe(slot)
            self.ring[slot] = server_id
            occupied.append(slot)
        self.server_slots[server_id] = occupied

    def remove_server(self, server_id: int) -> None:
        if server_id not in self.server_slots:
            raise ValueError(f"Server {server_id} not present in the ring")
        for slot in self.server_slots[server_id]:
            self.ring[slot] = None
        del self.server_slots[server_id]

    def get_server(self, request_id: int):
        """Return the server_id responsible for this request, or None if
        the ring has no servers."""
        if not self.server_slots:
            return None
        slot = self.H(request_id, self.num_slots)
        for step in range(self.num_slots):
            candidate = (slot + step) % self.num_slots
            if self.ring[candidate] is not None:
                return self.ring[candidate]
        return None  

    def servers(self):
        """List of server_ids currently on the ring."""
        return list(self.server_slots.keys())

    def load_distribution(self):
        """Occupied-slot count per server — a proxy for ring coverage, not
        actual request load (use get_server on a request sample for that)."""
        return {sid: len(slots) for sid, slots in self.server_slots.items()}

#  smoke test
if __name__ == "__main__":
    chm = ConsistentHashMap(num_slots=512)  # num_virtual defaults to 9

    for sid in (1, 2, 3):
        chm.add_server(sid)

    print(f"Servers on ring: {chm.servers()}")
    print(f"Virtual servers per server (K): {chm.num_virtual}")
    print(f"Slots occupied per server: {chm.load_distribution()}")

    # Route a sample of request IDs and tally hits per server
    import random
    random.seed(42)
    tally = {sid: 0 for sid in chm.servers()}
    N_REQUESTS = 10000
    for _ in range(N_REQUESTS):
        rid = random.randint(100000, 999999)  
        server = chm.get_server(rid)
        tally[server] += 1

    print(f"\nRequest distribution over {N_REQUESTS} requests:")
    for sid, count in sorted(tally.items()):
        pct = 100 * count / N_REQUESTS
        print(f"  Server {sid}: {count} ({pct:.1f}%)")

    # Failure simulation: drop Server 2
    print("\nRemoving Server 2 (simulated failure)...")
    chm.remove_server(2)
    tally_after = {sid: 0 for sid in chm.servers()}
    for _ in range(N_REQUESTS):
        rid = random.randint(100000, 999999)
        server = chm.get_server(rid)
        tally_after[server] += 1
    for sid, count in sorted(tally_after.items()):
        pct = 100 * count / N_REQUESTS
        print(f"  Server {sid}: {count} ({pct:.1f}%)")