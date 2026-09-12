"""
debug_three_nodes_no_gui.py
------------------------------
Same as run_local_demo.py's node setup (3 nodes, one process, same
topology) but with NO Tkinter/GUI at all -- just a plain status-print
loop, like debug_two_nodes.py but with a 3rd node added. This isolates
whether the bug is specifically about Tkinter's mainloop, or about
having 3+ Node/Transport objects alive in one process regardless of
any GUI.

Usage:
    python debug_three_nodes_no_gui.py
"""

import time
from node import Node
from topology import load_topology

topo = load_topology("topology_chain3.json")
ports = {"A": 20000, "B": 20001, "C": 20002}
all_ports = list(ports.values())

nodes = {}
for nid in ["A", "B", "C"]:
    n = Node(node_id=nid, port=ports[nid], mode="sim", sim_peer_ports=all_ports,
              protocol="flooding", topology=topo)
    nodes[nid] = n

for n in nodes.values():
    n.start()

print("3 nodes started (A,B,C), no GUI. Watching for 20 seconds...")
for i in range(20):
    time.sleep(1)
    for nid, n in nodes.items():
        print(f"[t={i+1}s] {nid}: pubkeys_known={list(n.peer_pubkeys.keys())} "
              f"last_heard={list(n.last_heard.keys())}")

for n in nodes.values():
    n.stop()
