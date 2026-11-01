#!/usr/bin/env python3
"""
MediTrack - Raspberry Pi RFID dashboard (PyQt5).

Supports two reader modes:
  * Bluetooth/BLE (ESP32-S3-RFID-Reader)
  * USB/Serial RFID reader (keyboard/serial wedge)

On scan, looks up the tag in the local CSV database and shows the patient's
record, medications and photo. Scan events are logged to CSV and optionally
POSTed to a MediTrack Flask backend.

Dependencies:
    pip install PyQt5 pillow bleak pyserial requests

Run:
    python rpi_full.py
"""

import asyncio
import csv
import os
import threading
import traceback
from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import Qt, QThread, pyqtSignal, QEvent, QTimer
from PyQt5.QtGui import QFont, QPixmap, QColor
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QLineEdit, QTextEdit, QFrame,
    QScrollArea, QMessageBox, QFileDialog, QSizePolicy, QDialog,
    QDialogButtonBox, QFormLayout, QCheckBox, QStackedWidget,
    QGraphicsDropShadowEffect
)
import hashlib

from PIL import Image, ImageQt

BASE_DIR = Path(__file__).resolve().parent
DB_DIR = BASE_DIR / "database"
IMG_DIR = BASE_DIR / "images"
LOG_DIR = BASE_DIR / "logs"

DEVICE_NAME = "ESP32-S3-RFID-Reader"
CHARACTERISTIC_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26a8"
SERVER_URL = os.environ.get("MEDITRACK_SERVER", "").rstrip("/")

LOG_DIR.mkdir(exist_ok=True)
DB_DIR.mkdir(exist_ok=True)
IMG_DIR.mkdir(exist_ok=True)

# Optional dependencies
try:
    from bleak import BleakScanner, BleakClient
    HAS_BLE = True
except Exception:
    HAS_BLE = False

try:
    import serial
    import serial.tools.list_ports
    HAS_SERIAL = True
except Exception:
    HAS_SERIAL = False

try:
    import requests
    HAS_REQUESTS = True
except Exception:
    HAS_REQUESTS = False


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


def get_bundle(uid):
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

    records = [r for r in read_csv("medical_records") if r["patient_id"] == patient["id"]]
    return {"tag": tag, "patient": patient, "meds": meds, "records": records}, "OK"


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


# --------------------------- Worker threads ---------------------------
class BleWorker(QThread):
    status = pyqtSignal(str)
    log = pyqtSignal(str)
    uid = pyqtSignal(str)

    def __init__(self, test_mode=False, parent=None):
        super().__init__(parent)
        self.test_mode = test_mode
        self.running = True
        self.client = None

    def stop(self):
        self.running = False

    def run(self):
        if not HAS_BLE:
            self.log.emit("bleak not installed. Install with: pip install bleak")
            return
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            if self.test_mode:
                loop.run_until_complete(self._test())
            else:
                loop.run_until_complete(self._connect())
        except Exception as e:
            self.log.emit(f"BLE error: {e}")
        finally:
            loop.close()

    async def _test(self):
        self.status.emit("Test scanning...")
        self.log.emit("Scanning for 10s (active mode)...")
        try:
            devices = await BleakScanner.discover(timeout=10.0, return_adv=True)
        except Exception as e:
            self.status.emit("Scan error")
            self.log.emit(f"Scan failed: {e}")
            return
        if not devices:
            self.status.emit("No devices found")
            self.log.emit("No BLE devices found.")
            return
        target_found = False
        for device, adv in devices.values():
            name = device.name or "(unnamed)"
            self.log.emit(f"  {name} [{device.address}] rssi={adv.rssi}")
            if name == DEVICE_NAME:
                target_found = True
        if target_found:
            self.status.emit("Target visible")
            self.log.emit(f"'{DEVICE_NAME}' is visible.")
        else:
            self.status.emit("Target not found")
            self.log.emit(f"'{DEVICE_NAME}' not in list.")

    async def _connect(self):
        self.status.emit("Scanning...")
        self.log.emit("Scanning for target device...")
        try:
            devices = await BleakScanner.discover(timeout=10.0, return_adv=True)
        except Exception as e:
            self.status.emit("Scan error")
            self.log.emit(f"Scan failed: {e}")
            return

        target = next((d for d, _ in devices.values() if d.name == DEVICE_NAME), None)
        if not target:
            self.status.emit("Device not found")
            self.log.emit(f"'{DEVICE_NAME}' not found. Try Test Scan first.")
            return

        self.status.emit(f"Connecting to {target.address}...")
        self.log.emit(f"Connecting to {target.address} ...")
        try:
            async with BleakClient(target, timeout=15.0) as client:
                self.client = client
                self.status.emit("Connected")
                self.log.emit("[OK] Connected. Waiting for card taps...")

                def on_notify(_sender, data: bytearray):
                    try:
                        uid = data.decode("utf-8", errors="replace").strip()
                        if uid:
                            self.uid.emit(uid)
                    except Exception as e:
                        self.log.emit(f"notify err: {e}")

                await client.start_notify(CHARACTERISTIC_UUID, on_notify)
                self.log.emit("Notifications enabled.")

                while self.running and client.is_connected:
                    await asyncio.sleep(0.2)

                self.log.emit("Stopping notifications...")
                try:
                    await client.stop_notify(CHARACTERISTIC_UUID)
                except Exception:
                    pass
        except Exception as e:
            self.status.emit(f"Error: {e}")
            self.log.emit(f"BLE error: {e}")
        finally:
            self.client = None
            self.status.emit("Disconnected")
            self.log.emit("Disconnected.")


class SerialWorker(QThread):
    status = pyqtSignal(str)
    log = pyqtSignal(str)
    uid = pyqtSignal(str)

    def __init__(self, port, baud=9600, parent=None):
        super().__init__(parent)
        self.port = port
        self.baud = baud
        self.running = True
        self.ser = None

    def stop(self):
        self.running = False

    def run(self):
        if not HAS_SERIAL:
            self.log.emit("pyserial not installed. Install with: pip install pyserial")
            return
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=1)
        except Exception as e:
            self.status.emit("Serial error")
            self.log.emit(f"Cannot open {self.port}: {e}")
            return

        self.status.emit(f"Connected {self.port}")
        self.log.emit(f"[OK] Serial connected: {self.port} @ {self.baud}")
        while self.running:
            try:
                line = self.ser.readline().decode("utf-8", errors="replace").strip()
                if line:
                    self.uid.emit(line)
            except Exception as e:
                self.log.emit(f"Serial read error: {e}")
                break
        try:
            self.ser.close()
        except Exception:
            pass
        self.status.emit("Disconnected")
        self.log.emit("Serial disconnected.")


# --------------------------- UI helpers ---------------------------
def card_frame():
    f = QFrame()
    f.setObjectName("card")
    f.setStyleSheet("""
        QFrame#card {
            background: white;
            border: 1px solid #e5e7eb;
            border-radius: 16px;
        }
    """)
    shadow = QGraphicsDropShadowEffect()
    shadow.setBlurRadius(24)
    shadow.setOffset(0, 6)
    shadow.setColor(QColor(0, 0, 0, 35))
    f.setGraphicsEffect(shadow)
    return f


# --------------------------- Login dialog ---------------------------
class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("MediTrack Login")
        self.setModal(True)
        self.resize(360, 200)
        self.user = None

        layout = QVBoxLayout(self)
        title = QLabel("MediTrack Hospital System")
        title.setStyleSheet("font-size:18px; font-weight:700; color:#1e3a8a;")
        layout.addWidget(title)
        sub = QLabel("Please sign in to continue")
        sub.setStyleSheet("color:#6b7280;")
        layout.addWidget(sub)

        form = QFormLayout()
        self.username_input = QLineEdit()
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        form.addRow("Username:", self.username_input)
        form.addRow("Password:", self.password_input)
        layout.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.try_login)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        self.status = QLabel("")
        self.status.setStyleSheet("color:#dc2626;")
        layout.addWidget(self.status)

    def try_login(self):
        username = self.username_input.text().strip()
        password = self.password_input.text()
        users = read_csv("users")
        user = find_one(users, username=username)
        if not user:
            self.status.setText("Unknown username.")
            return
        stored = user.get("password", user.get("password_hash", ""))
        if password != stored:
            self.status.setText("Incorrect password.")
            return
        self.user = user
        self.accept()

# --------------------------- Auto BLE worker ---------------------------
class AutoBleWorker(QThread):
    status = pyqtSignal(str)
    uid = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.running = True

    def stop(self):
        self.running = False

    def run(self):
        if not HAS_BLE:
            self.status.emit("BLE not available")
            return
        while self.running:
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                devices = loop.run_until_complete(BleakScanner.discover(timeout=4.0, return_adv=True))
                target = next((d for d, _ in devices.values() if d.name == DEVICE_NAME), None)
                if target is None:
                    self.status.emit("Waiting for wireless sensor...")
                    loop.close()
                    self._sleep(3)
                    continue
                self.status.emit(f"Connecting to {target.address}...")
                loop.run_until_complete(self._connect(loop, target))
                loop.close()
                if not self.running:
                    break
                self.status.emit("Disconnected. Reconnecting...")
                self._sleep(2)
            except Exception as e:
                self.status.emit(f"BLE error: {e}")
                self._sleep(3)

    async def _connect(self, loop, target):
        async with BleakClient(target, timeout=15.0) as client:
            self.status.emit("Connected")
            def on_notify(_sender, data):
                try:
                    uid = data.decode("utf-8", errors="replace").strip()
                    if uid:
                        self.uid.emit(uid, "Bluetooth")
                except Exception as e:
                    self.status.emit(f"notify err: {e}")
            await client.start_notify(CHARACTERISTIC_UUID, on_notify)
            while self.running and client.is_connected:
                await asyncio.sleep(0.5)
            try:
                await client.stop_notify(CHARACTERISTIC_UUID)
            except Exception:
                pass

    def _sleep(self, sec):
        for _ in range(int(sec * 10)):
            if not self.running:
                return
            QThread.msleep(100)

# --------------------------- Scan animation widget ---------------------------
class ScanAnimationWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(260, 260)
        self._phase = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(60)

    def _tick(self):
        self._phase = (self._phase + 6) % 360
        self.update()

    def paintEvent(self, event):
        from PyQt5.QtGui import QPainter, QColor, QPen, QRadialGradient
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        cx = self.width() // 2
        cy = self.height() // 2
        maxr = min(cx, cy) - 8

        # pulsing background glow
        grad = QRadialGradient(cx, cy, maxr)
        grad.setColorAt(0, QColor(37, 99, 235, 60))
        grad.setColorAt(1, QColor(37, 99, 235, 0))
        painter.setBrush(grad)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(cx - maxr, cy - maxr, 2 * maxr, 2 * maxr)

        # animated rings
        for i in range(5):
            progress = (self._phase + i * 72) % 360 / 360.0
            r = int(maxr * (0.2 + 0.75 * progress))
            alpha = int(220 * (1 - progress))
            pen = QPen(QColor(37, 99, 235, alpha))
            pen.setWidth(3)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(cx - r, cy - r, 2 * r, 2 * r)

        # center
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(30, 58, 138))
        painter.drawEllipse(cx - 26, cy - 26, 52, 52)
        painter.setPen(QColor("white"))
        painter.setFont(QFont("Segoe UI", 12, QFont.Bold))
        painter.drawText(cx - 26, cy - 26, 52, 52, Qt.AlignCenter, "RFID")

# --------------------------- Main window ---------------------------
class MediTrackWindow(QMainWindow):
    def __init__(self, current_user=None):
        super().__init__()
        self.setWindowTitle("MediTrack - Hospital Management")
        self.resize(1280, 820)
        self.setStyleSheet(self._stylesheet())

        self.current_user = current_user or {}
        self.users = read_csv("users")

        self.worker = None

        # Keyboard-wedge (plug-and-play USB RFID) capture
        self._wedge_buffer = ""
        self._wedge_timer = QTimer(self)
        self._wedge_timer.setSingleShot(True)
        self._wedge_timer.setInterval(250)
        self._wedge_timer.timeout.connect(self._process_wedge_buffer)

        self._build_ui()
        self._set_photo(None)

        if not HAS_BLE:
            self.status_label.setText("Status: BLE not available")
            self.bt_toggle.setEnabled(False)

    def _stylesheet(self):
        return """
        QMainWindow {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #eaf2ff, stop:1 #f7faff);
        }
        QLabel { color: #1f2937; font-size: 24px; }
        QLabel#title { color: #1e3a8a; font-size: 40px; font-weight: 800; }
        QLabel#subtitle { color: #64748b; font-size: 22px; }
        QLabel#status { font-size: 24px; font-weight: 600; color: #2563eb; }
        QPushButton {
            font-size: 22px; background: #2563eb; color: white;
            border: none; border-radius: 14px; padding: 14px 28px;
            font-weight: 600;
        }
        QPushButton:hover { background: #1d4ed8; }
        QPushButton:pressed { background: #1e40af; }
        QPushButton#secondary {
            background: white; color: #2563eb; border: 1px solid #bfdbfe;
        }
        QPushButton#secondary:hover { background: #eff6ff; }
        QCheckBox { font-size: 16px; color: #1f2937; }
        QLineEdit { font-size: 16px; border-radius: 10px; padding: 8px; }
        QTextEdit { font-size: 16px; border-radius: 12px; }
        QPushButton {
            background: #2563eb; color: white; border: none;
            border-radius: 10px; padding: 9px 16px; font-weight: 600;
        }
        QPushButton:hover { background: #1d4ed8; }
        QPushButton:pressed { background: #1e40af; }
        QPushButton:disabled { background: #93c5fd; color: #f9fafb; }
        QPushButton#secondary {
            background: white; color: #2563eb; border: 1px solid #bfdbfe;
        }
        QPushButton#secondary:hover { background: #eff6ff; }
        QComboBox, QLineEdit {
            border: 1px solid #d1d5db; border-radius: 10px;
            padding: 8px 10px; background: white; min-height: 18px;
        }
        QTextEdit {
            background: white; border: 1px solid #e5e7eb;
            border-radius: 10px; padding: 6px;
        }
        QFrame#card { background: white; border: 1px solid #e5e7eb; border-radius: 14px; }
        """

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ---------- Sidebar ----------
        sidebar = card_frame()
        sidebar.setFixedWidth(300)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(16, 16, 16, 16)
        side.setSpacing(12)

        title = QLabel("MediTrack")
        title.setObjectName("title")
        side.addWidget(title)
        sub = QLabel("Hospital Management")
        sub.setObjectName("subtitle")
        side.addWidget(sub)

        side.addWidget(self._section("Signed in"))
        user_name = self.current_user.get("name", "Unknown")
        self.current_user_label = QLabel(user_name)
        self.current_user_label.setStyleSheet("font-weight:600; color:#1e3a8a;")
        side.addWidget(self.current_user_label)

        side.addWidget(self._section("Wireless sensor"))
        self.bt_toggle = QCheckBox("Enable Bluetooth sensor")
        self.bt_toggle.toggled.connect(self._on_bt_toggle)
        side.addWidget(self.bt_toggle)
        self.status_label = QLabel("Status: Bluetooth off")
        self.status_label.setObjectName("status")
        side.addWidget(self.status_label)

        side.addStretch(1)
        logout_btn = QPushButton("Logout")
        logout_btn.setObjectName("secondary")
        logout_btn.clicked.connect(self.close)
        side.addWidget(logout_btn)

        # ---------- Stacked pages ----------
        self.stack = QStackedWidget()

        # Front / scan page
        front = QWidget()
        front_layout = QVBoxLayout(front)
        front_layout.setAlignment(Qt.AlignCenter)
        front_layout.setSpacing(24)

        front_title = QLabel("Ready to Scan")
        front_title.setStyleSheet("font-size:44px; font-weight:700; color:#1e3a8a;")
        front_title.setAlignment(Qt.AlignCenter)
        front_layout.addWidget(front_title)

        front_sub = QLabel("Scan an RFID wristband to view patient information")
        front_sub.setStyleSheet("font-size:22px; color:#6b7280;")
        front_sub.setAlignment(Qt.AlignCenter)
        front_layout.addWidget(front_sub)

        self.scan_anim = ScanAnimationWidget()
        front_layout.addWidget(self.scan_anim, 0, Qt.AlignCenter)

        self.front_status = QLabel("Waiting for scan...")
        self.front_status.setStyleSheet("font-size:24px; font-weight:600; color:#2563eb;")
        self.front_status.setAlignment(Qt.AlignCenter)
        front_layout.addWidget(self.front_status)

        self.stack.addWidget(front)

        # Result page
        result = QWidget()
        result_layout = QVBoxLayout(result)
        result_layout.setSpacing(16)

        # Patient card
        patient_card = card_frame()
        pc = QHBoxLayout(patient_card)
        pc.setContentsMargins(18, 18, 18, 18)
        pc.setSpacing(18)

        self.photo_label = QLabel("No photo")
        self.photo_label.setFixedSize(200, 200)
        self.photo_label.setAlignment(Qt.AlignCenter)
        self.photo_label.setStyleSheet("background:#eff6ff; border-radius:100px; color:#2563eb; font-weight:600;")
        pc.addWidget(self.photo_label, 0, Qt.AlignTop)

        details = QVBoxLayout()
        details.setSpacing(8)
        self.name_label = QLabel("No patient loaded")
        self.name_label.setStyleSheet("font-size:34px; font-weight:700; color:#1e3a8a;")
        details.addWidget(self.name_label)

        self.detail_labels = {}
        for key, text in [
            ("Patient ID", "-"),
            ("Room / Bed", "-"),
            ("Physician", "-"),
            ("RFID status", "-"),
            ("Birth date", "-"),
        ]:
            row = QHBoxLayout()
            k = QLabel(f"{key}:")
            k.setStyleSheet("font-weight:600; color:#374151; font-size:22px;")
            v = QLabel(text)
            v.setStyleSheet("color:#111827; font-size:22px;")
            self.detail_labels[key] = v
            row.addWidget(k)
            row.addWidget(v)
            row.addStretch(1)
            details.addLayout(row)
        details.addStretch(1)
        pc.addLayout(details, 1)
        result_layout.addWidget(patient_card)

        # meds + records
        mid_row = QHBoxLayout()
        mid_row.setSpacing(16)

        meds_card = card_frame()
        mc = QVBoxLayout(meds_card)
        mc.setContentsMargins(16, 14, 16, 14)
        mc.addWidget(self._card_title("Medications"))
        self.meds_text = QTextEdit()
        self.meds_text.setReadOnly(True)
        self.meds_text.setStyleSheet("font-size:20px;")
        mc.addWidget(self.meds_text)
        mid_row.addWidget(meds_card, 1)

        rec_card = card_frame()
        rc = QVBoxLayout(rec_card)
        rc.setContentsMargins(16, 14, 16, 14)
        rc.addWidget(self._card_title("Clinical records"))
        self.records_text = QTextEdit()
        self.records_text.setReadOnly(True)
        self.records_text.setStyleSheet("font-size:20px;")
        rc.addWidget(self.records_text)
        mid_row.addWidget(rec_card, 1)

        result_layout.addLayout(mid_row, 1)

        scan_again_btn = QPushButton("Scan Again")
        scan_again_btn.clicked.connect(self.back_to_front)
        result_layout.addWidget(scan_again_btn, 0, Qt.AlignRight)

        self.stack.addWidget(result)

        # combine sidebar + stack
        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)
        content.addWidget(sidebar)
        content.addWidget(self.stack, 1)

        wrapper = QWidget()
        wrapper.setLayout(content)
        outer.addWidget(wrapper)

        self.stack.setCurrentIndex(0)

    def _section(self, text):
        lbl = QLabel(text.upper())
        lbl.setStyleSheet("font-size:10px; font-weight:700; color:#6b7280; letter-spacing:1px; margin-top:6px;")
        return lbl

    def _card_title(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet("font-size:14px; font-weight:700; color:#1e3a8a; margin-bottom:4px;")
        return lbl

    def current_user_id(self):
        return self.user_map.get(self.user_combo.currentText(), "")

    # ---------------- connection handling ----------------
    def _on_bt_toggle(self, checked):
        if checked:
            if not HAS_BLE:
                self.status_label.setText("Status: BLE not available")
                self.bt_toggle.setChecked(False)
                return
            if self.worker is None or not self.worker.isRunning():
                self.worker = AutoBleWorker()
                self.worker.status.connect(self._on_status)
                self.worker.uid.connect(lambda u, src: self.process_uid(u, src))
                self.worker.start()
            self.status_label.setText("Status: Starting...")
        else:
            if self.worker is not None:
                self.worker.stop()
                self.worker = None
            self.status_label.setText("Status: Bluetooth off")

    def back_to_front(self):
        self.name_label.setText("No patient loaded")
        for v in self.detail_labels.values():
            v.setText("-")
        self._set_photo(None)
        self.meds_text.setPlainText("")
        self.records_text.setPlainText("")
        self.front_status.setText("Waiting for scan...")
        self.stack.setCurrentIndex(0)

    def _on_status(self, text):
        self.status_label.setText(f"Status: {text}")
        self.front_status.setText(text)

    # ---------------- scan handling ----------------
    def process_uid(self, uid, reader_type=None):
        uid = (uid or "").strip()
        if not uid:
            return
        if reader_type is None:
            reader_type = "Keyboard Wedge"
        self.log(f"UID: {uid}")
        save_uid(uid)
        user_id = self.current_user_id()

        bundle, msg = get_bundle(uid)
        if bundle is None:
            self.status_label.setText("Tag not recognized")
            self.log(msg)
            log_scan("", user_id, reader_type, "Unknown tag")
            QMessageBox.warning(self, "Unknown tag", msg)
            return

        self._display_bundle(bundle, reader_type, uid)
        self.stack.setCurrentIndex(1)

    def _display_bundle(self, bundle, reader_type, uid=None):
        p = bundle["patient"]
        tag = bundle.get("tag")
        user_id = self.current_user.get("id", "")
        self.name_label.setText(p["name"])
        self.detail_labels["Patient ID"].setText(p["patient_code"])
        self.detail_labels["Room / Bed"].setText(f"{p['room']} / {p['bed']}")
        self.detail_labels["Physician"].setText(p["attending_physician"])
        self.detail_labels["RFID status"].setText(tag["status"] if tag else "No tag")
        self.detail_labels["Birth date"].setText(p["birth_date"])
        self._set_photo(p["id"])

        lines = []
        for order, admin in bundle["meds"]:
            status = admin["status"] if admin else "No administration record"
            admin_time = admin["administered_at"] if admin and admin["administered_at"] else "-"
            lines.append(
                f"{order['medication']}  ({order['dose']}, {order['route']})\n"
                f"  Schedule: {order['frequency']}\n"
                f"  Status: {status}   |   Administered: {admin_time}\n"
            )
        self.meds_text.setPlainText("\n".join(lines) if lines else "No active medication orders.")

        rlines = [f"[{r['record_type']}] {r['note']}  ({r['recorded_at']})" for r in bundle["records"]]
        self.records_text.setPlainText("\n".join(rlines) if rlines else "No clinical records.")

        self.status_label.setText("Patient loaded")
        self.log(f"Loaded patient: {p['name']} ({p['patient_code']})")

        if uid:
            log_scan(tag["id"] if tag else "", user_id, reader_type, "Success")
            log_audit(user_id, "SCAN", "rfid_tag", tag["id"] if tag else "")
        log_audit(user_id, "VIEW", "patient", p["id"])
        self.post_result(bundle, uid) if uid else None

    def _bundle_for_patient(self, patient):
        tag = find_one(read_csv("rfid_tags"), patient_id=patient["id"], status="Active")
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
        records = [r for r in read_csv("medical_records") if r["patient_id"] == patient["id"]]
        return {"tag": tag, "patient": patient, "meds": meds, "records": records}

    def find_patient_by_name(self):
        query = self.search_input.text().strip().lower()
        if not query:
            QMessageBox.information(self, "Search", "Enter a patient name or ID.")
            return
        patients = read_csv("patients")
        matches = [p for p in patients if query in p["name"].lower() or query == p["patient_code"].lower()]
        if not matches:
            QMessageBox.information(self, "Search", "No patient found.")
            return
        if len(matches) > 1:
            names = "\n".join(f"- {p['name']} ({p['patient_code']})" for p in matches)
            QMessageBox.information(self, "Multiple matches", f"Showing first match.\nMatches:\n{names}")
        patient = matches[0]
        bundle = self._bundle_for_patient(patient)
        self._display_bundle(bundle, "Manual", None)
        # select in combo
        for i in range(self.patient_combo.count()):
            if self.patient_combo.itemData(i) == patient["id"]:
                self.patient_combo.setCurrentIndex(i)
                break

    def quick_select_patient(self):
        self.find_patient_by_name()

    def on_patient_selected(self, index):
        if index <= 0:
            return
        pid = self.patient_combo.itemData(index)
        patients = read_csv("patients")
        patient = find_one(patients, id=pid)
        if not patient:
            return
        bundle = self._bundle_for_patient(patient)
        self._display_bundle(bundle, "Manual", None)

    def current_user_id(self):
        return self.current_user.get("id", "")

    def _set_photo(self, patient_id):
        if patient_id is None:
            self.photo_label.setText("No photo")
            self.photo_label.setPixmap(QPixmap())
            return
        path = None
        for ext in (".jpg", ".jpeg", ".png"):
            cand = IMG_DIR / f"patient_{patient_id}{ext}"
            if cand.exists():
                path = cand
                break
        if path is None:
            self.photo_label.setText("No photo")
            self.photo_label.setPixmap(QPixmap())
            return
        pix = QPixmap(str(path))
        if pix.isNull():
            self.photo_label.setText("Photo error")
            self.photo_label.setPixmap(QPixmap())
        else:
            self.photo_label.setText("")
            self.photo_label.setPixmap(pix.scaled(180, 180, Qt.KeepAspectRatio, Qt.SmoothTransformation))

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

    def eventFilter(self, obj, event):
        # Capture keyboard-wedge RFID scans when no text field is focused.
        if event.type() == QEvent.KeyPress:
            fw = self.focusWidget()
            if isinstance(fw, (QLineEdit, QTextEdit, QComboBox)):
                return super().eventFilter(obj, event)
            text = event.text()
            if text:
                self._wedge_buffer += text
                self._wedge_timer.start(250)
                return True
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                if self._wedge_buffer:
                    self._process_wedge_buffer()
                return True
        return super().eventFilter(obj, event)

    def _process_wedge_buffer(self):
        data = self._wedge_buffer.strip()
        self._wedge_buffer = ""
        if data:
            self.process_uid(data)

    def log(self, msg):
        line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
        print(line)


if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 18))

    login = LoginDialog()
    if login.exec_() != QDialog.Accepted or not login.user:
        sys.exit(0)

    win = MediTrackWindow(current_user=login.user)
    app.installEventFilter(win)
    win.showFullScreen()
    sys.exit(app.exec_())
    