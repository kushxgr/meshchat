"""
routing/flooding.py
--------------------
Naive flooding: every DATA packet is rebroadcast by every node that
hears it for the first time, until TTL hits 0. No route discovery,
no routing table -- simplest possible MANET forwarding, used here as
the baseline against AODV-lite.

Overhead profile: O(N) retransmissions per message across an N-node
mesh (every node forwards once), zero control-packet overhead, but
also zero route "memory" -- every single message re-floods the whole
network from scratch.
"""

from packet import PacketType, make_packet, encode
from routing.base import RoutingProtocol


class Flooding(RoutingProtocol):
    name = "flooding"

    def send_data(self, dst: str, encrypted_payload: str, msg_id: str,
                  delivery_id: str = None):
        pkt = make_packet(
            PacketType.DATA,
            self.node.node_id,
            msg_id=msg_id,
            dst=dst,
            payload=encrypted_payload,
            delivery_id=delivery_id or msg_id,
        )
        self.seen.add(pkt["msg_id"])
        self.node.metrics.log("tx_data", pkt["msg_id"], f"dst={dst}")
        self.node.transport.broadcast(encode(pkt))

    def handle_packet(self, pkt: dict, addr):
        if pkt["type"] != PacketType.DATA:
            return

        if self.already_seen(pkt["msg_id"]):
            self.node.metrics.log("duplicate_dropped", pkt["msg_id"])
            return

        if pkt["dst"] == self.node.node_id:
            self.node.metrics.log("rx_data", pkt["msg_id"])
            self.node.deliver_local(pkt)
            return  # destination does not re-flood

        pkt["ttl"] -= 1
        if pkt["ttl"] <= 0:
            return

        pkt["last_hop"] = self.node.node_id
        self.node.metrics.log("tx_data", pkt["msg_id"], "relay")
        self.node.transport.broadcast(encode(pkt))
