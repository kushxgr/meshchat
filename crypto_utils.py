"""
crypto_utils.py
----------------
End-to-end encryption primitives for the mesh chat app.

- X25519 for ephemeral/static Diffie-Hellman key agreement
- HKDF-SHA256 to derive a symmetric key from the shared secret
- AES-256-GCM for authenticated encryption of message payloads

Design: every node has one long-term X25519 keypair generated at
startup. Public keys are distributed network-wide via KEYADV packets
(flooded, small payload). When node A wants to message node B, it
computes shared_secret = ECDH(A_priv, B_pub) and derives a per-peer
AES key with HKDF. Because X25519 is symmetric, B independently
derives the *same* key from ECDH(B_priv, A_pub) without any extra
round trip. Only the two endpoints ever hold this key -- relay nodes
only ever see ciphertext.
"""

import os
import base64
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey, X25519PublicKey
)
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

NONCE_LEN = 12  # 96-bit nonce, standard for AES-GCM


def generate_keypair():
    """Return (private_key_obj, public_key_bytes_b64)."""
    priv = X25519PrivateKey.generate()
    pub_bytes = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return priv, base64.b64encode(pub_bytes).decode()


def pubkey_from_b64(pub_b64: str) -> X25519PublicKey:
    raw = base64.b64decode(pub_b64)
    return X25519PublicKey.from_public_bytes(raw)


def derive_shared_key(my_priv: X25519PrivateKey, peer_pub_b64: str, salt: bytes = b"mesh-chat-v1") -> bytes:
    """ECDH + HKDF -> 32-byte AES-256 key, shared identically by both peers."""
    peer_pub = pubkey_from_b64(peer_pub_b64)
    shared_secret = my_priv.exchange(peer_pub)
    derived = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=b"mesh-chat-aes-gcm-key",
    ).derive(shared_secret)
    return derived


def encrypt(key: bytes, plaintext: bytes, aad: bytes = b"") -> str:
    """Encrypt with AES-256-GCM. Returns base64(nonce || ciphertext)."""
    aesgcm = AESGCM(key)
    nonce = os.urandom(NONCE_LEN)
    ct = aesgcm.encrypt(nonce, plaintext, aad)
    return base64.b64encode(nonce + ct).decode()


def decrypt(key: bytes, blob_b64: str, aad: bytes = b"") -> bytes:
    """Decrypt base64(nonce || ciphertext). Raises InvalidTag if key/AAD wrong."""
    raw = base64.b64decode(blob_b64)
    nonce, ct = raw[:NONCE_LEN], raw[NONCE_LEN:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ct, aad)
