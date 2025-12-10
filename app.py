from flask import Flask, request, jsonify
import requests
import os
import json
import uuid
import time
from datetime import datetime

app = Flask(__name__)

PUSHBULLET_API_KEY = os.getenv("PUSHBULLET_API_KEY")
LAST_STATUS = {
    "gate": None,
    "status": None,
    "time": None
}

# --------------------------------------
# Helpers: Load/Save JSON files
# --------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def load_json(filename):
    path = os.path.join(BASE_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(filename, data):
    path = os.path.join(BASE_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# --------------------------------------
# Load database files
# --------------------------------------

USERS = load_json("users.json")
GATES = load_json("gates.json")
DEVICE = load_json("device_status.json")

# session store in RAM (Railway ephemeral)
SESSIONS = {}


# ======================================
# BASIC ROUTES
# ======================================

@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "ok"}), 200


# ======================================
# GET ALLOWED GATES
# ======================================

@app.route("/allowed_gates", methods=["GET"])
def allowed_gates():
    token = request.args.get("token")

    # אין טוקן
    if not token:
        return jsonify({"error": "token required"}), 400

    # חיפוש המשתמש
    user = next((u for u in USERS if u["token"] == token), None)
    if not user:
        return jsonify({"error": "invalid token"}), 401

    allowed = user.get("allowed_gates")

    # ---------- ALL ----------
    # אם כתוב ALL – המשתמש יכול לפתוח את כל השערים
    if isinstance(allowed, str) and allowed.upper() == "ALL":
        try:
            all_gate_names = [g["name"] for g in GATES]
        except Exception as e:
            return jsonify({"error": f"gates.json invalid: {str(e)}"}), 500
        return jsonify({"allowed": all_gate_names}), 200

    # ---------- רשימת שערים ספציפית ----------
    if isinstance(allowed, list):
        return jsonify({"allowed": allowed}), 200

    # ---------- פורמט לא תקין ----------
    return jsonify({"error": "invalid user permissions format"}), 500


# ======================================
# VALIDATION FUNCTIONS
# ======================================

def gate_is_open_now(gate_name):
    # מציאת השער לפי שם
    gate = next((g for g in GATES if g["name"] == gate_name), None)
    if gate is None:
        return False  # לא אמור לקרות, כי כבר בדקנו קודם

    # get open_hours list
    hours_list = gate.get("open_hours", [])
    if not hours_list:
        return True  # אם אין מגבלות זמן – פתוח תמיד

    now = datetime.now().time()

    for rule in hours_list:
        t_from = datetime.strptime(rule["from"], "%H:%M").time()
        t_to = datetime.strptime(rule["to"], "%H:%M").time()

        # inclusive range
        if t_from <= now <= t_to:
            return True

    return False


def device_is_busy():
    return DEVICE.get("busy", False)


def set_device_busy(session_id):
    DEVICE["busy"] = True
    DEVICE["session"] = session_id
    DEVICE["timestamp"] = time.time()
    save_json("device_status.json", DEVICE)


def set_device_free():
    DEVICE["busy"] = False
    DEVICE["session"] = None
    save_json("device_status.json", DEVICE)


# ======================================
# OPEN GATE (CLIENT → SERVER)
# ======================================

@app.route("/open", methods=["POST"])
def open_gate():
    data = request.get_json()

    token = data.get("token")
    gate_name = data.get("gate")

    if not token or not gate_name:
        return jsonify({"error": "token and gate required"}), 400

    # Validate token
    user = next((u for u in USERS if u["token"] == token), None)
    if not user:
        return jsonify({"error": "invalid token"}), 401

    # Allowed list
    allowed = user.get("allowed_gates")
    if isinstance(allowed, str) and allowed.upper() == "ALL":
        allowed = [g["name"] for g in GATES]

    if gate_name not in allowed:
        return jsonify({"error": "not allowed"}), 403

    # Gate exists?
    gate_obj = next((g for g in GATES if g["name"] == gate_name), None)
    if gate_obj is None:
        return jsonify({"error": "unknown gate"}), 400

    # Time rule
    if not gate_is_open_now(gate_name):
        return jsonify({"error": "gate closed now"}), 403

    # Device busy?
    if device_is_busy():
        return jsonify({"error": "device busy"}), 409

    # Lock device
    set_device_busy("active")

    # Reset LAST_STATUS
    LAST_STATUS["gate"] = gate_name
    LAST_STATUS["status"] = "pending"
    LAST_STATUS["time"] = time.time()

    # Prepare Pushbullet
    pb_payload = {
        "type": "note",
        "title": "Open Gate",
        "body": f"gate={gate_name}"
    }

    headers = {
        "Access-Token": PUSHBULLET_API_KEY,
        "Content-Type": "application/json"
    }

    pb_response = requests.post(
        "https://api.pushbullet.com/v2/pushes",
        json=pb_payload,
        headers=headers,
        timeout=5
    )

    if pb_response.status_code != 200:
        set_device_free()
        LAST_STATUS["status"] = "failed"
        LAST_STATUS["time"] = time.time()
        return jsonify({"error": "pushbullet failure"}), 500

    return jsonify({"status": "received"})


# ======================================
# PHONE CONFIRMATION (/confirm)
# ======================================

@app.route("/confirm", methods=["POST"])
def confirm():
    data = request.get_json()

    gate = data.get("gate")
    status = data.get("status")

    if not gate or not status:
        return jsonify({"error": "gate and status required"}), 400

    # Update LAST_STATUS
    LAST_STATUS["gate"] = gate
    LAST_STATUS["status"] = status
    LAST_STATUS["time"] = time.time()

    # Free device
    set_device_free()

    return jsonify({"ok": True})


# ======================================
# SESSION STATUS POLL
# ======================================

@app.route("/status", methods=["GET"])
def status():
    # אם עדיין בהמתנה
    if LAST_STATUS["status"] == "pending":
        # Timeout after 30 seconds
        if time.time() - LAST_STATUS["time"] > 30:
            LAST_STATUS["status"] = "failed"
            LAST_STATUS["time"] = time.time()
            set_device_free()

    return jsonify(LAST_STATUS)


# ======================================
# MAIN (for local dev)
# ======================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
