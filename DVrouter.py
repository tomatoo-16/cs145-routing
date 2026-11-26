import json
from router import Router
from packet import Packet

INFINITY = 16


class DVrouter(Router):
    """Distance vector routing protocol implementation."""

    def __init__(self, addr, heartbeat_time):
        Router.__init__(self, addr)  # Initialize base class - DO NOT REMOVE
        self.heartbeat_time = heartbeat_time
        self.last_time = 0
        self.neighbors = {}
        self.neighbor_dvs = {}
        self.routing_table = {self.addr: (0, None)}

    def broadcast_dv(self):
        for port, info in self.neighbors.items():
            neighbor_addr = info["addr"]
            dv_to_send = {}
            for dest, (cost, next_port) in self.routing_table.items():
                if next_port == port and dest != neighbor_addr:
                    dv_to_send[dest] = INFINITY
                else:
                    dv_to_send[dest] = cost

            content = json.dumps(dv_to_send)
            pkt = Packet(Packet.ROUTING, self.addr, neighbor_addr, content)
            self.send(port, pkt)

    def recompute_dv(self):
        new_table = {self.addr: (0, None)}

        all_dests = set()
        for info in self.neighbors.values():
            all_dests.add(info["addr"])
        for dv in self.neighbor_dvs.values():
            all_dests.update(dv.keys())

        for dest in all_dests:
            if dest == self.addr:
                continue

            best_cost = INFINITY
            best_port = None

            for port, info in self.neighbors.items():
                n_addr = info["addr"]
                link_cost = info["cost"]

                if dest == n_addr:
                    cost = link_cost
                elif n_addr in self.neighbor_dvs and dest in self.neighbor_dvs[n_addr]:
                    cost = link_cost + self.neighbor_dvs[n_addr][dest]
                else:
                    cost = INFINITY

                if cost < best_cost:
                    best_cost = cost
                    best_port = port

            if best_cost < INFINITY:
                new_table[dest] = (best_cost, best_port)

        if new_table != self.routing_table:
            self.routing_table = new_table
            self.broadcast_dv()

    def handle_packet(self, port, packet):
        if packet.is_traceroute:
            if packet.dst_addr in self.routing_table:
                _, out_port = self.routing_table[packet.dst_addr]
                if out_port is not None:
                    self.send(out_port, packet)
        else:
            dv = json.loads(packet.content)
            self.neighbor_dvs[packet.src_addr] = dv
            self.recompute_dv()

    def handle_new_link(self, port, endpoint, cost):
        self.neighbors[port] = {"addr": endpoint, "cost": cost}
        self.recompute_dv()

    def handle_remove_link(self, port):
        if port in self.neighbors:
            n_addr = self.neighbors[port]["addr"]
            del self.neighbors[port]
            if n_addr in self.neighbor_dvs:
                del self.neighbor_dvs[n_addr]
            self.recompute_dv()

    def handle_time(self, time_ms):
        if time_ms - self.last_time >= self.heartbeat_time:
            self.last_time = time_ms
            self.broadcast_dv()

    def __repr__(self):
        return f"DVrouter(addr={self.addr}, table={self.routing_table})"
