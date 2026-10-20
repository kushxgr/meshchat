"""
node_worker.py
----------------
Runs ONE mesh-chat Node with real networking (UDP, X25519/AES-256-GCM
encryption, Flooding/AODV-lite routing) as a standalone process --
exactly like the headless test that was proven to work reliably.

It has NO GUI. It talks to whatever launched it (run_local_demo.py)
over plain stdin/stdout, one JSON object per line:

  Commands read from stdin:
    {"cmd": "send", "dst": "C", "text": "hello"}

  Events written to stdout:
    {"event": "started", "pubkey": "..."}
    {"event": "message", "src": "B", "text": "hi", "latency_ms": 12.3}
    {"event": "send_failed", "dst": "C", "reason": "no pubkey yet"}

This exists so the GUI process's Tkinter event loop never shares a
process with the networking threads at all -- they're fully separate
OS processes talking over a pipe, which sidesteps whatever GUI/thread
interaction was silently preventing the networking threads from
running when they lived in the same process as Tkinter.

Usage (normally launched automatically by run_local_demo.py, not run
by hand):
    python node_worker.py --id A --port 20000 --peers 20000,20001,20002 --protocol flooding --topology topology_chain3.json
"""

import argparse
import json
import sys
import threading

from node import Node
from topology import load_topology


def emit(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--peers", required=True)
    ap.add_argument("--protocol", default="flooding")
    ap.add_argument("--topology", default=None)
    ap.add_argument("--mode", choices=["sim", "hotspot"], default="sim")
    ap.add_argument("--broadcast", default="255.255.255.255")
    args = ap.parse_args()

    sim_peer_ports = [int(p) for p in args.peers.split(",") if p.strip()]
    topo = load_topology(args.topology) if args.topology else None

    try:
        node = Node(node_id=args.id, port=args.port, mode=args.mode,
                    sim_peer_ports=sim_peer_ports, broadcast_addr=args.broadcast,
                    protocol=args.protocol, topology=topo)
    except OSError as exc:
        emit({"event": "error", "message": str(exc)})
        return

    def on_message(src, text, meta):
        emit({"event": "message", "src": src, "text": text, "latency_ms": meta["latency_ms"]})

    node.on_message(on_message)
    try:
        node.start()
    except OSError as exc:
        emit({"event": "error", "message": str(exc)})
        node.stop()
        return
    emit({"event": "started", "pubkey": node.pub_key_b64})

    # Block reading commands from stdin forever -- this is exactly the
    # same "main thread does something else while background threads
    # handle networking" pattern as the headless test that worked.
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            cmd = json.loads(line)
        except json.JSONDecodeError:
            continue
        if cmd.get("cmd") == "send":
            dst, text = cmd["dst"], cmd["text"]
            ok = node.send_chat(dst, text)
            if not ok:
                emit({"event": "send_failed", "dst": dst, "reason": "no pubkey yet"})
        elif cmd.get("cmd") == "quit":
            break

    node.stop()


if __name__ == "__main__":
    main()
