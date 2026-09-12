"""
transport.py
------------
Abstracts "send this packet to everyone in my radio range" so the
same routing/crypto code runs in two modes:

1. HOTSPOT mode: real UDP broadcast on a Windows Mobile Hotspot subnet
   (e.g. 192.168.137.255). Every physically-connected device is in
   the same single broadcast domain, exactly like real Wi-Fi.

2. SIM mode: everything runs on localhost. Since loopback has no true
   broadcast, each node instead unicasts to every *known* node port
   on 127.0.0.1. This reproduces "everyone in range hears it" for
   testing without physical hardware. Multi-hop restriction is then
   applied purely in software via a topology file (topology.py) that
   says who is allowed to be whose direct neighbor -- this is what
   lets one laptop simulate a multi-hop mesh.
"""

import socket
import threading


class Transport:
    def __init__(self, node_id, port, mode="sim", sim_peer_ports=None,
                 broadcast_addr="255.255.255.255", on_receive=None):
        self.node_id = node_id
        self.port = port
        self.mode = mode
        self.sim_peer_ports = sim_peer_ports or []
        self.broadcast_addr = broadcast_addr
        self.on_receive = on_receive
        self._running = False

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if mode == "hotspot":
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.sock.bind(("", port))

    def start(self):
        self._running = True
        t = threading.Thread(target=self._recv_loop, daemon=True)
        t.start()
        return t

    def stop(self):
        self._running = False
        try:
            self.sock.close()
        except OSError:
            pass

    def _recv_loop(self):
        while self._running:
            try:
                raw, addr = self.sock.recvfrom(65535)
            except OSError:
                break
            if self.on_receive:
                self.on_receive(raw, addr)

    def broadcast(self, raw: bytes):
        """Send to everyone within (simulated or real) radio range."""
        try:
            if self.mode == "hotspot":
                self.sock.sendto(raw, (self.broadcast_addr, self.port))
            else:
                for p in self.sim_peer_ports:
                    if p == self.port:
                        continue
                    self.sock.sendto(raw, ("127.0.0.1", p))
        except OSError:
            # The node may already be stopping on another thread.
            return

    def unicast(self, raw: bytes, dest_addr):
        """Send to a specific known address (used for AODV RREP/data-on-route)."""
        try:
            self.sock.sendto(raw, dest_addr)
        except OSError:
            # The node may already be stopping on another thread.
            return
