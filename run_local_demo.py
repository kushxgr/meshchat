"""
run_local_demo.py
-------------------
Runs several mesh-chat chat windows, each backed by its OWN separate
node_worker.py subprocess (real UDP networking, real X25519/AES-256-
GCM encryption, real Flooding/AODV-lite routing -- the exact same
code that was proven reliable in headless testing).

The Tkinter GUI here does NOT touch sockets or networking threads at
all. It only spawns subprocesses and exchanges plain JSON lines with
them over stdin/stdout. This sidesteps a Windows-specific issue where
running Tkinter's event loop and the networking threads in the same
process silently prevented the networking threads from ever running.

Usage:
    python run_local_demo.py
    python run_local_demo.py --ids A,B,C --protocol aodv_lite --topology topology_chain3.json
    python run_local_demo.py --ids A,B,C,D,E --topology topology_demo.json
"""

import argparse
import os
import json
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import scrolledtext
import queue


class WorkerHandle:
    """One node_worker.py subprocess + the pipe I/O around it."""

    def __init__(self, node_id, port, all_ports, protocol, topology_path):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        if getattr(sys, "frozen", False):
            cmd = [
                sys.executable,
                "--worker",
                "--id", node_id, "--port", str(port),
                "--peers", ",".join(str(p) for p in all_ports),
                "--protocol", protocol,
            ]
        else:
            cmd = [
                sys.executable, os.path.join(script_dir, "node_worker.py"),
                "--id", node_id, "--port", str(port),
                "--peers", ",".join(str(p) for p in all_ports),
                "--protocol", protocol,
            ]
        if topology_path:
            cmd += ["--topology", topology_path]

        self.node_id = node_id
        self.proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            text=True, bufsize=1,
        )
        self.pubkey = None
        self.events = queue.Queue()
        threading.Thread(target=self._read_loop, daemon=True).start()

    def _read_loop(self):
        for line in self.proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("event") == "started":
                self.pubkey = obj["pubkey"]
            self.events.put(obj)

    def send(self, dst, text):
        self.proc.stdin.write(json.dumps({"cmd": "send", "dst": dst, "text": text}) + "\n")
        self.proc.stdin.flush()

    def quit(self):
        try:
            self.proc.stdin.write(json.dumps({"cmd": "quit"}) + "\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError):
            pass
        try:
            self.proc.terminate()
            self.proc.wait(timeout=2)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass


class WorkerChatGUI:
    """Same look-and-feel as gui.ChatGUI, but backed by a WorkerHandle
    (subprocess) instead of an in-process Node."""

    def __init__(self, worker: WorkerHandle, master, default_dst=None):
        self.worker = worker
        self.root = tk.Toplevel(master)
        self.root.title(f"Mesh Chat — {worker.node_id}")

        top = tk.Frame(self.root)
        top.pack(fill="x", padx=6, pady=4)
        tk.Label(top, text="To:").pack(side="left")
        self.dst_var = tk.StringVar(value=default_dst or "")
        tk.Entry(top, textvariable=self.dst_var, width=12).pack(side="left", padx=4)
        self.pubkey_label = tk.Label(top, text="my pubkey: (starting...)")
        self.pubkey_label.pack(side="left")

        self.log = scrolledtext.ScrolledText(self.root, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True, padx=6, pady=4)

        bottom = tk.Frame(self.root)
        bottom.pack(fill="x", padx=6, pady=4)
        self.entry = tk.Entry(bottom)
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", lambda e: self._send())
        tk.Button(bottom, text="Send", command=self._send).pack(side="left", padx=4)

    def _send(self):
        text = self.entry.get().strip()
        dst = self.dst_var.get().strip()
        if not text or not dst:
            return
        self.worker.send(dst, text)
        self._append(f"me -> {dst}: {text}")
        self.entry.delete(0, tk.END)

    def poll_events(self):
        """Call periodically from the GUI thread to drain this worker's
        event queue and update the window -- never touches sockets."""
        while not self.worker.events.empty():
            obj = self.worker.events.get()
            ev = obj.get("event")
            if ev == "started":
                self.pubkey_label.config(text=f"my pubkey: {obj['pubkey'][:16]}...")
            elif ev == "message":
                self._append(f"{obj['src']}: {obj['text']}   ({obj['latency_ms']:.0f} ms)")
            elif ev == "send_failed":
                self._append(f"[can't send -- no key for {obj['dst']} yet, waiting on KEYADV]")

    def _append(self, line):
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        self.log.configure(state="disabled")
        self.log.see("end")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="A,B,C", help="comma-separated node ids, e.g. A,B,C")
    ap.add_argument("--protocol", choices=["flooding", "aodv_lite"], default="flooding")
    ap.add_argument("--base-port", type=int, default=20000,
                     help="starting port number; avoid 6000-6002 (commonly reserved for X11/WSLg on Windows)")
    ap.add_argument("--topology", default=None, help="path to a topology.json; omit for fully connected")
    args = ap.parse_args()

    ids = [x.strip() for x in args.ids.split(",") if x.strip()]
    ports = {nid: args.base_port + i for i, nid in enumerate(ids)}
    all_ports = list(ports.values())

    root = tk.Tk()
    root.withdraw()

    windows = []
    x_offset = 0
    for nid in ids:
        worker = WorkerHandle(nid, ports[nid], all_ports, args.protocol, args.topology)
        default_dst = next((other for other in ids if other != nid), None)
        gui = WorkerChatGUI(worker, master=root, default_dst=default_dst)
        gui.root.geometry(f"480x420+{x_offset}+40")
        x_offset += 500
        windows.append(gui)

    print(f"Started {len(ids)} node worker process(es): {ids}  protocol={args.protocol}  "
          f"topology={'none (fully connected)' if not args.topology else args.topology}")
    print("Each node is a separate real subprocess -- close a window (or Ctrl+C here) to stop it.")

    def on_close(w):
        w.worker.quit()
        w.root.destroy()

    for gui in windows:
        gui.root.protocol("WM_DELETE_WINDOW", lambda w=gui: on_close(w))

    try:
        while any(w.root.winfo_exists() for w in windows):
            for w in windows:
                if w.root.winfo_exists():
                    w.poll_events()
            root.update_idletasks()
            root.update()
            time.sleep(0.03)
    except tk.TclError:
        pass
    finally:
        for w in windows:
            w.worker.quit()


if __name__ == "__main__":
    main()
