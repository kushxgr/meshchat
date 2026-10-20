"""
app.py
------
Desktop launcher for the mesh chat demo.

This wraps the existing subprocess-backed local demo flow in a single
window so the app can be started, configured, and monitored without
typing command-line arguments. It launches one worker process per node
and opens a chat window for each node automatically.
"""

import ipaddress
import os
import re
import socket
import sys

if "--worker" in sys.argv:
    sys.argv.remove("--worker")
    from node_worker import main as _worker_main

    _worker_main()
    raise SystemExit(0)

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from run_local_demo import WorkerHandle, WorkerChatGUI


class MeshChatStudio:
    def __init__(self):
        self._base_dir = self._resource_dir()

        self.root = tk.Tk()
        self.root.title("Mesh Chat Studio")
        self.root.geometry("1180x760")
        self.root.minsize(1020, 680)
        self._set_window_icon(self.root)

        self._workers = {}
        self._windows = {}
        self._rows = {}
        self._running = False

        self._apply_theme()
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(100, self._poll)

    def _resource_dir(self):
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            return sys._MEIPASS
        return os.path.dirname(os.path.abspath(__file__))

    def _icon_path(self):
        return os.path.join(self._base_dir, "assets", "mesh_chat.ico")

    def _set_window_icon(self, window):
        icon_path = self._icon_path()
        if os.path.exists(icon_path):
            try:
                window.iconbitmap(icon_path)
            except tk.TclError:
                pass

    def _apply_theme(self):
        self.bg = "#0f172a"
        self.panel = "#111827"
        self.card = "#1f2937"
        self.text = "#e5e7eb"
        self.muted = "#94a3b8"
        self.accent = "#f59e0b"

        self.root.configure(bg=self.bg)
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("TFrame", background=self.bg)
        style.configure("Card.TFrame", background=self.card)
        style.configure("TLabel", background=self.bg, foreground=self.text)
        style.configure("Muted.TLabel", background=self.bg, foreground=self.muted)
        style.configure("CardTitle.TLabel", background=self.card, foreground=self.text, font=("Segoe UI", 13, "bold"))
        style.configure("CardBody.TLabel", background=self.card, foreground=self.muted)
        style.configure("TButton", padding=(12, 7))
        style.configure("Accent.TButton", background=self.accent, foreground="#111827", padding=(14, 8), font=("Segoe UI", 10, "bold"))
        style.map("Accent.TButton", background=[("active", "#fbbf24")])
        style.configure("Treeview", background=self.card, fieldbackground=self.card, foreground=self.text, rowheight=28, borderwidth=0)
        style.configure("Treeview.Heading", background=self.bg, foreground=self.text, font=("Segoe UI", 10, "bold"))
        style.map("Treeview", background=[("selected", "#334155")])

    def _build_ui(self):
        outer = ttk.Frame(self.root, padding=20)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 16))
        title = ttk.Label(header, text="Mesh Chat Studio", font=("Segoe UI", 22, "bold"))
        title.pack(anchor="w")
        subtitle = ttk.Label(
            header,
            text="Simulate a mesh locally or connect devices on the same Wi-Fi network or hotspot.",
            style="Muted.TLabel",
        )
        subtitle.pack(anchor="w", pady=(4, 0))

        body = ttk.Panedwindow(outer, orient=tk.HORIZONTAL)
        body.pack(fill="both", expand=True)

        self.left = ttk.Frame(body, style="Card.TFrame", padding=18)
        self.right = ttk.Frame(body, style="Card.TFrame", padding=18)
        body.add(self.left, weight=1)
        body.add(self.right, weight=2)

        self._build_launcher_panel(self.left)
        self._build_monitor_panel(self.right)

    def _build_launcher_panel(self, parent):
        ttk.Label(parent, text="Demo Launcher", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(
            parent,
            text="Run a multi-node simulation on this PC, or launch one network node for this device.",
            style="CardBody.TLabel",
            wraplength=320,
            justify="left",
        ).pack(anchor="w", pady=(6, 14))

        form = ttk.Frame(parent, style="Card.TFrame")
        form.pack(fill="x")

        device_id = re.sub(r"[^A-Za-z0-9_-]", "-", socket.gethostname()).strip("-") or "MeshNode"
        self.ids_var = tk.StringVar(value=device_id)
        self.protocol_var = tk.StringVar(value="flooding")
        self.topology_var = tk.StringVar(value=os.path.join(self._base_dir, "topology_chain3.json"))
        self.base_port_var = tk.StringVar(value="20000")
        self.mode_var = tk.StringVar(value="Wi-Fi / hotspot")
        self.broadcast_var = tk.StringVar(value="192.168.137.255")

        self._field(form, "Device node ID", self.ids_var, row=0)
        self._field(form, "Port", self.base_port_var, row=1)

        ttk.Label(form, text="Connection mode", style="CardBody.TLabel").grid(row=2, column=0, sticky="w", pady=(8, 2))
        mode_box = ttk.Combobox(form, textvariable=self.mode_var, values=("Local demo", "Wi-Fi / hotspot"), state="readonly", width=24)
        mode_box.grid(row=2, column=1, sticky="ew", pady=(8, 2))
        mode_box.bind("<<ComboboxSelected>>", self._update_mode_controls)

        ttk.Label(form, text="Wi-Fi broadcast", style="CardBody.TLabel").grid(row=3, column=0, sticky="w", pady=(8, 2))
        self.broadcast_entry = ttk.Entry(form, textvariable=self.broadcast_var)
        self.broadcast_entry.grid(row=3, column=1, sticky="ew", pady=(8, 2))

        ttk.Label(form, text="Routing protocol", style="CardBody.TLabel").grid(row=4, column=0, sticky="w", pady=(8, 2))
        protocol_box = ttk.Combobox(form, textvariable=self.protocol_var, values=("flooding", "aodv_lite"), state="readonly", width=24)
        protocol_box.grid(row=4, column=1, sticky="ew", pady=(8, 2))

        ttk.Label(form, text="Topology file", style="CardBody.TLabel").grid(row=5, column=0, sticky="w", pady=(8, 2))
        topo_row = ttk.Frame(form, style="Card.TFrame")
        topo_row.grid(row=5, column=1, sticky="ew", pady=(8, 2))
        topo_entry = ttk.Entry(topo_row, textvariable=self.topology_var)
        topo_entry.pack(side="left", fill="x", expand=True)
        self.topology_browse = ttk.Button(topo_row, text="Browse", command=self._browse_topology)
        self.topology_browse.pack(side="left", padx=(8, 0))

        form.columnconfigure(1, weight=1)

        button_row = ttk.Frame(parent, style="Card.TFrame")
        button_row.pack(fill="x", pady=(14, 8))
        ttk.Button(button_row, text="Use Chain 3", command=self._preset_chain).pack(side="left")
        ttk.Button(button_row, text="Use Ring 5", command=self._preset_ring).pack(side="left", padx=8)
        ttk.Button(button_row, text="Stop Demo", command=self.stop_demo).pack(side="right")

        ttk.Button(parent, text="Launch Demo", style="Accent.TButton", command=self.start_demo).pack(fill="x", pady=(6, 12))

        hint = ttk.Label(
            parent,
            text="Run this EXE on each Windows device. Keep each device ID unique; select a discovered peer in its chat window. Use the same port and broadcast on all devices; allow UDP through Windows Firewall.",
            style="CardBody.TLabel",
            wraplength=320,
            justify="left",
        )
        hint.pack(anchor="w", pady=(0, 12))

        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(parent, textvariable=self.status_var, style="CardBody.TLabel", wraplength=320, justify="left").pack(anchor="w")
        self._update_mode_controls()

    def _field(self, parent, label, variable, row):
        ttk.Label(parent, text=label, style="CardBody.TLabel").grid(row=row, column=0, sticky="w", pady=(8, 2))
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", pady=(8, 2))

    def _update_mode_controls(self, _event=None):
        hotspot = self.mode_var.get() == "Wi-Fi / hotspot"
        self.broadcast_entry.configure(state="normal" if hotspot else "disabled")
        self.topology_browse.configure(state="disabled" if hotspot else "normal")

    def _build_monitor_panel(self, parent):
        ttk.Label(parent, text="Network Monitor", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(
            parent,
            text="Live node status appears here. In Wi-Fi mode, each device runs one node and discovers peers by UDP broadcast.",
            style="CardBody.TLabel",
            wraplength=640,
            justify="left",
        ).pack(anchor="w", pady=(6, 14))

        tree_frame = ttk.Frame(parent, style="Card.TFrame")
        tree_frame.pack(fill="both", expand=True)
        columns = ("node", "port", "status", "pubkey")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=7)
        self.tree.heading("node", text="Node")
        self.tree.heading("port", text="Port")
        self.tree.heading("status", text="Status")
        self.tree.heading("pubkey", text="Pubkey")
        self.tree.column("node", width=90, anchor="center")
        self.tree.column("port", width=100, anchor="center")
        self.tree.column("status", width=120, anchor="center")
        self.tree.column("pubkey", width=260, anchor="w")
        self.tree.pack(fill="both", expand=True, side="left")

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        scrollbar.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scrollbar.set)

        log_label = ttk.Label(parent, text="Launcher Log", style="CardTitle.TLabel")
        log_label.pack(anchor="w", pady=(16, 6))
        self.log = tk.Text(parent, height=10, wrap="word", bg=self.card, fg=self.text, insertbackground=self.text, relief="flat", highlightthickness=0)
        self.log.pack(fill="x")
        self.log.configure(state="disabled")

    def _browse_topology(self):
        path = filedialog.askopenfilename(
            title="Choose topology JSON",
            initialdir=self._base_dir,
            filetypes=(("JSON files", "*.json"), ("All files", "*.*")),
        )
        if path:
            self.topology_var.set(path)

    def _preset_chain(self):
        self.mode_var.set("Local demo")
        self._update_mode_controls()
        self.ids_var.set("A,B,C")
        self.topology_var.set(os.path.join(self._base_dir, "topology_chain3.json"))

    def _preset_ring(self):
        self.mode_var.set("Local demo")
        self._update_mode_controls()
        self.ids_var.set("A,B,C,D,E")
        self.topology_var.set(os.path.join(self._base_dir, "topology_demo.json"))

    def _append_log(self, message):
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _set_row(self, node_id, port, status, pubkey=""):
        values = (node_id, str(port), status, pubkey)
        if node_id in self._rows:
            self.tree.item(self._rows[node_id], values=values)
        else:
            self._rows[node_id] = self.tree.insert("", "end", values=values)

    def _clear_rows(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._rows.clear()

    def start_demo(self):
        if self._running:
            self.stop_demo()

        node_ids = [part.strip() for part in self.ids_var.get().split(",") if part.strip()]
        hotspot = self.mode_var.get() == "Wi-Fi / hotspot"
        if len(node_ids) != len(set(node_ids)):
            messagebox.showerror("Invalid setup", "Node IDs must be unique.")
            return
        if hotspot and len(node_ids) != 1:
            messagebox.showerror("Invalid setup", "Wi-Fi / hotspot mode runs one node on this device. Enter one node ID.")
            return
        if not hotspot and len(node_ids) < 2:
            messagebox.showerror("Invalid setup", "Enter at least two node IDs for a local demo, for example A,B,C.")
            return

        try:
            base_port = int(self.base_port_var.get().strip())
            if not 1 <= base_port <= 65535 or base_port + len(node_ids) - 1 > 65535:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid setup", "Port must be between 1 and 65535, with room for every local node.")
            return

        if hotspot:
            try:
                broadcast_addr = str(ipaddress.IPv4Address(self.broadcast_var.get().strip()))
            except ipaddress.AddressValueError:
                messagebox.showerror("Invalid setup", "Enter a valid IPv4 broadcast address, for example 192.168.137.255.")
                return
            topology_path = None
        else:
            broadcast_addr = "255.255.255.255"
            topology_path = self.topology_var.get().strip()
            if topology_path:
                topology_path = os.path.abspath(topology_path)
                if not os.path.exists(topology_path):
                    messagebox.showerror("Invalid setup", f"Topology file not found:\n{topology_path}")
                    return
            else:
                topology_path = None

        protocol = self.protocol_var.get().strip()
        ports = {nid: base_port + i for i, nid in enumerate(node_ids)}
        all_ports = list(ports.values())
        mode = "hotspot" if hotspot else "sim"

        self._clear_rows()
        self._workers.clear()
        self._windows.clear()

        for index, nid in enumerate(node_ids):
            worker = WorkerHandle(
                nid, ports[nid], all_ports, protocol, topology_path,
                mode=mode, broadcast_addr=broadcast_addr,
            )
            default_dst = next((other for other in node_ids if other != nid), "")
            window = WorkerChatGUI(worker, master=self.root, default_dst=default_dst)
            self._set_window_icon(window.root)
            window.root.geometry(f"480x420+{80 + (index * 40)}+{80 + (index * 28)}")
            window.root.protocol("WM_DELETE_WINDOW", lambda node_id=nid: self._close_node(node_id))
            self._workers[nid] = worker
            self._windows[nid] = window
            self._set_row(nid, ports[nid], "starting")

        self._running = True
        if hotspot:
            self.status_var.set(f"Listening on Wi-Fi port {base_port}; use a unique node ID on each device.")
            self._append_log(f"Connected to Wi-Fi mode: node={node_ids[0]} port={base_port} broadcast={broadcast_addr} protocol={protocol}")
        else:
            self.status_var.set(f"Running {len(node_ids)} local nodes with {protocol}.")
            self._append_log(f"Launched local demo: nodes={','.join(node_ids)} protocol={protocol}")

    def _close_node(self, node_id):
        worker = self._workers.pop(node_id, None)
        window = self._windows.pop(node_id, None)
        if worker is not None:
            worker.quit()
        if window is not None and window.root.winfo_exists():
            try:
                window.root.destroy()
            except tk.TclError:
                pass
        self._set_row(node_id, self.tree.set(self._rows[node_id], "port") if node_id in self._rows else "", "stopped", self.tree.set(self._rows[node_id], "pubkey") if node_id in self._rows else "")
        self._append_log(f"Stopped node {node_id}")
        if not self._workers:
            self._running = False
            self.status_var.set("Ready.")

    def stop_demo(self):
        if not self._workers:
            self._running = False
            self.status_var.set("Ready.")
            return

        for node_id in list(self._workers.keys()):
            worker = self._workers.get(node_id)
            window = self._windows.get(node_id)
            if worker is not None:
                worker.quit()
            if window is not None and window.root.winfo_exists():
                try:
                    window.root.destroy()
                except tk.TclError:
                    pass
            self._set_row(node_id, self.tree.set(self._rows[node_id], "port") if node_id in self._rows else "", "stopped", self.tree.set(self._rows[node_id], "pubkey") if node_id in self._rows else "")

        self._workers.clear()
        self._windows.clear()
        self._running = False
        self.status_var.set("Ready.")
        self._append_log("Stopped all demo nodes.")

    def _poll(self):
        for node_id, window in list(self._windows.items()):
            worker = self._workers.get(node_id)
            if worker is None:
                continue
            if not window.root.winfo_exists():
                self._close_node(node_id)
                continue
            window.poll_events()
            status = "error" if worker.error else ("running" if worker.pubkey else "starting")
            pubkey = worker.pubkey[:16] + "..." if worker.pubkey else ""
            port = self.tree.set(self._rows[node_id], "port") if node_id in self._rows else ""
            self._set_row(node_id, port, status, pubkey)
            if worker.error:
                self.status_var.set(f"Node {node_id} failed: {worker.error}")
            if worker.pubkey and not getattr(worker, "_pubkey_logged", False):
                worker._pubkey_logged = True
                self._append_log(f"Node {node_id} ready: pubkey advertised.")
        self.root.after(100, self._poll)

    def close(self):
        self.stop_demo()
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def run(self):
        self.root.mainloop()


def main():
    MeshChatStudio().run()


if __name__ == "__main__":
    main()