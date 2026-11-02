#!/usr/bin/env python3
"""
MediTrack - Raspberry Pi RFID patient monitoring dashboard (PyQt5).

Features:
- Full-screen login
- RFID scanning flow with animated scan screen
- Patient profile, medications, clinical records
- Bluetooth auto-connect toggle (large touch target)
- Keyboard-wedge (plug-and-play USB RFID) auto-capture
- CSV-backed data and logging
"""

import asyncio
import csv
import hashlib
import os
import threading

# Force X11 on Linux/Wayland systems (fixes input and activation issues with PyQt5)
if os.name == "posix":
    # Force X11 even if the session defaults to Wayland
    os.environ["QT_QPA_PLATFORM"] = "xcb"
    # Avoid GTK/GObject style warnings on Raspberry Pi
    os.environ.setdefault("QT_STYLE_OVERRIDE", "Fusion")
import traceback
from datetime import datetime, timezone
from pathlib import Path

from PyQt5.QtCore import Qt, QThread, pyqtSignal, QEvent, QTimer
from PyQt5.QtGui import QFont, QPixmap, QColor, QBrush
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QLineEdit, QTextEdit, QFrame,
    QScrollArea, QMessageBox, QDialog, QDialogButtonBox, QFormLayout,
    QGridLayout, QCheckBox, QStackedWidget, QGraphicsDropShadowEffect,
    QScroller
)

BASE_DIR = Path(__file__).resolve().parent
DB_DIR = BASE_DIR / "database"
IMG_DIR = BASE_DIR / "images"
LOG_DIR = BASE_DIR / "logs"

DEVICE_NAME = "ESP32-S3-RFID-Reader"
CHARACTERISTIC_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26a8"
SERVER_URL = os.environ.get("MEDITRACK_SERVER", "").rstrip("/")

# Supabase
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://kjadezwzwvfualbvjrkm.supabase.co").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtqYWRlend6d3ZmdWFsYnZqcmttIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc5MzIyODkxMywiZXhwIjoyMTA4ODA0OTEzfQ.fXMvycUvTp9-TTuPPUnmrVFcI8kzuVrdoVJOQaX6ffA")
SYNC_INTERVAL = int(os.environ.get("SUPABASE_SYNC_INTERVAL", "30"))

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
        "scanned_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "outcome": outcome,
    })
    print(f"[scan] tag={tag_id} user={user_id} reader={reader_type} outcome={outcome}")
    # resolve tag token from csv for supabase
    def _push():
        try:
            tag_token = None
            for t in read_csv("rfid_tags"):
                if str(t.get("id")) == str(tag_id):
                    tag_token = t.get("tag_token")
                    break
            if tag_token:
                sb_log_scan(tag_token, user_id, reader_type, outcome)
            else:
                sb_insert("scan_logs", {
                    "reader_type": reader_type,
                    "scanned_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "outcome": outcome,
                })
        except Exception as e:
            print("log_scan sync failed:", e)
    threading.Thread(target=_push, daemon=True).start()


def log_audit(user_id, action, record_type, record_id):
    append_csv("audit_logs", {
        "id": next_id("audit_logs"),
        "user_id": user_id,
        "action": action,
        "record_type": record_type,
        "record_id": record_id,
        "occurred_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    print(f"[audit] user={user_id} action={action} {record_type}={record_id}")
    # sync to supabase (background to avoid UI delay)
    def _push():
        sb_insert("audit_logs", {
            "user_id": int(user_id) if str(user_id).isdigit() else None,
            "action": action,
            "record_type": record_type,
            "record_id": str(record_id),
            "occurred_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
    threading.Thread(target=_push, daemon=True).start()


# --------------------------- Supabase sync helpers ---------------------------
def _sb_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }


def sb_insert(table, row):
    if not HAS_REQUESTS:
        return
    try:
        requests.post(f"{SUPABASE_URL}/rest/v1/{table}", headers=_sb_headers(), json=row, timeout=8)
    except Exception as e:
        print("sb_insert failed:", e)


def sb_upsert(table, rows, on_conflict="id"):
    if not HAS_REQUESTS or not rows:
        return
    headers = _sb_headers()
    headers["Prefer"] = f"resolution=merge-duplicates,return=minimal"
    try:
        requests.post(
            f"{SUPABASE_URL}/rest/v1/{table}?on_conflict={on_conflict}",
            headers=headers, json=rows, timeout=15)
    except Exception as e:
        print("sb_upsert failed:", e)


def sync_csv_to_supabase():
    # The website is the source of truth for patient/tag/medication/record data.
    # The Pi only pulls those tables (see pull_supabase_to_csv). Pushing them from
    # the Pi can overwrite website edits (e.g. medication administration status),
    # so we intentionally do NOT push them here.
    # Scan/audit logs are pushed individually when they happen.
    pass  # keep quiet during periodic sync


def pull_supabase_to_csv():
    """Best-effort: refresh local CSV cache from Supabase so IDs and data match."""
    if not HAS_REQUESTS:
        return
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    tables = {
        "users": (DB_DIR / "users.csv", ["id", "employee_id", "name", "username", "password", "role", "status"]),
        "patients": (DB_DIR / "patients.csv", ["id", "patient_code", "name", "birth_date", "room", "bed", "attending_physician", "admission_status"]),
        "rfid_tags": (DB_DIR / "rfid_tags.csv", ["id", "tag_token", "patient_id", "status", "assigned_at", "deactivated_at"]),
        "medication_orders": (DB_DIR / "medication_orders.csv", ["id", "patient_id", "medication", "dose", "route", "frequency", "prescriber_id", "status"]),
        "medication_administrations": (DB_DIR / "medication_administrations.csv", ["id", "order_id", "scheduled_at", "administered_at", "status", "administered_by", "notes"]),
        "medical_records": (DB_DIR / "medical_records.csv", ["id", "patient_id", "clinician_id", "record_type", "note", "recorded_at"]),
    }
    for table, (path, cols) in tables.items():
        try:
            r = requests.get(f"{SUPABASE_URL}/rest/v1/{table}?select={','.join(cols)}", headers=headers, timeout=15)
            if not r.ok:
                print("pull", table, "failed:", r.status_code, r.text[:200])
                continue
            rows = r.json() or []
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(cols)
                for row in rows:
                    w.writerow([("" if row.get(c) is None else row.get(c, "")) for c in cols])
            pass  # keep quiet during periodic sync
        except Exception as e:
            print("pull", table, "error:", e)


def sb_log_scan(tag_token, user_id, reader_type, outcome):
    # resolve tag id
    try:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/rfid_tags?tag_token=eq.{tag_token}&select=id",
                         headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}, timeout=8)
        tid = None
        if r.ok and r.json():
            tid = r.json()[0]["id"]
        sb_insert("scan_logs", {
            "tag_id": tid,
            "user_id": int(user_id) if str(user_id).isdigit() else None,
            "reader_type": reader_type,
            "scanned_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "outcome": outcome,
        })
    except Exception as e:
        print("sb_log_scan failed:", e)


def save_uid(uid):
    try:
        with open(LOG_DIR / "uids.log", "a", encoding="utf-8") as f:
            f.write(f"{datetime.now(timezone.utc).isoformat()}  {uid}\n")
    except Exception as e:
        print("log write failed:", e)


# --------------------------- Card frame helper ---------------------------
def card_frame():
    frame = QFrame()
    frame.setObjectName("card")
    shadow = QGraphicsDropShadowEffect()
    shadow.setBlurRadius(24)
    shadow.setOffset(0, 4)
    shadow.setColor(QColor(0, 0, 0, 30))
    frame.setGraphicsEffect(shadow)
    return frame


def fmt_dt(value):
    if not value:
        return "-"
    try:
        txt = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(txt)
        return dt.astimezone().strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(value)


# --------------------------- Toggle switch ---------------------------
class ToggleSwitch(QCheckBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(52, 28)
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, event):
        painter = QPainter(self) if False else None
        from PyQt5.QtGui import QPainter
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        bg = QColor("#2563EB") if self.isChecked() else QColor("#CBD5E1")
        painter.setBrush(QBrush(bg))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(0, 0, w, h, h // 2, h // 2)
        knob_d = h - 6
        knob_x = w - knob_d - 3 if self.isChecked() else 3
        painter.setBrush(QBrush(QColor("#FFFFFF")))
        painter.drawEllipse(knob_x, 3, knob_d, knob_d)


# --------------------------- Scan animation ---------------------------
class ScanAnimationWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(220, 220)
        self._phase = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(50)

    def _tick(self):
        self._phase = (self._phase + 5) % 360
        self.update()

    def paintEvent(self, event):
        from PyQt5.QtGui import QPainter, QColor, QPen, QRadialGradient
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        cx = self.width() // 2
        cy = self.height() // 2
        maxr = min(cx, cy) - 8

        grad = QRadialGradient(cx, cy, maxr)
        grad.setColorAt(0, QColor(37, 99, 235, 50))
        grad.setColorAt(1, QColor(37, 99, 235, 0))
        painter.setBrush(grad)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(cx - maxr, cy - maxr, 2 * maxr, 2 * maxr)

        for i in range(5):
            progress = (self._phase + i * 72) % 360 / 360.0
            r = int(maxr * (0.2 + 0.75 * progress))
            alpha = int(200 * (1 - progress))
            pen = QPen(QColor(37, 99, 235, alpha))
            pen.setWidth(3)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(cx - r, cy - r, 2 * r, 2 * r)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(20, 43, 74))
        painter.drawEllipse(cx - 24, cy - 24, 48, 48)
        painter.setPen(QColor("white"))
        painter.setFont(QFont("Segoe UI", 10, QFont.Bold))
        painter.drawText(cx - 24, cy - 24, 48, 48, Qt.AlignCenter, "RFID")


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
        async with BleakClient(target, timeout=30.0) as client:
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
                await asyncio.sleep(1)
            try:
                await client.stop_notify(CHARACTERISTIC_UUID)
            except Exception:
                pass

    def _sleep(self, sec):
        for _ in range(int(sec * 10)):
            if not self.running:
                return
            QThread.msleep(100)


# --------------------------- On-screen keyboard ---------------------------
class VirtualKeyboard(QWidget):
    def __init__(self, parent=None, submit=None):
        super().__init__(parent)
        self.submit = submit
        outer = QVBoxLayout(self)
        outer.setSpacing(6)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setAlignment(Qt.AlignCenter)

        rows = [
            list("1234567890"),
            list("qwertyuiop"),
            list("asdfghjkl"),
            list("zxcvbnm") + ["Backspace"],
        ]
        for row in rows:
            hbox = QHBoxLayout()
            hbox.setSpacing(4)
            hbox.setAlignment(Qt.AlignCenter)
            for ch in row:
                if ch == "Backspace":
                    btn = QPushButton("Backspace")
                    btn.setFixedSize(96, 44)
                    btn.setFocusPolicy(Qt.NoFocus)
                    btn.clicked.connect(self._backspace)
                else:
                    btn = QPushButton(ch)
                    btn.setFixedSize(44, 44)
                    btn.setFocusPolicy(Qt.NoFocus)
                    btn.clicked.connect(lambda checked, x=ch: self._press(x))
                hbox.addWidget(btn)
            outer.addLayout(hbox)

        # space + enter row
        bottom = QHBoxLayout()
        bottom.setSpacing(4)
        bottom.setAlignment(Qt.AlignCenter)
        space = QPushButton("Space")
        space.setFixedSize(220, 44)
        space.setFocusPolicy(Qt.NoFocus)
        space.clicked.connect(lambda: self._press(" "))
        bottom.addWidget(space)
        enter = QPushButton("Enter")
        enter.setFixedSize(120, 44)
        enter.setFocusPolicy(Qt.NoFocus)
        enter.clicked.connect(self._enter)
        bottom.addWidget(enter)
        outer.addLayout(bottom)

    def _press(self, ch):
        w = QApplication.focusWidget()
        if isinstance(w, QLineEdit):
            w.insert(ch)
        elif isinstance(w, QTextEdit):
            w.insertPlainText(ch)

    def _backspace(self):
        w = QApplication.focusWidget()
        if isinstance(w, QLineEdit):
            w.backspace()
        elif isinstance(w, QTextEdit):
            c = w.textCursor()
            c.deletePreviousChar()
            w.setTextCursor(c)

    def _enter(self):
        if callable(self.submit):
            self.submit()
        else:
            w = QApplication.focusWidget()
            if isinstance(w, QLineEdit):
                w.parent().try_login() if hasattr(w.parent(), "try_login") else None


# --------------------------- Login dialog ---------------------------
class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("MediTrack Login")
        self.setModal(True)
        self.setWindowState(Qt.WindowFullScreen)
        self.user = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("QDialog { background: #F4F7FB; }")

        card = QFrame()
        card.setFixedWidth(1120)
        card.setStyleSheet("""
            QFrame {
                background: white;
                border: none;
                border-radius: 16px;
            }
        """)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(30)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 30))
        card.setGraphicsEffect(shadow)

        row = QHBoxLayout(card)
        row.setContentsMargins(24, 24, 24, 24)
        row.setSpacing(24)

        # Left: on-screen keyboard
        kb_wrap = QVBoxLayout()
        kb_label = QLabel("On-screen keyboard")
        kb_label.setStyleSheet("font-size:14px; font-weight:600; color:#64748B;")
        kb_label.setAlignment(Qt.AlignCenter)
        kb_wrap.addStretch(1)
        kb_wrap.addWidget(kb_label)
        self.keyboard = VirtualKeyboard(self, submit=self.try_login)
        kb_wrap.addWidget(self.keyboard)
        kb_wrap.addStretch(1)
        row.addLayout(kb_wrap, 0)

        # Right: login form
        cl = QVBoxLayout()
        cl.setSpacing(14)

        logo_pix = QPixmap(str(BASE_DIR / "logo.png"))
        if not logo_pix.isNull():
            logo_lbl = QLabel()
            logo_lbl.setPixmap(logo_pix.scaled(72, 72, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            logo_lbl.setAlignment(Qt.AlignCenter)
            cl.addWidget(logo_lbl)

        title = QLabel("MediTrack")
        title.setStyleSheet("font-size:30px; font-weight:800; color:#142B4A;")
        title.setAlignment(Qt.AlignCenter)
        cl.addWidget(title)

        sub = QLabel("Hospital Management System")
        sub.setStyleSheet("font-size:14px; color:#64748B;")
        sub.setAlignment(Qt.AlignCenter)
        cl.addWidget(sub)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Username")
        self.username_input.setMinimumHeight(44)
        self.username_input.setFocusPolicy(Qt.StrongFocus)
        cl.addWidget(self.username_input)
        self.username_input.setFocus()

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Password")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setMinimumHeight(44)
        cl.addWidget(self.password_input)

        login_btn = QPushButton("Sign In")
        login_btn.setMinimumHeight(44)
        login_btn.clicked.connect(self.try_login)
        cl.addWidget(login_btn)

        self.status = QLabel("")
        self.status.setStyleSheet("color:#DC2626; font-size:13px;")
        self.status.setAlignment(Qt.AlignCenter)
        cl.addWidget(self.status)
        cl.addStretch(1)

        row.addLayout(cl, 1)
        outer.addWidget(card, 0, Qt.AlignCenter)

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


# --------------------------- Main window ---------------------------
class MediTrackWindow(QMainWindow):
    def __init__(self, current_user=None):
        super().__init__()
        self.setWindowTitle("MediTrack")
        self.setStyleSheet(self._stylesheet())
        self.showFullScreen()

        self.current_user = current_user or {}
        self.users = read_csv("users")

        self.worker = None
        self._wedge_buffer = ""
        self._wedge_timer = QTimer(self)
        self._wedge_timer.setSingleShot(True)
        self._wedge_timer.setInterval(250)
        self._wedge_timer.timeout.connect(self._process_wedge_buffer)

        self._current_uid = None
        self._current_reader_type = None
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(30000)
        self._refresh_timer.timeout.connect(self._refresh_current)
        self._refresh_timer.start()

        self._build_ui()
        self._set_photo(None)

        if not HAS_BLE:
            self.status_label.setText("Status: BLE not available")
            self.bt_toggle.setEnabled(False)

    def _stylesheet(self):
        return """
        QMainWindow { background: #F4F7FB; }
        QLabel { color: #1E293B; font-size: 18px; }
        QLabel#title { color: #142B4A; font-size: 28px; font-weight: 800; }
        QLabel#subtitle { color: #64748B; font-size: 14px; }
        QLabel#status { font-size: 16px; font-weight: 600; color: #2563EB; }
        QPushButton {
            font-size: 18px; background: #2563EB; color: white;
            border: none; border-radius: 10px; padding: 10px 20px;
            font-weight: 600;
        }
        QPushButton:hover { background: #1D4ED8; }
        QPushButton:pressed { background: #1E40AF; }
        QPushButton:disabled { background: #94A3B8; color: #F8FAFC; }
        QPushButton#secondary {
            background: white; color: #2563EB; border: 1px solid #E2E8F0;
        }
        QPushButton#secondary:hover { background: #F8FAFC; }
        QLineEdit {
            border: 1px solid #CBD5E1; border-radius: 10px;
            padding: 10px 12px; background: white; font-size: 18px;
        }
        QTextEdit {
            background: white; border: 1px solid #CBD5E1;
            border-radius: 10px; padding: 8px; font-size: 16px;
        }
        QFrame#card {
            background: white; border: none;
            border-radius: 14px;
        }
        QScrollArea { border: none; background: transparent; }
        """

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ---------- Main content ----------
        main_wrapper = QWidget()
        main_wrapper.setStyleSheet("background: #F4F7FB;")
        main_layout = QHBoxLayout(main_wrapper)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(24)

        # Sidebar
        sidebar = card_frame()
        sidebar.setFixedWidth(280)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(20, 20, 20, 20)
        side.setSpacing(14)

        logo_pix = QPixmap(str(BASE_DIR / "logo.png"))
        if not logo_pix.isNull():
            logo_img = QLabel()
            logo_img.setPixmap(logo_pix.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            logo_img.setAlignment(Qt.AlignCenter)
            side.addWidget(logo_img)

        app_title = QLabel("MediTrack")
        app_title.setStyleSheet("font-size:20px; font-weight:700; color:#142B4A;")
        app_title.setAlignment(Qt.AlignCenter)
        side.addWidget(app_title)

        self.current_user_label = QLabel(self.current_user.get("name", "Unknown"))
        self.current_user_label.setStyleSheet("font-size:14px; font-weight:600; color:#1E293B;")
        self.current_user_label.setAlignment(Qt.AlignCenter)
        side.addWidget(self.current_user_label)

        side.addWidget(self._section("Wireless Sensor"))
        toggle_row = QHBoxLayout()
        toggle_label = QLabel("Bluetooth")
        toggle_label.setStyleSheet("font-size:16px; font-weight:600; color:#1E293B;")
        toggle_label.setCursor(Qt.PointingHandCursor)
        toggle_label.mousePressEvent = lambda e: self.bt_toggle.toggle()
        toggle_row.addWidget(toggle_label)

        touch_area = QWidget()
        touch_area.setFixedSize(80, 36)
        touch_area.setCursor(Qt.PointingHandCursor)
        ta_layout = QHBoxLayout(touch_area)
        ta_layout.setContentsMargins(12, 4, 12, 4)
        self.bt_toggle = ToggleSwitch()
        self.bt_toggle.setFixedSize(48, 24)
        self.bt_toggle.toggled.connect(self._on_bt_toggle)
        ta_layout.addWidget(self.bt_toggle, 0, Qt.AlignCenter)
        touch_area.mousePressEvent = lambda e: self.bt_toggle.toggle()
        toggle_row.addWidget(touch_area)
        toggle_row.addStretch(1)
        side.addLayout(toggle_row)

        self.rfid_status_indicator = QLabel("● Waiting for scan")
        self.rfid_status_indicator.setStyleSheet("color:#64748B; font-weight:600; font-size:14px;")
        side.addWidget(self.rfid_status_indicator)

        self.status_label = QLabel("Status: Bluetooth off")
        self.status_label.setStyleSheet("color:#2563EB; font-size:16px; font-weight:600;")
        side.addWidget(self.status_label)

        side.addStretch(1)

        scan_again_top = QPushButton("Scan Again")
        scan_again_top.setObjectName("secondary")
        scan_again_top.clicked.connect(self.back_to_front)
        side.addWidget(scan_again_top)

        logout_btn = QPushButton("Logout")
        logout_btn.setObjectName("secondary")
        logout_btn.clicked.connect(self.close)
        side.addWidget(logout_btn)

        main_layout.addWidget(sidebar)

        # ---------- Stacked pages ----------
        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack, 1)

        # Front / scan page
        front = QWidget()
        front.setStyleSheet("background: #F4F7FB;")
        front_layout = QVBoxLayout(front)
        front_layout.setContentsMargins(40, 40, 40, 40)
        front_layout.setSpacing(20)
        front_layout.addStretch(1)

        front_title = QLabel("Ready to Scan")
        front_title.setStyleSheet("font-size:36px; font-weight:700; color:#142B4A;")
        front_title.setAlignment(Qt.AlignCenter)
        front_layout.addWidget(front_title)

        front_sub = QLabel("Scan an RFID wristband to view patient information")
        front_sub.setStyleSheet("font-size:18px; color:#64748B;")
        front_sub.setAlignment(Qt.AlignCenter)
        front_layout.addWidget(front_sub)

        self.scan_anim = ScanAnimationWidget()
        self.scan_anim.setFixedSize(240, 240)
        front_layout.addWidget(self.scan_anim, 0, Qt.AlignCenter)

        self.front_status = QLabel("Waiting for scan...")
        self.front_status.setStyleSheet("font-size:20px; font-weight:600; color:#2563EB;")
        self.front_status.setAlignment(Qt.AlignCenter)
        front_layout.addWidget(self.front_status)

        front_layout.addStretch(1)
        self.stack.addWidget(front)

        # Result page
        result = QWidget()
        result.setStyleSheet("background: #F4F7FB;")
        result_layout = QVBoxLayout(result)
        result_layout.setContentsMargins(0, 0, 0, 0)
        result_layout.setSpacing(16)

        # Patient profile card
        patient_card = card_frame()
        pc = QHBoxLayout(patient_card)
        pc.setContentsMargins(24, 24, 24, 24)
        pc.setSpacing(24)

        self.photo_label = QLabel("No photo")
        self.photo_label.hide()

        details = QVBoxLayout()
        details.setSpacing(10)
        self.name_label = QLabel("No patient loaded")
        self.name_label.setStyleSheet("font-size:26px; font-weight:700; color:#142B4A;")
        details.addWidget(self.name_label)

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)
        self.detail_labels = {}
        keys = ["Patient ID", "Room / Bed", "Physician", "RFID status", "Birth date"]
        for i, key in enumerate(keys):
            k = QLabel(f"{key}:")
            k.setStyleSheet("font-weight:600; color:#374151; font-size:15px;")
            v = QLabel("-")
            v.setStyleSheet("color:#1E293B; font-size:15px;")
            v.setWordWrap(True)
            self.detail_labels[key] = v
            grid.addWidget(k, i, 0)
            grid.addWidget(v, i, 1)
        details.addLayout(grid)
        details.addStretch(1)
        pc.addLayout(details, 1)
        result_layout.addWidget(patient_card)

        # Medications + Clinical records
        mid_row = QHBoxLayout()
        mid_row.setSpacing(16)

        meds_card = card_frame()
        mc = QVBoxLayout(meds_card)
        mc.setContentsMargins(18, 16, 18, 16)
        mc.addWidget(self._card_title("Medications"))
        self.meds_container = QWidget()
        self.meds_layout = QVBoxLayout(self.meds_container)
        self.meds_layout.setSpacing(10)
        mc.addWidget(self.meds_container)
        mid_row.addWidget(meds_card, 1)

        rec_card = card_frame()
        rc = QVBoxLayout(rec_card)
        rc.setContentsMargins(18, 16, 18, 16)
        rc.addWidget(self._card_title("Clinical Records"))
        self.records_container = QWidget()
        self.records_layout = QVBoxLayout(self.records_container)
        self.records_layout.setSpacing(10)
        rc.addWidget(self.records_container)
        mid_row.addWidget(rec_card, 1)

        result_layout.addLayout(mid_row, 1)

        scan_again_btn = QPushButton("Scan Again")
        scan_again_btn.setMinimumHeight(40)
        scan_again_btn.clicked.connect(self.back_to_front)
        result_layout.addWidget(scan_again_btn, 0, Qt.AlignRight)

        result_scroll = QScrollArea()
        result_scroll.setWidgetResizable(True)
        result_scroll.setWidget(result)
        result_scroll.setStyleSheet("border:none; background:transparent;")
        result_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        QScroller.grabGesture(result_scroll, QScroller.TouchGesture)
        self.stack.addWidget(result_scroll)

        outer.addWidget(main_wrapper)
        self.stack.setCurrentIndex(0)

    def _section(self, text):
        lbl = QLabel(text.upper())
        lbl.setStyleSheet("font-size:12px; font-weight:700; color:#64748B; letter-spacing:1px; margin-top:6px;")
        return lbl

    def _card_title(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet("font-size:18px; font-weight:700; color:#142B4A; margin-bottom:4px;")
        return lbl

    def _refresh_ports(self):
        pass

    def _on_bt_toggle(self, checked):
        if checked:
            if not HAS_BLE:
                self.status_label.setText("Status: Bleak not installed")
                self.bt_toggle.setChecked(False)
                QMessageBox.warning(self, "Missing dependency", "bleak is not installed.\nRun: pip install bleak")
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

    def current_user_id(self):
        return self.current_user.get("id", "")

    def _on_status(self, text):
        self.status_label.setText(f"Status: {text}")
        self.front_status.setText(text)

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
            self.rfid_status_indicator.setText("● Unknown RFID tag")
            self.rfid_status_indicator.setStyleSheet("color:#DC2626; font-weight:600; font-size:14px;")
            self.front_status.setText("Unrecognized RFID tag")
            self.front_status.setStyleSheet("font-size:20px; font-weight:600; color:#DC2626;")
            self.stack.setCurrentIndex(0)
            self.log(msg)
            log_scan("", user_id, reader_type, "Unknown tag")
            return

        self._current_uid = uid
        self._current_reader_type = reader_type
        self._display_bundle(bundle, reader_type, uid)
        self.stack.setCurrentIndex(1)

    def _display_bundle(self, bundle, reader_type, uid=None):
        p = bundle["patient"]
        tag = bundle.get("tag")
        user_id = self.current_user_id()
        self.name_label.setText(p["name"])
        self.detail_labels["Patient ID"].setText(p["patient_code"])
        self.detail_labels["Room / Bed"].setText(f"{p['room']} / {p['bed']}")
        self.detail_labels["Physician"].setText(p["attending_physician"])
        self.detail_labels["RFID status"].setText(tag["status"] if tag else "No tag")
        self.detail_labels["Birth date"].setText(p["birth_date"])
        self._set_photo(p["id"])

        self._render_medications(bundle)
        self._render_records(bundle)

        self.status_label.setText("Patient loaded")
        self.rfid_status_indicator.setText("● Patient recognized")
        self.rfid_status_indicator.setStyleSheet("color:#16A34A; font-weight:600; font-size:14px;")
        self.log(f"Loaded patient: {p['name']} ({p['patient_code']})")

        if uid:
            log_scan(tag["id"] if tag else "", user_id, reader_type, "Success")
            log_audit(user_id, "SCAN", "rfid_tag", tag["id"] if tag else "")
        log_audit(user_id, "VIEW", "patient", p["id"])
        if uid:
            self.post_result(bundle, uid)

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

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
            elif item.layout() is not None:
                self._clear_layout(item.layout())

    def _render_medications(self, bundle):
        self._clear_layout(self.meds_layout)
        meds = bundle.get("meds", [])
        if not meds:
            lbl = QLabel("No active medication orders.")
            lbl.setStyleSheet("color:#64748B; font-size:14px;")
            self.meds_layout.addWidget(lbl)
            self.meds_layout.addStretch(1)
            return
        for order, admin in meds:
            status = admin["status"] if admin else "Pending"
            admin_time = fmt_dt(admin["administered_at"]) if admin and admin["administered_at"] else "-"
            color = {"Given": "#16A34A", "Pending": "#F59E0B", "Missed": "#DC2626", "Held": "#F59E0B", "Refused": "#DC2626"}.get(status, "#64748B")
            card = QFrame()
            card.setStyleSheet("background:#F8FAFC; border:none; border-radius:10px; padding:8px;")
            cl = QVBoxLayout(card)
            cl.setSpacing(4)
            name = QLabel(order["medication"])
            name.setStyleSheet("font-weight:700; font-size:16px; color:#142B4A;")
            name.setWordWrap(True)
            cl.addWidget(name)
            dose_lbl = QLabel(f"Dose: {order['dose']}   |   Route: {order['route']}")
            dose_lbl.setWordWrap(True)
            cl.addWidget(dose_lbl)
            sched_lbl = QLabel(f"Schedule: {order['frequency']}")
            sched_lbl.setWordWrap(True)
            cl.addWidget(sched_lbl)
            badge = QLabel(status.upper())
            badge.setStyleSheet(f"background:{color}; color:white; border-radius:6px; padding:2px 8px; font-size:11px; font-weight:700;")
            badge.setAlignment(Qt.AlignCenter)
            cl.addWidget(badge)
            cl.addWidget(QLabel(f"Administered: {admin_time}"))
            self.meds_layout.addWidget(card)
        self.meds_layout.addStretch(1)

    def _render_records(self, bundle):
        self._clear_layout(self.records_layout)
        records = bundle.get("records", [])
        if not records:
            lbl = QLabel("No clinical records.")
            lbl.setStyleSheet("color:#64748B; font-size:14px;")
            self.records_layout.addWidget(lbl)
            self.records_layout.addStretch(1)
            return
        for r in records:
            rtype = r.get("record_type", "Note")
            card = QFrame()
            card.setStyleSheet("background:#F8FAFC; border:none; border-radius:10px; padding:8px;")
            cl = QVBoxLayout(card)
            cl.setSpacing(4)
            title = QLabel(rtype)
            title.setStyleSheet("font-weight:700; font-size:16px; color:#2563EB;")
            cl.addWidget(title)
            note_lbl = QLabel(r.get("note", ""))
            note_lbl.setWordWrap(True)
            cl.addWidget(note_lbl)
            date_lbl = QLabel(f"Date: {fmt_dt(r.get('recorded_at', ''))}")
            date_lbl.setWordWrap(True)
            cl.addWidget(date_lbl)
            self.records_layout.addWidget(card)
        self.records_layout.addStretch(1)

    def back_to_front(self):
        self._current_uid = None
        self._current_reader_type = None
        self.name_label.setText("No patient loaded")
        for v in self.detail_labels.values():
            v.setText("-")
        self._set_photo(None)
        self._clear_layout(self.meds_layout)
        self._clear_layout(self.records_layout)
        self.front_status.setText("Waiting for scan...")
        self.front_status.setStyleSheet("font-size:20px; font-weight:600; color:#2563EB;")
        self.rfid_status_indicator.setText("● Waiting for scan")
        self.rfid_status_indicator.setStyleSheet("color:#64748B; font-weight:600; font-size:14px;")
        self.stack.setCurrentIndex(0)

    def _refresh_current(self):
        if not self._current_uid:
            return
        bundle, msg = get_bundle(self._current_uid)
        if bundle is not None:
            self._display_bundle(bundle, self._current_reader_type, None)

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
            self.photo_label.setPixmap(pix.scaled(150, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation))

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
            "scanned_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        try:
            r = requests.post(f"{SERVER_URL}/api/scan", json=payload, timeout=5)
            self.log(f"POST /api/scan -> {r.status_code}")
        except Exception as e:
            self.log(f"POST failed: {e}")

    def log(self, msg):
        line = f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {msg}"
        print(line)

    def _process_wedge_buffer(self):
        data = self._wedge_buffer.strip()
        self._wedge_buffer = ""
        if data:
            self.process_uid(data)

    def eventFilter(self, obj, event):
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


# --------------------------- Main entry ---------------------------
if __name__ == "__main__":
    import sys
    def _sync_loop():
        # initial sync in background so the UI appears immediately
        # Push local changes first, then pull remote changes, so we never
        # overwrite unsynced local edits.
        try:
            sync_csv_to_supabase()
        except Exception as e:
            print("initial sync failed:", e)
        try:
            pull_supabase_to_csv()
        except Exception as e:
            print("initial pull failed:", e)
        while True:
            try:
                threading.Event().wait(SYNC_INTERVAL)
                sync_csv_to_supabase()
                # Pull remote (website) changes frequently so the Pi stays in sync.
                pull_supabase_to_csv()
            except Exception as e:
                print("sync loop error:", e)

    threading.Thread(target=_sync_loop, daemon=True).start()

    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 12))
    app.setStyleSheet("QWidget { font-family: 'Segoe UI', 'Inter', sans-serif; }")

    login = LoginDialog()
    if login.exec_() != QDialog.Accepted or not login.user:
        sys.exit(0)

    win = MediTrackWindow(current_user=login.user)
    app.installEventFilter(win)
    win.showFullScreen()
    sys.exit(app.exec_())