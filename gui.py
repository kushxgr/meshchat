"""
gui.py
------
Minimal Tkinter chat window for one Node. Run one instance per
device (or per simulated node on localhost -- see run_local_demo.py).
"""

import tkinter as tk
from tkinter import scrolledtext
import queue
import time


class ChatGUI:
    def __init__(self, node, default_dst=None, master=None):
        self.node = node
        self._ui_queue = queue.Queue()  # cross-thread hand-off into Tk main loop

        # master=None -> this window owns the Tk event loop itself (normal single-node usage).
        # master=<a Tk root> -> this window is a Toplevel sharing someone else's mainloop
        # (used by run_local_demo.py to run several node windows in one process/one mainloop).
        self.root = tk.Toplevel(master) if master is not None else tk.Tk()
        self.root.title(f"Mesh Chat — {node.node_id} [{node.protocol_name}]")
        self.root.geometry("480x420")

        top = tk.Frame(self.root)
        top.pack(fill="x", padx=6, pady=4)
        tk.Label(top, text="To:").pack(side="left")
        self.dst_var = tk.StringVar(value=default_dst or "")
        tk.Entry(top, textvariable=self.dst_var, width=12).pack(side="left", padx=4)
        tk.Label(top, text=f"  my pubkey: {node.pub_key_b64[:16]}...").pack(side="left")

        self.log = scrolledtext.ScrolledText(self.root, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True, padx=6, pady=4)

        bottom = tk.Frame(self.root)
        bottom.pack(fill="x", padx=6, pady=4)
        self.entry = tk.Entry(bottom)
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", lambda e: self._send())
        tk.Button(bottom, text="Send", command=self._send).pack(side="left", padx=4)

        node.on_message(self._on_incoming)
        self.root.after(100, self._drain_queue)

    def _send(self):
        text = self.entry.get().strip()
        dst = self.dst_var.get().strip()
        if not text or not dst:
            return
        ok = self.node.send_chat(dst, text)
        self._append(f"me -> {dst}: {text}" if ok else f"[can't send -- no key for {dst} yet, waiting on KEYADV]")
        self.entry.delete(0, tk.END)

    def _on_incoming(self, src, text, meta):
        # called from a background thread -- hand off to the Tk thread
        self._ui_queue.put(f"{src}: {text}   ({meta['latency_ms']:.0f} ms)")

    def _drain_queue(self):
        while not self._ui_queue.empty():
            self._append(self._ui_queue.get())
        self.root.after(100, self._drain_queue)

    def _append(self, line):
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        self.log.configure(state="disabled")
        self.log.see("end")

    def start_node(self):
        """Start the underlying node's networking (call once per node)."""
        self.node.start()

    def run(self):
        """Standalone usage only (single node + owns the mainloop). For the
        multi-node-in-one-process runner, call start_node() on each GUI
        instead and drive a single shared event loop yourself (see
        run_local_demo.py, which uses the same update()-polling pattern
        below rather than mainloop() -- see the note there for why)."""
        self.start_node()
        try:
            while True:
                self.root.update_idletasks()
                self.root.update()
                time.sleep(0.01)
        except tk.TclError:
            pass  # window was closed
        finally:
            self.node.stop()
