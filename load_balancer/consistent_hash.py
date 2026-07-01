class ConsistentHashMap:
    M = 512
    K = 9
    def __init__(self):
        self.ring = [None] * self.M
        self.servers = {}

    def _H(self, i):
        return (i**2+ 2*i + 17) %self.M
    def _Phi(self, i, j):
        return (i**2+ j**2 + 2 * j + 25) %self.M
    def add_server(self, server_id, name):
        self.servers[name] = server_id
        for j in range(self.K):
            slot = self._Phi(server_id, j)
            while self.ring[slot] is not None:
                slot = (slot + 1) % self.M
            self.ring[slot] = name
    def remove_server(self, name):
        server_id = self.servers.pop(name, None)
        if server_id is None:
            return
        for j in range(self.K):
            slot = self._Phi(server_id, j)

            for _ in range(self.M):
                if self.ring[slot] == name:
                    self.ring[slot] = None
                    break
                slot = (slot+1) % self.M
    def get_server(self, request_id):
        if not any(self.ring):
            return None
        slot = self._H(request_id)
        for _ in range(self.M):
            if self.ring[slot] is not None:
                return self.ring[slot]
            slot = (slot + 1) % self.M
        return None
