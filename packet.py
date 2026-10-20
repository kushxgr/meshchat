"""
packet.py
---------
Wire format for all mesh packets. JSON-over-UDP for readability and
easy Wireshark/packet-log inspection during the protocol comparison.

Common header fields on every packet:
    type      - one of the PacketType constants below
    msg_id    - unique id for dedup / loop prevention (uuid4 hex)
    src       - originating node id
    last_hop  - id of the node that most recently (re)transmitted this
                packet; rewritten at every hop. Used for neighbor
                filtering, i.e. simulating "out of radio range".
    ttl       - hop budget, decremented at every relay
    ts        - float timestamp (time.time()) set at *original* send,
                used for end-to-end latency measurement

Type-specific fields are added on top of the common header.
"""

import json
import time
import uuid

MAX_TTL = 8


class PacketType:
    HELLO = "HELLO"          # neighbor liveness beacon
    KEYADV = "KEYADV"        # public-key advertisement (flooded)
    DATA = "DATA"            # encrypted chat payload
    ACK = "ACK"              # end-to-end delivery acknowledgement
    RREQ = "RREQ"            # AODV-lite route request
    RREP = "RREP"            # AODV-lite route reply
    RERR = "RERR"            # AODV-lite route error


def new_msg_id() -> str:
    return uuid.uuid4().hex[:12]


def make_packet(ptype: str, src: str, **fields) -> dict:
    pkt = {
        "type": ptype,
        "msg_id": new_msg_id(),
        "src": src,
        "last_hop": src,
        "ttl": MAX_TTL,
        "ts": time.time(),
    }
    pkt.update(fields)
    return pkt


def encode(pkt: dict) -> bytes:
    return json.dumps(pkt, separators=(",", ":")).encode("utf-8")


def decode(raw: bytes) -> dict:
    return json.loads(raw.decode("utf-8"))
