"""
topology.py
-----------
In SIM mode all nodes physically receive every broadcast packet over
loopback (see transport.py). To actually test *multi-hop* routing we
need some nodes to be "out of range" of others. This module loads a
simple adjacency list from JSON and each Node uses it to drop packets
whose immediate sender (last_hop) is not a declared neighbor -- i.e.
software-simulated radio range, applied identically to every packet
regardless of routing protocol.

In HOTSPOT mode this is unused: everyone connected to the same
Windows Mobile Hotspot is genuinely in range of everyone else, so if
you want real multi-hop over real hardware you need >=3 physical
devices where the outer two are out of Wi-Fi range of each other but
both in range of a middle relay device. topology.json is then not
needed at all -- physics does the filtering for you.
"""

import json


def load_topology(path: str) -> dict:
    """
    JSON format:
    {
      "A": ["B"],
      "B": ["A", "C"],
      "C": ["B"]
    }
    Meaning: A can only directly hear B; B can hear A and C; etc.
    (Should be symmetric for a sane wireless model, but not enforced.)
    """
    with open(path) as f:
        return json.load(f)


def is_neighbor(topology: dict, me: str, other: str) -> bool:
    if topology is None:
        return True  # no restriction -> fully connected (single-hop) mesh
    return other in topology.get(me, [])
