"""
node.py
-------
The Node ties together: transport (UDP), topology filtering
(simulated radio range), crypto (per-peer E2E keys), and a pluggable
routing protocol (Flooding or AODV-lite). It exposes a small API a
GUI (or a headless test script) drives:

    node.send_chat(dst_id, text)
    node.on_message(callback)     # callback(src_id, text, meta)

Everything else -- HELLO beacons, KEYADV flooding, packet dispatch,
periodic ticking -- runs on background threads.
"""

import threading
import time

from packet import PacketType, make_packet, encode, decode
import crypto_utils
from metrics import MetricsLogger
from topology import is_neighbor
from routing.flooding import Flooding
from routing.aodv_lite import AODVLite

from config import HELLO_INTERVAL, KEYADV_INTERVAL, TICK_INTERVAL, NEIGHBOR_TIMEOUT  # noqa: F401 (re-exported)

PROTOCOLS = {"flooding": Flooding, "aodv_lite": AODVLite}


class Node:
    def __init__(self, node_id, port, mode="sim", sim_peer_ports=None,
                 broadcast_addr="255.255.255.255", protocol="flooding",
                 topology=None):
        self.node_id = node_id
        self.protocol_name = protocol
        self.topology = topology  # None => fully connected, or dict from topology.py

        self.priv_key, self.pub_key_b64 = crypto_utils.generate_keypair()
        self.peer_pubkeys = {}     # node_id -> pub_key_b64
        self.peer_addrs = {}       # node_id -> (ip, port), populated in hotspot mode from HELLO
        self.last_heard = {}       # node_id -> timestamp of most recent packet accepted from them

        self.metrics = MetricsLogger(node_id, protocol)
        self._message_callback = None
        self._running = False

        from transport import Transport
        self.transport = Transport(
            node_id, port, mode=mode, sim_peer_ports=sim_peer_ports,
            broadcast_addr=broadcast_addr, on_receive=self._on_raw_receive,
        )

        self.routing = PROTOCOLS[protocol](self)

    # ---------- lifecycle ----------

    def start(self):
        self._running = True
        self.transport.start()
        threading.Thread(target=self._periodic_loop, daemon=True).start()

    def stop(self):
        self._running = False
        self.transport.stop()

    def on_message(self, callback):
        """callback(src_id: str, text: str, meta: dict)"""
        self._message_callback = callback

    # ---------- outgoing ----------

    def send_chat(self, dst_id: str, text: str):
        if dst_id not in self.peer_pubkeys:
            # no key yet -> can't encrypt; ask routing layer to (re)discover /
            # rely on next KEYADV flood cycle to learn it, then retry.
            self.metrics.log("tx_data", extra=f"no pubkey yet for {dst_id}")
            return False

        key = crypto_utils.derive_shared_key(self.priv_key, self.peer_pubkeys[dst_id])
        aad = f"{self.node_id}->{dst_id}".encode()
        ciphertext = crypto_utils.encrypt(key, text.encode("utf-8"), aad)
        from packet import new_msg_id
        msg_id = new_msg_id()
        self.routing.send_data(dst_id, ciphertext, msg_id)
        return True

    # ---------- incoming ----------

    def _on_raw_receive(self, raw: bytes, addr):
        try:
            pkt = decode(raw)
        except Exception:
            return

        if pkt.get("src") == self.node_id:
            return  # our own broadcast looped back

        # simulated / real radio-range filtering: only accept from a declared neighbor
        if not is_neighbor(self.topology, self.node_id, pkt.get("last_hop", pkt["src"])):
            return

        self.peer_addrs[pkt["last_hop"]] = addr
        self.last_heard[pkt["last_hop"]] = time.time()

        if pkt["type"] == PacketType.HELLO:
            return  # presence only, nothing further to do
        if pkt["type"] == PacketType.KEYADV:
            self._handle_keyadv(pkt)
            return

        self.routing.handle_packet(pkt, addr)

    def deliver_local(self, pkt):
        """Called by routing protocol once a DATA packet has reached its destination."""
        src = pkt["src"]
        if src not in self.peer_pubkeys:
            return  # can't decrypt without sender's pubkey (shouldn't normally happen)
        key = crypto_utils.derive_shared_key(self.priv_key, self.peer_pubkeys[src])
        aad = f"{src}->{self.node_id}".encode()
        try:
            plaintext = crypto_utils.decrypt(key, pkt["payload"], aad)
        except Exception:
            self.metrics.log("decrypt_failed", pkt.get("msg_id", ""))
            return
        latency_ms = (time.time() - pkt["ts"]) * 1000
        self.metrics.log("delivered", pkt.get("msg_id", ""), f"latency_ms={latency_ms:.1f}")
        if self._message_callback:
            self._message_callback(src, plaintext.decode("utf-8"), {"latency_ms": latency_ms})

    def resolve_addr(self, node_id):
        return self.peer_addrs.get(node_id)

    # ---------- key advertisement ----------

    def _handle_keyadv(self, pkt):
        if self.routing.already_seen(pkt["msg_id"]):
            return
        self.peer_pubkeys[pkt["src"]] = pkt["pubkey"]
        pkt["ttl"] -= 1
        if pkt["ttl"] <= 0:
            return
        pkt["last_hop"] = self.node_id
        self.transport.broadcast(encode(pkt))

    def _send_keyadv(self):
        pkt = make_packet(PacketType.KEYADV, self.node_id, pubkey=self.pub_key_b64)
        self.routing.seen.add(pkt["msg_id"])
        self.transport.broadcast(encode(pkt))

    def _send_hello(self):
        pkt = make_packet(PacketType.HELLO, self.node_id, ttl=1)
        self.transport.broadcast(encode(pkt))

    # ---------- background loop ----------

    def _periodic_loop(self):
        last_hello = last_keyadv = 0
        while self._running:
            now = time.time()
            if now - last_hello >= HELLO_INTERVAL:
                self._send_hello()
                last_hello = now
            if now - last_keyadv >= KEYADV_INTERVAL:
                self._send_keyadv()
                last_keyadv = now
            self.routing.tick()
            time.sleep(TICK_INTERVAL)
