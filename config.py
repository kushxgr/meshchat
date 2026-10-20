"""
config.py
---------
Shared timing constants. Centralized so node.py and the routing
protocols (which need to agree on what "out of range" means) don't
have to import from each other.
"""

HELLO_INTERVAL = 1.0      # how often each node beacons its presence
KEYADV_INTERVAL = 5.0     # how often each node re-floods its public key
TICK_INTERVAL = 0.5       # background housekeeping loop period
DELIVERY_TTL = 30.0       # seconds to keep an unacknowledged message pending

# Missed ~2-3 HELLOs in a row => treat that neighbor as out of Wi-Fi
# range / the link as dead. This is what lets AODV-lite detect a
# broken route reactively instead of waiting for the full route
# lifetime to expire.
NEIGHBOR_TIMEOUT = 2.5
