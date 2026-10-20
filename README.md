# Secure Offline Mesh Messaging over Wi-Fi Hotspot with MANET Routing Protocols

An encrypted, internet-independent chat app that runs over a locally created
Wi-Fi hotspot. Devices out of direct radio range talk to each other through
multi-hop relaying (MANET). Two routing protocols — **Flooding** and
**AODV-lite** — are implemented behind the same interface so they can be
swapped in and quantitatively compared for packet overhead, latency, and
failure recovery. All chat content is end-to-end encrypted with X25519 ECDH
+ AES-256-GCM, so relay nodes forward ciphertext they cannot read.

## Project layout

```
mesh_chat/
  crypto_utils.py      X25519 ECDH + HKDF + AES-256-GCM
  packet.py             wire format (JSON-over-UDP) for every packet type
  transport.py           UDP socket wrapper: real hotspot broadcast, or a
                           localhost "everyone hears it" simulation mode
  topology.py            software-simulated radio range (who can hear whom)
  config.py               shared timing constants (HELLO interval, timeouts)
  node.py                  glue: identity, keys, transport, routing dispatch
  routing/
    base.py                common RoutingProtocol interface
    flooding.py             naive flood-and-forward
    aodv_lite.py            on-demand route discovery (RREQ/RREP/RERR)
  metrics.py                per-node CSV event logger
  gui.py                     Tkinter chat window
  main.py                    CLI entry point (one node + GUI)
  app.py                     desktop launcher for local mesh demos
  compare_protocols.py        headless benchmark harness, both protocols
  topology_demo.json          5-node ring with redundant paths
  topology_chain3.json         simple 3-node chain
  logs/                        CSV output from runs (created at runtime)
```

## How the encryption works

Every node generates one X25519 keypair at startup and floods its **public**
key network-wide in small `KEYADV` packets. When node A wants to message
node B, it computes `shared_secret = ECDH(A_priv, B_pub)` and derives a
32-byte AES key via HKDF-SHA256. Because X25519 is symmetric, B
independently derives the identical key from `ECDH(B_priv, A_pub)` — no
extra handshake round trip is needed. The message body is then sealed with
AES-256-GCM (random 96-bit nonce, source/destination bound in as
associated data). Relay nodes route on the plaintext header
(`src`/`dst`/`ttl`) only; the payload is opaque ciphertext to them.

## How the two routing protocols work

**Flooding** (`routing/flooding.py`): every node that hears a `DATA` packet
for the first time rebroadcasts it (decrementing TTL) until it reaches the
destination or TTL hits zero. No routing table, no discovery phase — simple
and always finds a path if one exists, at the cost of every message
re-flooding the whole network.

**AODV-lite** (`routing/aodv_lite.py`): route discovery happens on demand.
When a node has data for a destination it has no route to, it broadcasts an
`RREQ`; every relay records a *reverse route* back to the requester. The
destination (or a relay with a fresh route) unicasts an `RREP` back along
that reverse path, and each hop it passes through records a *forward
route*. Once a route exists, `DATA` is **unicast** hop-by-hop using the
route table instead of being re-flooded. Broken links are detected
reactively: each node tracks when it last heard a HELLO from each neighbor,
and a route whose next hop has gone quiet is dropped and rediscovered on
the next send (`RERR` is also generated/propagated when a relay is asked to
forward toward a destination it has no route for).

Both protocols share the same duplicate-suppression (`msg_id` cache) and
the same neighbor-range check, so the comparison isolates the *routing*
strategy rather than incidental implementation differences.

Every delivered chat message is confirmed with an end-to-end ACK from the
recipient. Each chat message is sent once. The sender keeps it visible as
awaiting receipt for up to 30 seconds, then reports if no ACK arrived; an ACK
clears the pending status earlier. Messages waiting for an AODV-lite route are
removed from that route queue when their delivery TTL expires.

## Simulating multi-hop on one machine (no hardware needed)

A real Wi-Fi hotspot is a single broadcast domain — every connected device
can directly hear every other one. To actually exercise multi-hop relaying
without several physical devices, `topology.json` files declare a software
adjacency list (who is allowed to be whose *direct* neighbor). Every
packet's immediate sender is checked against this list on receipt, exactly
as if it were a radio-range check — so a laptop can simulate a 5-node mesh
by running 5 processes on different ports and restricting who can hear whom.

```
python main.py --id A --port 6000 --peers 6000,6001,6002 --protocol flooding --topology topology_chain3.json --dst C
python main.py --id B --port 6001 --peers 6000,6001,6002 --protocol flooding --topology topology_chain3.json --dst A
python main.py --id C --port 6002 --peers 6000,6001,6002 --protocol flooding --topology topology_chain3.json --dst A
```

With `topology_chain3.json`, A and C are not neighbors — a message from A to
C must relay through B. Swap `--protocol aodv_lite` to compare.

## Running over a real Windows Mobile Hotspot

1. On the host device: Settings → Network & Internet → Mobile hotspot → turn
   it on. Note its IP, typically `192.168.137.1`; the subnet broadcast
   address is then `192.168.137.255`.
2. Connect the other devices to that hotspot Wi-Fi network.
3. On each device:
   ```
   python main.py --id phone1 --port 6000 --mode hotspot --broadcast 192.168.137.255 --protocol aodv_lite --dst phone2
   ```
4. For genuine multi-hop (not just single-hop over the AP), you need a third
   device physically out of Wi-Fi range of one of the endpoints but in
   range of a middle relay device — `topology.json` is not used in hotspot
   mode since real radio range does the filtering for you.

## Desktop app

```
python app.py
```

This opens a launcher window with two connection modes:

- **Local demo** starts multiple simulated nodes on one PC.
- **Wi-Fi / hotspot** starts one node on this PC (the default). Run the
  executable on each Windows device connected to the same Wi-Fi LAN or
  hotspot. Keep the suggested device name as its node ID, or choose a
  different unique ID. Use the same UDP port and broadcast address on all
  devices. The chat window lists discovered peers; select one to message it.

For Windows Mobile Hotspot the subnet broadcast is commonly
`192.168.137.255`; other Wi-Fi networks use their own subnet broadcast.
If peer discovery does not work, check the router's client/AP isolation
setting and allow Mesh Chat to receive UDP traffic on the selected port in
Windows Firewall (Private networks). Guest Wi-Fi networks often isolate
devices. A Wi-Fi access point is usually one broadcast domain; it does not
automatically provide multi-hop relaying between clients.

To build a standalone Windows executable, run `build_app.ps1` on Windows.
It bundles Python, the GUI, cryptography, and topology resources; Python
does not need to be installed on the target PC. The output is
`dist/MeshChatStudio.exe`. The build is for the architecture of the Python
used to build it (normally Windows x64); PyInstaller does not make one
binary compatible with every Windows architecture or version.

Example:

```
powershell -ExecutionPolicy Bypass -File .\build_app.ps1
```

## Inspecting traffic in Wireshark

Filter on `udp.port == 6000` (or whichever port you used) to see the raw
JSON packets on the wire. Because the header (`type`, `src`, `dst`, `ttl`,
`msg_id`) is plaintext, you can watch RREQ/RREP/RERR control traffic and
DATA relaying live; the `payload` field inside DATA packets is base64
ciphertext and will not decode to readable text — that's the point.

## Quantitative comparison (packet overhead / latency / failure recovery)

```
python compare_protocols.py
```

This headless harness builds the 5-node ring topology twice (once per
protocol), sends a burst of messages from A to D, severs whichever link is
actually carrying traffic partway through, and keeps sending. It reports:

- **Packet overhead** — total control + data transmissions across all nodes
  to deliver the message burst
- **Latency** — time from send to successful decrypt-and-deliver at the
  destination
- **Failure recovery** — whether/how many messages are lost during the
  outage window before the protocol reroutes, and how many extra control
  packets (`route_broken`/`route_recovered` events) recovery costs

Per-node raw CSV logs are left in `logs/` for further analysis. In practice
you'll see the expected qualitative tradeoff: flooding has zero discovery
overhead and never "loses" a route (there's no route to lose) but sends
O(N) copies of every single message; AODV-lite pays an upfront route
discovery cost and a brief packet-loss window when its active route breaks,
but then forwards subsequent messages far more cheaply via unicast reuse of
the established route. For short/bursty traffic the discovery cost can
dominate; for sustained conversations AODV-lite's overhead per message
drops well below flooding's.

## Limitations / possible extensions

- `AODV-lite` picks the lowest-hop-count route seen during one discovery
  round rather than continuously tracking sequence numbers like full RFC
  3561 AODV.
- Sim-mode "unicast" is implemented as a stamped broadcast (every neighbor
  physically receives it, but only the intended next hop acts on it) since
  loopback has no true multicast-to-a-subset primitive; real hotspot mode
  uses genuine per-socket unicast.
- No message persistence/store-and-forward for nodes that are briefly
  disconnected — packets in flight during a partition are dropped, not
  queued.
