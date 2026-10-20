"""
routing/base.py
----------------
Common interface both routing protocols implement. A Node holds one
RoutingProtocol instance and delegates all packet handling / sending
to it, so Flooding and AODV-lite are fully interchangeable and can be
benchmarked head-to-head under identical topology/crypto conditions.
"""


class RoutingProtocol:
    name = "base"

    def __init__(self, node):
        self.node = node          # back-reference to the owning Node
        self.seen = set()         # msg_ids already processed (loop/dup prevention)

    def already_seen(self, msg_id: str) -> bool:
        if msg_id in self.seen:
            return True
        self.seen.add(msg_id)
        return False

    # --- interface every protocol must implement ---
    def send_data(self, dst: str, encrypted_payload: str, msg_id: str,
                  delivery_id: str = None):
        raise NotImplementedError

    def handle_packet(self, pkt: dict, addr):
        raise NotImplementedError

    def cancel_pending_delivery(self, delivery_id: str):
        """Cancel a message that expired before a queued route became available."""

    def tick(self):
        """Called periodically (e.g. every 1s) for timers/beacons/route expiry."""
        pass
