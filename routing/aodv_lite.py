"""
routing/aodv_lite.py
---------------------
A simplified Ad-hoc On-Demand Distance Vector protocol:

- Route discovery only happens when data needs to be sent and no
  active route exists (on-demand, unlike flooding's "flood every
  message").
- RREQ is broadcast/flooded with a growing hop_count; every relay
  records a *reverse route* back toward the RREQ originator.
- The destination (or a relay that already has a fresh route to it)
  unicasts an RREP back along that reverse path, and every relay it
  passes through records a *forward route* toward the destination.
- Once a forward route exists, DATA is unicast hop-by-hop (no more
  flooding) using the route table -- this is AODV-lite's main
  advantage over plain flooding: O(hops) transmissions per message
  instead of O(N).
- RERR is generated when a next-hop forward fails (simulated via a
  liveness/neighbor check) and propagated back toward anyone using
  that route, invalidating it and forcing rediscovery.

Route table entry: dst -> {next_hop, hop_count, expiry}
Reverse table entry (discovery-time only): originator -> {next_hop, hop_count}
"""

import time

from packet import PacketType, make_packet, encode
from routing.base import RoutingProtocol
from config import NEIGHBOR_TIMEOUT

ROUTE_LIFETIME = 20.0     # seconds a discovered route stays valid
RREQ_RETRY_LIMIT = 2
RREQ_TIMEOUT = 2.0


class AODVLite(RoutingProtocol):
    name = "aodv_lite"

    def __init__(self, node):
        super().__init__(node)
        self.routes = {}          # dst -> {next_hop, hop_count, expiry}
        self.reverse = {}         # originator -> {next_hop, hop_count, expiry}
        self.pending = {}         # dst -> list[(payload, msg_id)] queued awaiting a route
        self.rreq_seen_for = {}   # dst -> last rreq send time (avoid spamming)

    # ---------- public API ----------

    def send_data(self, dst: str, encrypted_payload: str, msg_id: str):
        route = self._valid_route(dst)
        if route:
            self._forward_data(dst, encrypted_payload, msg_id, origin=self.node.node_id)
            return
        already_queued = dst in self.pending and len(self.pending[dst]) > 0
        self.pending.setdefault(dst, []).append((encrypted_payload, msg_id))
        if not already_queued:
            # only kick off discovery if one isn't already in flight for this dst;
            # tick() will retry on RREQ_TIMEOUT if this attempt is lost
            self._start_route_discovery(dst)

    def tick(self):
        now = time.time()
        for dst in list(self.routes.keys()):
            route = self.routes[dst]
            if route["expiry"] < now:
                del self.routes[dst]
                self.node.metrics.log("route_broken", extra=f"expired dst={dst}")
                continue
            last_heard = self.node.last_heard.get(route["next_hop"], 0)
            if now - last_heard > NEIGHBOR_TIMEOUT:
                # our next hop toward dst has gone quiet -> link is dead,
                # this is the reactive failure-detection path (no ACKs needed)
                del self.routes[dst]
                self.node.metrics.log(
                    "route_broken", extra=f"neighbor_timeout dst={dst} next_hop={route['next_hop']}"
                )
        # retry discovery for anything still queued
        for dst in list(self.pending.keys()):
            last = self.rreq_seen_for.get(dst, 0)
            if now - last > RREQ_TIMEOUT and self.pending[dst]:
                self._start_route_discovery(dst)

    def handle_packet(self, pkt: dict, addr):
        # RREP/RERR/point-to-point DATA carry an explicit intended-next-hop.
        # The underlying transport may still physically broadcast the bytes
        # (real Wi-Fi is a shared medium, and our sim-mode loopback fallback
        # broadcasts too) -- any *other* neighbor that overhears it must
        # silently ignore it rather than trying to route it itself, exactly
        # like a real 802.11 node discards frames not addressed to it.
        intended = pkt.get("next_hop")
        if intended is not None and intended != self.node.node_id:
            return

        t = pkt["type"]
        if t == PacketType.RREQ:
            self._handle_rreq(pkt)
        elif t == PacketType.RREP:
            self._handle_rrep(pkt)
        elif t == PacketType.RERR:
            self._handle_rerr(pkt)
        elif t == PacketType.DATA:
            self._handle_data(pkt)

    # ---------- route discovery ----------

    def _start_route_discovery(self, dst):
        self.rreq_seen_for[dst] = time.time()
        pkt = make_packet(
            PacketType.RREQ,
            self.node.node_id,
            origin=self.node.node_id,
            dst=dst,
            hop_count=0,
        )
        self.seen.add(pkt["msg_id"])
        self.node.metrics.log("tx_control", pkt["msg_id"], f"RREQ dst={dst}")
        self.node.transport.broadcast(encode(pkt))

    def _handle_rreq(self, pkt):
        if self.already_seen(pkt["msg_id"]):
            return

        # record/refresh reverse route back to the RREQ originator
        self.reverse[pkt["origin"]] = {
            "next_hop": pkt["last_hop"],
            "hop_count": pkt["hop_count"] + 1,
            "expiry": time.time() + ROUTE_LIFETIME,
        }

        if pkt["dst"] == self.node.node_id:
            self._send_rrep(origin=pkt["origin"], dst=pkt["dst"], hop_count=0)
            return

        existing = self._valid_route(pkt["dst"])
        if existing:
            # we already know a fresh route to the destination -> reply on its behalf
            self._send_rrep(origin=pkt["origin"], dst=pkt["dst"], hop_count=existing["hop_count"])
            return

        pkt["ttl"] -= 1
        if pkt["ttl"] <= 0:
            return
        pkt["hop_count"] += 1
        pkt["last_hop"] = self.node.node_id
        self.node.metrics.log("tx_control", pkt["msg_id"], "RREQ relay")
        self.node.transport.broadcast(encode(pkt))

    def _send_rrep(self, origin, dst, hop_count):
        rev = self.reverse.get(origin)
        if not rev:
            return  # no path back, give up
        pkt = make_packet(
            PacketType.RREP,
            self.node.node_id,
            origin=origin,
            dst=dst,
            hop_count=hop_count,
        )
        self.node.metrics.log("tx_control", pkt["msg_id"], f"RREP dst={dst}")
        self._unicast_next(pkt, rev["next_hop"])

    def _handle_rrep(self, pkt):
        if self.already_seen(pkt["msg_id"]):
            return
        # forward route: toward pkt['dst'], reachable via whoever just sent us this RREP.
        # Prefer the shorter of any two candidate routes received during one discovery,
        # matching real AODV's "freshest + shortest" route selection.
        new_hops = pkt["hop_count"] + 1
        current = self.routes.get(pkt["dst"])
        if current is None or new_hops <= current["hop_count"]:
            self.routes[pkt["dst"]] = {
                "next_hop": pkt["last_hop"],
                "hop_count": new_hops,
                "expiry": time.time() + ROUTE_LIFETIME,
            }
            self.node.metrics.log("route_recovered", pkt["msg_id"], f"dst={pkt['dst']} hops={new_hops}")

        if pkt["origin"] == self.node.node_id:
            # route discovery finished at the requester -> flush queued messages
            for payload, msg_id in self.pending.pop(pkt["dst"], []):
                self._forward_data(pkt["dst"], payload, msg_id, origin=self.node.node_id)
            return

        rev = self.reverse.get(pkt["origin"])
        if not rev:
            return
        pkt["hop_count"] += 1
        self._unicast_next(pkt, rev["next_hop"])

    def _handle_rerr(self, pkt):
        if self.already_seen(pkt["msg_id"]):
            return
        broken_dst = pkt["dst"]
        if broken_dst in self.routes:
            del self.routes[broken_dst]
            self.node.metrics.log("route_broken", pkt["msg_id"], f"dst={broken_dst} via RERR")
        pkt["ttl"] -= 1
        if pkt["ttl"] > 0:
            pkt["last_hop"] = self.node.node_id
            self.node.transport.broadcast(encode(pkt))

    # ---------- data forwarding ----------

    def _handle_data(self, pkt):
        if self.already_seen(pkt["msg_id"]):
            return
        if pkt["dst"] == self.node.node_id:
            self.node.metrics.log("rx_data", pkt["msg_id"])
            self.node.deliver_local(pkt)
            return

        route = self._valid_route(pkt["dst"])
        if not route:
            self._send_rerr(pkt["dst"], pkt["msg_id"])
            return
        pkt["ttl"] -= 1
        if pkt["ttl"] <= 0:
            return
        pkt["last_hop"] = self.node.node_id
        self.node.metrics.log("tx_data", pkt["msg_id"], "relay(unicast)")
        self._unicast_next(pkt, route["next_hop"])

    def _forward_data(self, dst, encrypted_payload, msg_id, origin):
        route = self._valid_route(dst)
        pkt = make_packet(
            PacketType.DATA,
            self.node.node_id,
            msg_id=msg_id,
            dst=dst,
            payload=encrypted_payload,
        )
        self.seen.add(pkt["msg_id"])
        self.node.metrics.log("tx_data", pkt["msg_id"], f"dst={dst} unicast")
        self._unicast_next(pkt, route["next_hop"])

    def _send_rerr(self, dst, related_msg_id):
        pkt = make_packet(PacketType.RERR, self.node.node_id, dst=dst)
        self.node.metrics.log("route_broken", pkt["msg_id"], f"no route to {dst}, msg={related_msg_id}")
        self.node.transport.broadcast(encode(pkt))

    # ---------- helpers ----------

    def _valid_route(self, dst):
        r = self.routes.get(dst)
        if r and r["expiry"] >= time.time():
            return r
        return None

    def _unicast_next(self, pkt, next_hop_id):
        """
        Logical unicast to a specific neighbor. In HOTSPOT mode we use a
        real per-node socket address (Node.resolve_addr, learned from
        HELLO packets). In SIM mode loopback can't truly broadcast to a
        subset, so we fall back to sending to everyone but stamp the
        packet with next_hop so only the intended neighbor acts on it
        (see the guard at the top of handle_packet).
        """
        pkt["next_hop"] = next_hop_id
        addr = self.node.resolve_addr(next_hop_id)
        if addr and self.node.transport.mode == "hotspot":
            self.node.transport.unicast(encode(pkt), addr)
        else:
            self.node.transport.broadcast(encode(pkt))
