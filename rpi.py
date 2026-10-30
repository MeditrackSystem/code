#!/usr/bin/env python3
"""
meditrack.py — All-in-one RFID BLE reader for Raspberry Pi.

Connects to ESP32-S3-RFID-Reader over BLE and displays received UIDs.
Uses ACTIVE scanning (compatible with all BlueZ versions).

Run:  python meditrack.py
"""

import tkinter as tk
from tkinter import scrolledtext
import asyncio
import threading
import traceback
from datetime import datetime
from pathlib import Path

from bleak import BleakScanner, BleakClient

# ======================= CONFIG =======================
DEVICE_NAME = "ESP32-S3-RFID-Reader"
CHARACTERISTIC_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26a8"
LOG_DIR = Path(__file__).parent / "logs"
# ======================================================


class RFIDApp:
    def __init__(self, root):
        self.root = root
        self.root.title("MediTrack — RFID Reader")
        self.root.geometry("560x520")
        self.root.resizable(False, False)

        self.client = None
        self.reading = False
        self.scanning = False
        self.loop = None
        self.thread = None

        # ---------------- UI ----------------
        tk.Label(root, text="MediTrack RFID",
                 font=("Helvetica", 16, "bold")).pack(pady=(10, 4))

        buttons = tk.Frame(root)
        buttons.pack(pady=8)

        self.connect_btn = tk.Button(
            buttons, text="Scan & Connect", width=15, bg="#2ecc71",
            fg="white", command=self.start_connection)
        self.connect_btn.grid(row=0, column=0, padx=3)

        self.test_btn = tk.Button(
            buttons, text="Test Scan", width=12, bg="#3498db",
            fg="white", command=self.start_test_scan)
        self.test_btn.grid(row=0, column=1, padx=3)

        self.disconnect_btn = tk.Button(
            buttons, text="Disconnect", width=12, bg="#e74c3c",
            fg="white", command=self.disconnect, state="disabled")
        self.disconnect_btn.grid(row=0, column=2, padx=3)

        self.status_label = tk.Label(root, text="Status: Idle",
                                     fg="gray", font=("Helvetica", 11))
        self.status_label.pack(pady=6)

        tk.Label(root, text="Output:", anchor="w").pack(
            fill="x", padx=10, pady=(4, 0))

        self.text_area = scrolledtext.ScrolledText(
            root, width=66, height=20, state="disabled",
            font=("Courier", 10))
        self.text_area.pack(padx=10, pady=6)

        LOG_DIR.mkdir(exist_ok=True)
        self.log_text("Ready. Press 'Test Scan' to check the ESP32 is visible, "
                      "or 'Scan & Connect' to connect.")

    # ---------- thread-safe UI ----------
    def update_status(self, text, color="black"):
        self.root.after(0, lambda: self.status_label.config(text=text, fg=color))

    def log_text(self, msg):
        line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"

        def _do():
            self.text_area.config(state="normal")
            self.text_area.insert(tk.END, line + "\n")
            self.text_area.see(tk.END)
            self.text_area.config(state="disabled")
        self.root.after(0, _do)
        print(line)

    def save_uid(self, uid):
        try:
            with open(LOG_DIR / "uids.log", "a") as f:
                f.write(f"{datetime.now().isoformat()}  {uid}\n")
        except Exception as e:
            print("log write failed:", e)

    def set_buttons(self, connected=False, busy=False):
        def _do():
            state = "disabled" if (connected or busy) else "normal"
            self.connect_btn.config(state=state)
            self.test_btn.config(state=state)
            self.disconnect_btn.config(
                state="normal" if connected else "disabled")
        self.root.after(0, _do)

    # ---------- button handlers ----------
    def start_connection(self):
        if self.reading or self.scanning:
            return
        self.reading = True
        self.set_buttons(connected=False, busy=True)
        self.thread = threading.Thread(
            target=self._run, args=(self._connect_flow,), daemon=True)
        self.thread.start()

    def start_test_scan(self):
        if self.reading or self.scanning:
            return
        self.scanning = True
        self.set_buttons(connected=False, busy=True)
        self.thread = threading.Thread(
            target=self._run, args=(self._test_flow,), daemon=True)
        self.thread.start()

    def disconnect(self):
        self.reading = False
        self.update_status("Status: Disconnecting...", "orange")
        if self.client and self.client.is_connected and self.loop:
            asyncio.run_coroutine_threadsafe(
                self.client.disconnect(), self.loop)

    # ---------- async runners ----------
    def _run(self, coro_func):
        try:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(coro_func())
        except Exception as e:
            print("[THREAD]", e)
            traceback.print_exc()
            self.log_text(f"THREAD ERROR: {e}")
            self.update_status(f"Error: {e}", "red")
        finally:
            self.reading = False
            self.scanning = False
            self.set_buttons(connected=False, busy=False)

    async def _scan_devices(self, timeout=10.0):
        """Active scan; returns dict of {address: (device, adv)}."""
        return await BleakScanner.discover(
            timeout=timeout,
            return_adv=True,
        )

    async def _test_flow(self):
        self.update_status("Status: Test scanning...", "orange")
        self.log_text(f"Scanning for {10}s (active mode)...")

        try:
            devices = await self._scan_devices(timeout=10.0)
        except Exception as e:
            self.update_status("Status: Scan error", "red")
            self.log_text(f"Scan failed: {e}")
            return

        if not devices:
            self.update_status("Status: No devices found", "red")
            self.log_text("No BLE devices at all. Check:")
            self.log_text("  - Bluetooth ON? (rfkill list)")
            self.log_text("  - ESP32 powered & in range?")
            return

        self.log_text(f"Found {len(devices)} device(s):")
        target_found = False
        for device, adv in devices.values():
            name = device.name or "(unnamed)"
            mark = "  <-- TARGET [OK]" if name == DEVICE_NAME else ""
            self.log_text(
                f"  {name}  [{device.address}]  rssi={adv.rssi}{mark}")
            if name == DEVICE_NAME:
                target_found = True

        if target_found:
            self.update_status("Status: Target visible", "green")
            self.log_text(
                f"[OK] '{DEVICE_NAME}' is visible. Press 'Scan & Connect'.")
        else:
            self.update_status("Status: Target not found", "red")
            self.log_text(
                f"[!] '{DEVICE_NAME}' not in list. Check ESP32 serial monitor.")

    async def _connect_flow(self):
        self.update_status("Status: Scanning...", "orange")
        self.log_text("Scanning for target device...")

        try:
            devices = await self._scan_devices(timeout=10.0)
        except Exception as e:
            self.update_status("Status: Scan error", "red")
            self.log_text(f"Scan failed: {e}")
            return

        target = next(
            (d for d, _ in devices.values() if d.name == DEVICE_NAME),
            None)

        if not target:
            self.update_status("Status: Device not found", "red")
            self.log_text(
                f"[!] '{DEVICE_NAME}' not found. Try 'Test Scan' first.")
            return

        self.update_status(f"Found {target.address}. Connecting...", "orange")
        self.log_text(f"Connecting to {target.address} ...")

        try:
            async with BleakClient(target, timeout=15.0) as client:
                self.client = client
                self.update_status("Status: Connected", "green")
                self.log_text("[OK] Connected. Waiting for card taps...")
                self.set_buttons(connected=True, busy=False)

                def on_notify(_sender, data: bytearray):
                    try:
                        uid = data.decode("utf-8", errors="replace").strip()
                        if uid:
                            self.log_text(f"UID: {uid}")
                            self.save_uid(uid)
                    except Exception as e:
                        print("notify err:", e)

                await client.start_notify(CHARACTERISTIC_UUID, on_notify)
                self.log_text("Notifications enabled.")

                while self.reading and client.is_connected:
                    await asyncio.sleep(0.2)

                self.log_text("Stopping notifications...")
                try:
                    await client.stop_notify(CHARACTERISTIC_UUID)
                except Exception:
                    pass

        except Exception as e:
            print("[BLE ERROR]", e)
            traceback.print_exc()
            self.update_status(f"Error: {e}", "red")
            self.log_text(f"BLE error: {e}")
        finally:
            self.client = None
            self.reading = False
            self.update_status("Status: Disconnected", "red")
            self.log_text("Disconnected.")


if __name__ == "__main__":
    root = tk.Tk()
    app = RFIDApp(root)
    root.mainloop()