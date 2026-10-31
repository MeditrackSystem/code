#!/usr/bin/env python3
"""
MediTrack - Raspberry Pi RFID client (Bluetooth/BLE).

Connects to the ESP32-S3 RFID reader over BLE, looks up the scanned
RFID tag in the local CSV database, and shows the patient's record,
medications and photo. Scan events are appended to scan_logs/audit_logs
and (optionally) POSTed to a MediTrack Flask backend.

Dependencies (on Raspberry Pi OS):
    pip install bleak pillow requests

Run:
    python rpi_full.py
"""

import asyncio
import csv
import json
import os
import threading
import traceback
from datetime import datetime
from pathlib import Path

import tkinter as tk
from tkinter import ttk, scrolledtext

from PIL import Image, ImageTk

from bleak import BleakScanner, BleakClient

try:
    import requests
    HAS_REQUESTS = True
except Exception:
    HAS_REQUESTS = False

# ============================ CONFIG ============================
BASE_DIR = Path(__file__).resolve().parent
DB_DIR = BASE_DIR / "database"
IMG_DIR = BASE_DIR / "images"
LOG_DIR = BASE_DIR / "logs"

DEVICE_NAME = "ESP32-S3-RFID-Reader"
CHARACTERISTIC_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26a8"

# Optional: set MEDITRACK_SERVER=http://<host>:5000 to POST scan results
SERVER_URL = os.environ.get("MEDITRACK_SERVER", "").rstrip("/")

LOG_DIR.mkdir(exist_ok=True)
DB_DIR.mkdir(exist_ok=True)
IMG_DIR.mkdir(exist_ok=True)
# ===============================================================


# --------------------------- CSV helpers ---------------------------
def read_csv(name):
    path = DB_DIR / f"{name}.csv"
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def append_csv(name, row):
    path = DB_DIR / f"{name}.csv"
    if path.exists():
        with open(path, newline="", encoding="utf-8") as f:
            header = next(csv.reader(f))
    else:
        header = list(row.keys())
    values = [row.get(h, "") for h in header]
    with open(path, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(values)


def next_id(name):
    rows = read_csv(name)
    ids = [int(r["id"]) for r in rows if str(r.get("id", "")).isdigit()]
    return (max(ids) + 1) if ids else 1


def find_one(rows, **kwargs):
    for r in rows:
        if all(str(r.get(k, "")) == str(v) for k, v in kwargs.items()):
            return r
    return None


# --------------------------- Data access ---------------------------
def get_bundle(uid):
    """Return (bundle_dict, message) for a scanned tag UID."""
    tag = find_one(read_csv("rfid_tags"), tag_token=uid, status="Active")
    if not tag:
        return None, "Tag not found or inactive."

    patient = find_one(read_csv("patients"), id=tag["patient_id"])
    if not patient:
        return None, "Patient record not found for this tag."

    orders = [
        r for r in read_csv("medication_orders")
        if r["patient_id"] == patient["id"] and r["status"] == "Active"
    ]
    admins = read_csv("medication_administrations")
    by_order = {}
    for a in admins:
        by_order.setdefault(a["order_id"], []).append(a)

    meds = []
    for o in orders:
        history = by_order.get(o["id"], [])
        latest = history[-1] if history else None
        meds.append((o, latest))

    records = [
        r for r in read_csv("medical_records")
        if r["patient_id"] == patient["id"]
    ]

    return {
        "tag": tag,
        "patient": patient,
        "meds": meds,
        "records": records,
    }, "OK"


def log_scan(tag_id, user_id, reader_type, outcome):
    append_csv("scan_logs", {
        "id": next_id("scan_logs"),
        "tag_id": tag_id,
        "user_id": user_id,
        "reader_type": reader_type,
        "scanned_at": datetime.now().isoformat(timespec="seconds"),
        "outcome": outcome,
    })


def log_audit(user_id, action, record_type, record_id):
    append_csv("audit_logs", {
        "id": next_id("audit_logs"),
        "user_id": user_id,
        "action": action,
        "record_type": record_type,
        "record_id": record_id,
        "occurred_at": datetime.now().isoformat(timespec="seconds"),
    })


def save_uid(uid):
    try:
        with open(LOG_DIR / "uids.log", "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()}  {uid}\n")
    except Exception as e:
        print("log write failed:", e)


# --------------------------- GUI app ---------------------------
class MediTrackApp:
    def __init__(self, root):
        self.root = root
        self.root.title("MediTrack - RFID Patient Lookup")
        self.root.geometry("980x640")
        self.root.resizable(False, False)

        self.client = None
        self.reading = False
        self.scanning = False
        self.loop = None
        self.thread = None
        self.current_photo = None

        self.users = read_csv("users")
        self.user_map = {f"{u['name']} ({u['role']})": u["id"] for u in self.users}
        self.current_user_var = tk.StringVar(
            value=next(iter(self.user_map)) if self.user_map else ""
        )

        self._build_ui()
        self._show_placeholder_photo()

    # ---------------- UI ----------------
    def _build_ui(self):
        # Top bar
        top = tk.Frame(self.root)
        top.pack(fill="x", padx=10, pady=(10, 4))

        tk.Label(top, text="MediTrack RFID", font=("Helvetica", 16, "bold")).pack(side="left")

        user_frame = tk.Frame(top)
        user_frame.pack(side="right")
        tk.Label(user_frame, text="Logged-in user:").pack(side="left", padx=(0, 4))
        self.user_combo = ttk.Combobox(
            user_frame, textvariable=self.current_user_var,
            values=list(self.user_map.keys()), state="readonly", width=34
        )
        self.user_combo.pack(side="left")

        # Buttons
        btns = tk.Frame(self.root)
        btns.pack(pady=6)
        self.connect_btn = tk.Button(
            btns, text="Scan & Connect", width=16, bg="#2ecc71", fg="white",
            command=self.start_connection)
        self.connect_btn.grid(row=0, column=0, padx=3)
        self.test_btn = tk.Button(
            btns, text="Test Scan", width=12, bg="#3498db", fg="white",
            command=self.start_test_scan)
        self.test_btn.grid(row=0, column=1, padx=3)
        self.disconnect_btn = tk.Button(
            btns, text="Disconnect", width=12, bg="#e74c3c", fg="white",
            command=self.disconnect, state="disabled")
        self.disconnect_btn.grid(row=0, column=2, padx=3)

        self.status_label = tk.Label(
            self.root, text="Status: Idle", fg="gray", font=("Helvetica", 11))
        self.status_label.pack(pady=4)

        # Main content: left info, right log
        content = tk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        content.pack(fill="both", expand=True, padx=10, pady=6)

        left = tk.Frame(content, bd=1, relief="groove")
        right = tk.Frame(content, bd=1, relief="groove")
        content.add(left, minsize=620)
        content.add(right, minsize=340)

        # --- Left: patient info ---
        tk.Label(left, text="Patient Information", font=("Helvetica", 12, "bold")).pack(anchor="w", padx=8, pady=(6, 2))

        info = tk.Frame(left)
        info.pack(fill="x", padx=8, pady=4)

        self.photo_label = tk.Label(info, text="No photo", width=24, height=12,
                                   bg="#ecf0f1", relief="sunken")
        self.photo_label.grid(row=0, column=0, rowspan=6, padx=(0, 12), pady=4, sticky="n")

        fields = tk.Frame(info)
        fields.grid(row=0, column=1, sticky="nw")

        self.vars = {
            "name": tk.StringVar(value="-"),
            "patient_id": tk.StringVar(value="-"),
            "room_bed": tk.StringVar(value="-"),
            "physician": tk.StringVar(value="-"),
            "rfid_status": tk.StringVar(value="-"),
            "birth_date": tk.StringVar(value="-"),
        }
        labels = [
            ("Name:", "name"),
            ("Patient ID:", "patient_id"),
            ("Room / Bed:", "room_bed"),
            ("Attending physician:", "physician"),
            ("RFID status:", "rfid_status"),
            ("Birth date:", "birth_date"),
        ]
        for i, (txt, key) in enumerate(labels):
            tk.Label(fields, text=txt, font=("Helvetica", 10, "bold")).grid(row=i, column=0, sticky="w", pady=2)
            tk.Label(fields, textvariable=self.vars[key], font=("Helvetica", 10)).grid(row=i, column=1, sticky="w", pady=2, padx=(6, 0))

        # Medications
        tk.Label(left, text="Medications", font=("Helvetica", 12, "bold")).pack(anchor="w", padx=8, pady=(8, 2))
        self.meds_text = scrolledtext.ScrolledText(left, height=8, width=74, state="disabled", font=("Courier", 9))
        self.meds_text.pack(padx=8, pady=4, fill="x")

        # Clinical notes / records
        tk.Label(left, text="Clinical records", font=("Helvetica", 12, "bold")).pack(anchor="w", padx=8, pady=(8, 2))
        self.records_text = scrolledtext.ScrolledText(left, height=6, width=74, state="disabled", font=("Courier", 9))
        self.records_text.pack(padx=8, pady=4, fill="x")

        # --- Right: log ---
        tk.Label(right, text="Activity log", font=("Helvetica", 12, "bold")).pack(anchor="w", padx=8, pady=(6, 2))
        self.text_area = scrolledtext.ScrolledText(right, width=46, height=34, state="disabled", font=("Courier", 9))
        self.text_area.pack(padx=8, pady=4, fill="both", expand=True)

        self.log("Ready. Press 'Test Scan' or 'Scan & Connect'.")

    def _show_placeholder_photo(self):
        self.photo_label.config(image="", text="No photo")

    def show_photo(self, patient_id):
        path = None
        for ext in (".jpg", ".jpeg", ".png"):
            cand = IMG_DIR / f"patient_{patient_id}{ext}"
            if cand.exists():
                path = cand
                break
        if path is None:
            self.photo_label.config(image="", text="No photo")
            self.current_photo = None
            return
        try:
            img = Image.open(path)
            img = img.resize((150, 150))
            self.current_photo = ImageTk.PhotoImage(img)
            self.photo_label.config(image=self.current_photo, text="")
        except Exception as e:
            self.photo_label.config(image="", text="Photo error")
            self.log(f"Photo load error: {e}")

    # ---------------- thread-safe UI ----------------
    def update_status(self, text, color="black"):
        self.root.after(0, lambda: self.status_label.config(text=text, fg=color))

    def log(self, msg):
        line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"

        def _do():
            self.text_area.config(state="normal")
            self.text_area.insert(tk.END, line + "\n")
            self.text_area.see(tk.END)
            self.text_area.config(state="disabled")
        self.root.after(0, _do)
        print(line)

    def set_text(self, widget, text):
        def _do():
            widget.config(state="normal")
            widget.delete("1.0", tk.END)
            widget.insert(tk.END, text)
            widget.config(state="disabled")
        self.root.after(0, _do)

    def set_buttons(self, connected=False, busy=False):
        def _do():
            state = "disabled" if (connected or busy) else "normal"
            self.connect_btn.config(state=state)
            self.test_btn.config(state=state)
            self.disconnect_btn.config(state="normal" if connected else "disabled")
        self.root.after(0, _do)

    def current_user_id(self):
        return self.user_map.get(self.current_user_var.get(), "")

    # ---------------- button handlers ----------------
    def start_connection(self):
        if self.reading or self.scanning:
            return
        self.reading = True
        self.set_buttons(connected=False, busy=True)
        self.thread = threading.Thread(target=self._run, args=(self._connect_flow,), daemon=True)
        self.thread.start()

    def start_test_scan(self):
        if self.reading or self.scanning:
            return
        self.scanning = True
        self.set_buttons(connected=False, busy=True)
        self.thread = threading.Thread(target=self._run, args=(self._test_flow,), daemon=True)
        self.thread.start()

    def disconnect(self):
        self.reading = False
        self.update_status("Status: Disconnecting...", "orange")
        if self.client and self.client.is_connected and self.loop:
            asyncio.run_coroutine_threadsafe(self.client.disconnect(), self.loop)

    # ---------------- async runners ----------------
    def _run(self, coro_func):
        try:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(coro_func())
        except Exception as e:
            print("[THREAD]", e)
            traceback.print_exc()
            self.log(f"THREAD ERROR: {e}")
            self.update_status(f"Error: {e}", "red")
        finally:
            self.reading = False
            self.scanning = False
            self.set_buttons(connected=False, busy=False)

    async def _scan_devices(self, timeout=10.0):
        return await BleakScanner.discover(timeout=timeout, return_adv=True)

    async def _test_flow(self):
        self.update_status("Status: Test scanning...", "orange")
        self.log(f"Scanning for {10}s (active mode)...")
        try:
            devices = await self._scan_devices(timeout=10.0)
        except Exception as e:
            self.update_status("Status: Scan error", "red")
            self.log(f"Scan failed: {e}")
            return

        if not devices:
            self.update_status("Status: No devices found", "red")
            self.log("No BLE devices found. Check Bluetooth and ESP32 power.")
            return

        self.log(f"Found {len(devices)} device(s):")
        target_found = False
        for device, adv in devices.values():
            name = device.name or "(unnamed)"
            mark = "  <-- TARGET" if name == DEVICE_NAME else ""
            self.log(f"  {name} [{device.address}] rssi={adv.rssi}{mark}")
            if name == DEVICE_NAME:
                target_found = True

        if target_found:
            self.update_status("Status: Target visible", "green")
            self.log(f"'{DEVICE_NAME}' is visible. Press 'Scan & Connect'.")
        else:
            self.update_status("Status: Target not found", "red")
            self.log(f"'{DEVICE_NAME}' not in list. Check ESP32 serial monitor.")

    async def _connect_flow(self):
        self.update_status("Status: Scanning...", "orange")
        self.log("Scanning for target device...")
        try:
            devices = await self._scan_devices(timeout=10.0)
        except Exception as e:
            self.update_status("Status: Scan error", "red")
            self.log(f"Scan failed: {e}")
            return

        target = next((d for d, _ in devices.values() if d.name == DEVICE_NAME), None)
        if not target:
            self.update_status("Status: Device not found", "red")
            self.log(f"'{DEVICE_NAME}' not found. Try 'Test Scan' first.")
            return

        self.update_status(f"Found {target.address}. Connecting...", "orange")
        self.log(f"Connecting to {target.address} ...")

        try:
            async with BleakClient(target, timeout=15.0) as client:
                self.client = client
                self.update_status("Status: Connected", "green")
                self.log("[OK] Connected. Waiting for card taps...")
                self.set_buttons(connected=True, busy=False)

                def on_notify(_sender, data: bytearray):
                    try:
                        uid = data.decode("utf-8", errors="replace").strip()
                        if uid:
                            self.root.after(0, lambda u=uid: self.handle_uid(u))
                    except Exception as e:
                        print("notify err:", e)

                await client.start_notify(CHARACTERISTIC_UUID, on_notify)
                self.log("Notifications enabled.")

                while self.reading and client.is_connected:
                    await asyncio.sleep(0.2)

                self.log("Stopping notifications...")
                try:
                    await client.stop_notify(CHARACTERISTIC_UUID)
                except Exception:
                    pass

        except Exception as e:
            print("[BLE ERROR]", e)
            traceback.print_exc()
            self.update_status(f"Error: {e}", "red")
            self.log(f"BLE error: {e}")
        finally:
            self.client = None
            self.reading = False
            self.update_status("Status: Disconnected", "red")
            self.log("Disconnected.")

    # ---------------- scan handling ----------------
    def handle_uid(self, uid):
        self.log(f"UID: {uid}")
        save_uid(uid)
        user_id = self.current_user_id()

        bundle, msg = get_bundle(uid)
        if bundle is None:
            self.update_status("Tag not recognized", "red")
            self.log(msg)
            log_scan("", user_id, "Bluetooth", "Unknown tag")
            messagebox.showwarning("Unknown tag", msg)
            return

        p = bundle["patient"]
        tag = bundle["tag"]
        self.vars["name"].set(p["name"])
        self.vars["patient_id"].set(p["patient_code"])
        self.vars["room_bed"].set(f"{p['room']} / {p['bed']}")
        self.vars["physician"].set(p["attending_physician"])
        self.vars["rfid_status"].set(tag["status"])
        self.vars["birth_date"].set(p["birth_date"])

        self.show_photo(p["id"])

        # medications
        lines = []
        for order, admin in bundle["meds"]:
            status = admin["status"] if admin else "No administration record"
            admin_time = admin["administered_at"] if admin and admin["administered_at"] else "-"
            lines.append(
                f"{order['medication']} ({order['dose']}, {order['route']})\n"
                f"  Schedule: {order['frequency']}\n"
                f"  Status: {status} | Administered: {admin_time}\n"
            )
        self.set_text(self.meds_text, "\n".join(lines) if lines else "No active medication orders.")

        # clinical records
        rlines = [f"[{r['record_type']}] {r['note']} ({r['recorded_at']})" for r in bundle["records"]]
        self.set_text(self.records_text, "\n".join(rlines) if rlines else "No clinical records.")

        self.update_status("Patient loaded", "green")
        self.log(f"Loaded patient: {p['name']} ({p['patient_code']})")

        log_scan(tag["id"], user_id, "Bluetooth", "Success")
        log_audit(user_id, "SCAN", "rfid_tag", tag["id"])
        log_audit(user_id, "VIEW", "patient", p["id"])

        self.post_result(bundle, uid)

    def post_result(self, bundle, uid):
        if not SERVER_URL:
            self.log("Server not configured (MEDITRACK_SERVER). Skipped POST.")
            return
        if not HAS_REQUESTS:
            self.log("requests not installed. Skipped POST.")
            return
        p = bundle["patient"]
        tag = bundle["tag"]
        payload = {
            "uid": uid,
            "tag_id": tag["id"],
            "patient_code": p["patient_code"],
            "name": p["name"],
            "room": p["room"],
            "bed": p["bed"],
            "physician": p["attending_physician"],
            "user_id": self.current_user_id(),
            "scanned_at": datetime.now().isoformat(timespec="seconds"),
        }
        try:
            r = requests.post(f"{SERVER_URL}/api/scan", json=payload, timeout=5)
            self.log(f"POST /api/scan -> {r.status_code}")
        except Exception as e:
            self.log(f"POST failed: {e}")


if __name__ == "__main__":
    root = tk.Tk()
    app = MediTrackApp(root)
    root.mainloop()
PY