"""
main.py
-------
Launch one mesh-chat node with a GUI.

NOTE: avoid ports 6000-6002 on Windows -- they're commonly claimed by
X11/WSLg display-server components and traffic to them can be
silently dropped even though bind()/sendto() report success. Use
20000+ instead, as in the examples below.

Local simulation example (3 terminals, one machine, ports 20000-20002):
    python main.py --id A --port 20000 --peers 20000,20001,20002 --protocol flooding --topology topology_demo.json
    python main.py --id B --port 20001 --peers 20000,20001,20002 --protocol flooding --topology topology_demo.json
    python main.py --id C --port 20002 --peers 20000,20001,20002 --protocol flooding --topology topology_demo.json

(Tip: on Windows, run_local_demo.py runs all simulated nodes in ONE
process instead of 3 terminals, which sidesteps some Windows-specific
cross-process networking quirks entirely -- see README.md.)

Real Windows Mobile Hotspot example (run on each physical device,
after connecting them all to the same hotspot -- find the hotspot's
broadcast address, typically 192.168.137.255):
    python main.py --id phone1 --port 6000 --mode hotspot --broadcast 192.168.137.255 --protocol aodv_lite
"""

import argparse
from node import Node
from gui import ChatGUI


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True, help="unique node id, e.g. A")
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--mode", choices=["sim", "hotspot"], default="sim")
    ap.add_argument("--peers", default="", help="sim mode only: comma-separated ports of all nodes")
    ap.add_argument("--broadcast", default="255.255.255.255", help="hotspot mode: subnet broadcast address")
    ap.add_argument("--protocol", choices=["flooding", "aodv_lite"], default="flooding")
    ap.add_argument("--topology", default=None, help="sim mode only: path to topology.json for multi-hop testing")
    ap.add_argument("--dst", default=None, help="pre-fill the 'To:' field")
    args = ap.parse_args()

    sim_peer_ports = [int(p) for p in args.peers.split(",") if p.strip()] if args.peers else []

    topo = None
    if args.topology:
        from topology import load_topology
        topo = load_topology(args.topology)

    node = Node(
        node_id=args.id,
        port=args.port,
        mode=args.mode,
        sim_peer_ports=sim_peer_ports,
        broadcast_addr=args.broadcast,
        protocol=args.protocol,
        topology=topo,
    )

    gui = ChatGUI(node, default_dst=args.dst)
    gui.run()


if __name__ == "__main__":
    main()
