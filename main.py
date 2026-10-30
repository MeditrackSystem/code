import tkinter as tk
from tkinter import scrolledtext, messagebox
import asyncio
import threading
import traceback
from bleak import BleakScanner, BleakClient

DEVICE_NAME = "ESP32-S3-RFID-Reader"
CHARACTERISTIC_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26a8"

class RFIDApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ESP32-S3 RFID BLE Reader")
        self.client = None
        self.reading = False
        self.thread = None

        tk.Button(root, text="Scan & Connect", command=self.start_connection).pack(pady=10)
        tk.Button(root, text="Disconnect", command=self.disconnect).pack(pady=5)

        self.status_label = tk.Label(root, text="Status: Idle", fg="gray")
        self.status_label.pack(pady=5)

        self.text_area = scrolledtext.ScrolledText(root, width=50, height=15, state='disabled')
        self.text_area.pack(pady=10)

    # ---- Thread-safe status updater ----
    def update_status(self, text, color="black"):
        self.root.after(0, lambda: self.status_label.config(text=text, fg=color))

    def log_uid(self, uid):
        def _update():
            self.text_area.config(state='normal')
            self.text_area.insert(tk.END, f"{uid}\n")
            self.text_area.see(tk.END)
            self.text_area.config(state='disabled')
        self.root.after(0, _update)

    # ---- Button handlers ----
    def start_connection(self):
        if self.thread and self.thread.is_alive():
            print("[GUI] Already connecting/reading, ignoring click.")
            return
        self.reading = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def disconnect(self):
        self.reading = False
        if self.client and self.client.is_connected:
            # schedule async disconnect on the loop thread
            asyncio.run_coroutine_threadsafe(self.client.disconnect(),
                                             self.loop)
        else:
            self.update_status("Status: Disconnected", "red")

    def _run(self):
        try:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(self.connect_and_listen())
        except Exception as e:
            print("[THREAD EXCEPTION]", e)
            traceback.print_exc()
            self.update_status(f"Thread error: {e}", "red")

    async def connect_and_listen(self):
        self.update_status("Status: Scanning...", "orange")
        try:
            device = await BleakScanner.find_device_by_name(DEVICE_NAME, timeout=10.0)
            if not device:
                self.update_status(
                    f"Device '{DEVICE_NAME}' not found. Is BT on?", "red")
                return

            self.update_status(f"Found {device.address}. Connecting...", "orange")
            async with BleakClient(device) as client:
                self.client = client
                self.update_status("Status: Connected", "green")

                def on_notify(sender, data):
                    try:
                        uid = data.decode("utf-8", errors="replace")
                        print(f"[BLE] UID: {uid}")
                        self.log_uid(uid)
                    except Exception as e:
                        print("notify err:", e)

                await client.start_notify(CHARACTERISTIC_UUID, on_notify)
                print("[BLE] Notifications enabled.")

                # Keep alive until user disconnects or BLE drops
                while self.reading and client.is_connected:
                    await asyncio.sleep(0.2)

                print("[BLE] Loop exited. reading =", self.reading,
                      "connected =", client.is_connected)
                try:
                    await client.stop_notify(CHARACTERISTIC_UUID)
                except Exception:
                    pass

        except Exception as e:
            print("[BLE ERROR]", e)
            traceback.print_exc()
            self.update_status(f"Error: {e}", "red")
        finally:
            self.client = None
            # Only set disconnected if we are not already showing a real error
            if self.status_label.cget("fg") != "red":
                self.update_status("Status: Disconnected", "red")


if __name__ == "__main__":
    root = tk.Tk()
    app = RFIDApp(root)
    root.mainloop()