import pytest

from crypto_utils import generate_keypair, derive_shared_key, encrypt, decrypt
from packet import PacketType, make_packet, encode, decode
from topology import is_neighbor


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
