import threading

import pytest

from crypto_utils import generate_keypair, derive_shared_key, encrypt, decrypt
from packet import PacketType, make_packet, encode, decode
from topology import is_neighbor
from node import Node
from config import DELIVERY_TTL


def test_topology_check_restricts_neighbors():
    topology = {"A": ["B"], "B": ["A", "C"], "C": ["B"]}
    assert is_neighbor(topology, "A", "B") is True
    assert is_neighbor(topology, "A", "C") is False
    assert is_neighbor(None, "A", "C") is True


def test_encryption_round_trip_matches_between_peers():
    priv_a, pub_a = generate_keypair()
    priv_b, pub_b = generate_keypair()

    key_a = derive_shared_key(priv_a, pub_b)
    key_b = derive_shared_key(priv_b, pub_a)

    assert key_a == key_b

    aad = b"A->B"
    ciphertext = encrypt(key_a, b"hello mesh chat", aad)
    assert decrypt(key_b, ciphertext, aad) == b"hello mesh chat"


def test_packet_json_round_trip_preserves_fields():
    pkt = make_packet(PacketType.DATA, "A", dst="B", payload="abc123")
    encoded = encode(pkt)
    decoded = decode(encoded)

    assert decoded["type"] == PacketType.DATA
    assert decoded["src"] == "A"
    assert decoded["dst"] == "B"
    assert decoded["payload"] == "abc123"


def test_node_reports_a_peer_only_when_first_discovered():
    class SeenMessages:
        def __init__(self):
            self.seen = set()

        def already_seen(self, msg_id):
            if msg_id in self.seen:
                return True
            self.seen.add(msg_id)
            return False

    node = object.__new__(Node)
    node.node_id = "A"
    node.peer_pubkeys = {}
    node.routing = SeenMessages()
    discovered = []
    node._peer_callback = discovered.append

    node._handle_keyadv({
        "src": "B",
        "pubkey": "public-key",
        "msg_id": "first",
        "ttl": 0,
    })
    node._handle_keyadv({
        "src": "B",
        "pubkey": "updated-key",
        "msg_id": "second",
        "ttl": 0,
    })

    assert discovered == ["B"]
    assert node.peer_pubkeys == {"B": "updated-key"}


def test_acknowledgement_clears_pending_message_and_notifies_sender(monkeypatch):
    class Metrics:
        def __init__(self):
            self.events = []

        def log(self, event, msg_id="", extra=""):
            self.events.append((event, msg_id, extra))

    node = object.__new__(Node)
    node.node_id = "A"
    class SeenMessages:
        def __init__(self):
            self.seen = set()

        def already_seen(self, msg_id):
            if msg_id in self.seen:
                return True
            self.seen.add(msg_id)
            return False

    node.routing = SeenMessages()
    node._pending_lock = threading.Lock()
    node.priv_key = "private-key"
    node.peer_pubkeys = {"B": "peer-key"}
    node._pending_messages = {
        "delivery-1": {"dst": "B", "text": "hello"},
    }
    node._delivery_status_callback = lambda *args: statuses.append(args)
    node.metrics = Metrics()
    node.transport = type("Transport", (), {"broadcast": lambda *args: None})()
    statuses = []
    monkeypatch.setattr("crypto_utils.derive_shared_key", lambda *_: b"key")
    monkeypatch.setattr(
        "crypto_utils.decrypt",
        lambda _key, _payload, _aad: b"delivery-1",
    )

    node._handle_ack({
        "msg_id": "ack-1",
        "src": "B",
        "dst": "A",
        "payload": "encrypted-delivery-id",
        "ttl": 8,
    })

    assert node._pending_messages == {}
    assert statuses == [("delivery-1", "B", "hello", "delivered", DELIVERY_TTL)]


def test_message_is_sent_once_then_expires_without_retry(monkeypatch):
    class Metrics:
        def log(self, *args):
            pass

    class Routing:
        def __init__(self):
            self.sent = []
            self.cancelled = []

        def send_data(self, dst, payload, msg_id, delivery_id=None):
            self.sent.append((dst, payload, msg_id, delivery_id))

        def cancel_pending_delivery(self, delivery_id):
            self.cancelled.append(delivery_id)

    node = object.__new__(Node)
    node.node_id = "A"
    node.peer_pubkeys = {"B": "peer-key"}
    node.priv_key = "private-key"
    node._pending_lock = threading.Lock()
    node._pending_messages = {}
    statuses = []
    node._delivery_status_callback = lambda *args: statuses.append(args)
    node.metrics = Metrics()
    node.routing = Routing()
    monkeypatch.setattr("crypto_utils.derive_shared_key", lambda *_: b"key")
    monkeypatch.setattr("crypto_utils.encrypt", lambda *_: "ciphertext")
    monkeypatch.setattr("packet.new_msg_id", lambda: "delivery-1")

    assert node.send_chat("B", "hello") is True
    node._pending_messages["delivery-1"]["expires_at"] = 0
    node._expire_pending_messages()

    assert node.routing.sent == [("B", "ciphertext", "delivery-1", "delivery-1")]
    assert node.routing.cancelled == ["delivery-1"]
    assert node._pending_messages == {}
    assert statuses == [
        ("delivery-1", "B", "hello", "pending", DELIVERY_TTL),
        ("delivery-1", "B", "hello", "expired", DELIVERY_TTL),
    ]

    # No retry is sent for a pending message: it is sent once and then expires.


def test_duplicate_delivery_is_acknowledged_without_displaying_twice(monkeypatch):
    class Metrics:
        def log(self, *args):
            pass

    class Routing:
        seen = set()

    class Transport:
        def __init__(self):
            self.sent = []

        def broadcast(self, raw):
            self.sent.append(decode(raw))

    node = object.__new__(Node)
    node.node_id = "B"
    node.peer_pubkeys = {"A": "peer-key"}
    node.priv_key = "private-key"
    node._delivery_lock = threading.Lock()
    node._delivered_messages = {("A", "delivery-1")}
    node.routing = Routing()
    node.metrics = Metrics()
    node.transport = Transport()
    messages = []
    node._message_callback = lambda *args: messages.append(args)
    monkeypatch.setattr("crypto_utils.derive_shared_key", lambda *_: b"key")
    monkeypatch.setattr("crypto_utils.decrypt", lambda *_: b"hello")
    monkeypatch.setattr(
        "crypto_utils.encrypt",
        lambda _key, plaintext, _aad: "encrypted:" + plaintext.decode("utf-8"),
    )

    node.deliver_local({
        "src": "A",
        "msg_id": "retry-1",
        "delivery_id": "delivery-1",
        "payload": "ciphertext",
        "ts": 1,
    })

    assert messages == []
    assert node.transport.sent[0]["type"] == PacketType.ACK
    assert node.transport.sent[0]["payload"] == "encrypted:delivery-1"
