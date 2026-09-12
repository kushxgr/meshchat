"""
compare_protocols.py
---------------------
Headless (no GUI) benchmark: spins up the 5-node ring topology
(topology_demo.json) twice -- once running Flooding, once running
AODV-lite -- and measures:

  1. Packet overhead   -- total packets transmitted (control + data)
                           across all nodes to deliver N messages
  2. End-to-end latency -- time from send to decrypt-and-deliver
  3. Failure recovery   -- after severing the B<->C link mid-run,
                           how long / how many extra packets it takes
                           for messages A -> D to keep arriving

Run:
    python compare_protocols.py
Results are printed as a summary table and raw per-node CSVs are
left in logs/ for deeper inspection (e.g. load into pandas or
Wireshark-style manual review).
"""

import os
import shutil
import time
import glob
import csv
from collections import defaultdict

from node import Node
from topology import load_topology

TOPO_PATH = os.path.join(os.path.dirname(__file__), "topology_demo.json")
NODE_IDS = ["A", "B", "C", "D", "E"]
BASE_PORT = 7100
N_MESSAGES = 8
SETTLE_TIME = 3.0      # let HELLO/KEYADV flood before sending
MSG_GAP = 1.5           # seconds between messages
FAILURE_AFTER_MSG = 2   # sever the active link after this many messages


def clear_logs():
    log_dir = os.path.join(os.path.dirname(__file__), "logs")
    if os.path.isdir(log_dir):
        shutil.rmtree(log_dir)


def build_nodes(protocol):
    topo = load_topology(TOPO_PATH)
    ports = {nid: BASE_PORT + i for i, nid in enumerate(NODE_IDS)}
    all_ports = list(ports.values())
    nodes = {}
    for nid in NODE_IDS:
        n = Node(
            node_id=nid, port=ports[nid], mode="sim", sim_peer_ports=all_ports,
            protocol=protocol, topology=topo,
        )
        received = []
        n.on_message(lambda src, text, meta, box=received: box.append((src, text, meta)))
        n._received_box = received  # stash for the harness to read
        nodes[nid] = n
    return nodes, topo


def _sever_active_path(nodes, topo, sender, receiver):
    """
    Break a real link on the path currently being used to reach `receiver`.
    For AODV-lite this is read straight out of the sender's route table, so
    the cut genuinely invalidates the in-use route (exercising RERR +
    rediscovery). For Flooding there is no route table -- it has no
    "active path" to target, so we just sever one edge on the shortest
    path in the topology graph, which best illustrates that flooding
    doesn't need or use route state to keep working.
    """
    route = getattr(nodes[sender].routing, "routes", {}).get(receiver)
    if route:
        a, b = sender, route["next_hop"]
    else:
        a, b = "B", "C"  # a fixed edge on the ring, fine for flooding's stateless case
    print(f"  -> severing {a}<->{b} link (simulated relay failure on the active path)")
    if b in topo.get(a, []):
        topo[a] = [x for x in topo[a] if x != b]
    if a in topo.get(b, []):
        topo[b] = [x for x in topo[b] if x != a]


def run_scenario(protocol):
    print(f"\n=== Running scenario: {protocol} ===")
    nodes, topo = build_nodes(protocol)
    for n in nodes.values():
        n.start()

    time.sleep(SETTLE_TIME)  # let KEYADV / HELLO propagate so keys are known

    sender, receiver = "A", "D"

    # Prime the route (AODV-lite) / warm the dedup cache (flooding) with one
    # message before the measured loop, so the later failure injection can
    # reliably target whatever path actually ended up carrying traffic.
    nodes[sender].send_chat(receiver, "warmup")
    time.sleep(3.0)

    delivered_latencies = []
    for i in range(N_MESSAGES):
        text = f"msg-{i}"
        nodes[sender].send_chat(receiver, text)

        if i + 1 == FAILURE_AFTER_MSG:
            _sever_active_path(nodes, topo, sender, receiver)

        time.sleep(MSG_GAP)

    time.sleep(2.0)  # drain any in-flight recovery traffic

    for n in nodes.values():
        n.stop()

    return nodes


def summarize():
    print("\n=== Summary ===")
    for protocol in ("flooding", "aodv_lite"):
        files = glob.glob(os.path.join(os.path.dirname(__file__), "logs", f"*_{protocol}.csv"))
        total_packets = 0
        latencies = []
        recovery_events = 0
        for path in files:
            with open(path) as f:
                for row in csv.DictReader(f):
                    if row["event"] in ("tx_data", "tx_control"):
                        total_packets += 1
                    if row["event"] == "delivered" and "latency_ms=" in row["extra"]:
                        latencies.append(float(row["extra"].split("=")[1]))
                    if row["event"] in ("route_broken", "route_recovered"):
                        recovery_events += 1
        avg_latency = sum(latencies) / len(latencies) if latencies else float("nan")
        print(f"{protocol:12s}  total_tx_packets={total_packets:4d}  "
              f"delivered={len(latencies):2d}  avg_latency_ms={avg_latency:6.1f}  "
              f"route_events={recovery_events}")


if __name__ == "__main__":
    clear_logs()
    run_scenario("flooding")
    run_scenario("aodv_lite")
    summarize()
    print("\nPer-node raw logs are in logs/*.csv")
