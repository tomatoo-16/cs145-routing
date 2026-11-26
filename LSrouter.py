####################################################
# LSrouter.py
# Name:
# HUID:
#####################################################

import json
import heapq
from router import Router
from packet import Packet


class LSrouter(Router):
    """Link state routing protocol implementation."""

    def __init__(self, addr, heartbeat_time):
        Router.__init__(self, addr)  # Initialize base class - DO NOT REMOVE
        self.heartbeat_time = heartbeat_time
        self.last_time = 0
        self.seq_num = 0
        # Lưu thông tin các cổng nối trực tiếp: {port: (endpoint_addr, cost)}
        self.neighbors = {}
        # Lưu bản đồ toàn mạng: {router_addr: (seq_num, {neighbor_addr: cost})}
        self.topology = {self.addr: (0, {})}
        # Bảng chuyển tiếp: {dest_addr: out_port}
        self.forwarding_table = {}

    def _build_local_links(self):
        """Tạo dictionary {neighbor_addr: cost} từ các cổng hiện tại."""
        links = {}
        for _, (endpoint, cost) in self.neighbors.items():
            # Nếu có nhiều link tới cùng 1 endpoint, lấy chi phí nhỏ nhất
            if endpoint not in links or cost < links[endpoint]:
                links[endpoint] = cost
        return links

    def _broadcast_own_lsp(self, increment_seq=True):
        """Tăng sequence number (nếu có thay đổi) và gửi LSP của chính mình ra các cổng."""
        if increment_seq:
            self.seq_num += 1
        local_links = self._build_local_links()
        self.topology[self.addr] = (self.seq_num, local_links)

        payload = json.dumps({
            "seq": self.seq_num,
            "links": local_links
        })
        for port, (endpoint, _) in self.neighbors.items():
            pkt = Packet(Packet.ROUTING, self.addr, endpoint, payload)
            self.send(port, pkt)

    def _recompute_routes(self):
        """Chạy thuật toán Dijkstra trên self.topology để cập nhật forwarding_table."""
        # Xây dựng đồ thị vô hướng/có hướng từ self.topology
        # Lưu ý: một cạnh (u, v) chỉ hợp lệ nếu u khai báo v (và nếu v là router trong topology thì v cũng khai báo u)
        graph = {}
        for u, (_, u_links) in self.topology.items():
            graph.setdefault(u, {})
            for v, cost in u_links.items():
                if v in self.topology:
                    # Kiểm tra hai chiều để tránh dùng link chết chưa kịp xóa ở đầu bên kia
                    if u in self.topology[v][1]:
                        graph[u][v] = cost
                else:
                    # v là client (không tự phát LSP), tin tưởng khai báo từ router u
                    graph[u][v] = cost

        # Dijkstra từ self.addr
        dist = {self.addr: 0}
        first_hop = {}
        pq = [(0, self.addr)]

        while pq:
            d, u = heapq.heappop(pq)
            if d > dist.get(u, float("inf")):
                continue

            for v, weight in graph.get(u, {}).items():
                new_dist = d + weight
                if new_dist < dist.get(v, float("inf")):
                    dist[v] = new_dist
                    # Xác định bước nhảy đầu tiên rời khỏi self.addr
                    if u == self.addr:
                        first_hop[v] = v
                    else:
                        first_hop[v] = first_hop[u]
                    heapq.heappush(pq, (new_dist, v))

        # Ánh xạ first_hop sang port ra tương ứng
        addr_to_port = {}
        for port, (endpoint, cost) in self.neighbors.items():
            if endpoint not in addr_to_port or cost < self.neighbors[addr_to_port[endpoint]][1]:
                addr_to_port[endpoint] = port

        new_ft = {}
        for dest, hop_addr in first_hop.items():
            if hop_addr in addr_to_port:
                new_ft[dest] = addr_to_port[hop_addr]

        self.forwarding_table = new_ft

    def handle_packet(self, port, packet):
        """Process incoming packet."""
        if packet.is_traceroute:
            if packet.dst_addr in self.forwarding_table:
                self.send(self.forwarding_table[packet.dst_addr], packet)
        else:
            src = packet.src_addr
            if src == self.addr:
                return

            data = json.loads(packet.content)
            seq = data["seq"]
            links = data["links"]

            # Chỉ xử lý nếu sequence number mới hơn thông tin đang lưu
            if src not in self.topology or seq > self.topology[src][0]:
                self.topology[src] = (seq, links)
                self._recompute_routes()

                # Flooding: chuyển tiếp nguyên vẹn gói LSP ra tất cả các port khác
                for out_port, (endpoint, _) in self.neighbors.items():
                    if out_port != port:
                        fwd_pkt = Packet(Packet.ROUTING, src, endpoint, packet.content)
                        self.send(out_port, fwd_pkt)

    def handle_new_link(self, port, endpoint, cost):
        """Handle new link."""
        self.neighbors[port] = (endpoint, cost)
        self._broadcast_own_lsp(increment_seq=True)
        self._recompute_routes()

    def handle_remove_link(self, port):
        """Handle removed link."""
        if port in self.neighbors:
            del self.neighbors[port]
            self._broadcast_own_lsp(increment_seq=True)
            self._recompute_routes()

    def handle_time(self, time_ms):
        """Handle current time."""
        if time_ms - self.last_time >= self.heartbeat_time:
            self.last_time = time_ms
            self._broadcast_own_lsp(increment_seq=False)

    def __repr__(self):
        """Representation for debugging in the network visualizer."""
        return f"LSrouter(addr={self.addr}, ft={self.forwarding_table})"
