"""
metrics.py
----------
Lightweight CSV logger each Node writes to. Used afterward by
analyze_metrics.py to produce the Flooding vs AODV-lite comparison
(packet overhead, end-to-end latency, failure-recovery time).

Log rows (one CSV per node, in logs/):
    ts, node_id, protocol, event, msg_id, extra
        event in {tx_control, tx_data, rx_data, delivered,
                  route_broken, route_recovered, duplicate_dropped}
"""

import csv
import os
import time
import threading

LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")


class MetricsLogger:
    def __init__(self, node_id, protocol):
        os.makedirs(LOG_DIR, exist_ok=True)
        self.path = os.path.join(LOG_DIR, f"{node_id}_{protocol}.csv")
        self._lock = threading.Lock()
        self._fresh_file()
        self.node_id = node_id
        self.protocol = protocol

    def _fresh_file(self):
        with open(self.path, "w", newline="") as f:
            csv.writer(f).writerow(["ts", "node_id", "protocol", "event", "msg_id", "extra"])

    def log(self, event, msg_id="", extra=""):
        with self._lock:
            with open(self.path, "a", newline="") as f:
                csv.writer(f).writerow([time.time(), self.node_id, self.protocol, event, msg_id, extra])
