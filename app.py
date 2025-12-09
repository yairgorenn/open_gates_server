from flask import Flask, request, jsonify
import requests
import os
import json
import uuid
import time
from datetime import datetime

app = Flask(__name__)

PUSHBULLET_API_KEY = os.getenv("PUSHBULLET_API_KEY")

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
    gate = GATES.get(gate_name)
    if not gate:
        return False

    # 24/7
    if gate.get("hours") == "24/7":
        return True

    try:
        start, end = gate["hours"].split("-")
        now = datetime.now().strftime("%H:%M")
        return start <= now <= end
    except:
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

    # Extract allowed list
    allowed = user.get("allowed_gates")
    if isinstance(allowed, str) and allowed.upper() == "ALL":
        allowed = [g["name"] for g in GATES]

    # Validate permissions
    if gate_name not in allowed:
        return jsonify({"error": "not allowed"}), 403

    # Validate gate exists
    gate_obj = next((g for g in GATES if g["name"] == gate_name), None)
    if gate_obj is None:
        return jsonify({"error": "unknown gate"}), 400

    # Validate gate is open now
    if not gate_is_open_now(gate_name):
        return jsonify({"error": "gate closed now"}), 403

    # Check if device busy
    if device_is_busy():
        return jsonify({"error": "device busy"}), 409

    # Create session
    session_id = uuid.uuid4().hex[:12]
    SESSIONS[session_id] = {
        "gate": gate_name,
        "status": "pending",
        "created": time.time()
    }

    # Lock device
    set_device_busy(session_id)

    # Prepare Pushbullet payload
    pb_payload = {
        "type": "note",
        "title": "Open Gate",
        "body": f"gate={gate_name};session={session_id}"
    }

    headers = {
        "Access-Token": PUSHBULLET_API_KEY,
        "Content-Type": "application/json"
    }

    # Send Pushbullet command
    pb_response = requests.post(
        "https://api.pushbullet.com/v2/pushes",
        json=pb_payload,
        headers=headers,
        timeout=5
    )

    if pb_response.status_code != 200:
        set_device_free()
        SESSIONS[session_id]["status"] = "failed"
        SESSIONS[session_id]["reason"] = "pushbullet_error"
        return jsonify({"error": "pushbullet failure"}), 500

    return jsonify({"status": "received", "session": session_id})


# ======================================
# PHONE CONFIRMATION (/confirm)
# ======================================

@app.route("/confirm", methods=["POST"])
def confirm():
    data = request.get_json()

    session_id = data.get("session")
    status = data.get("status")
    gate = data.get("gate")

    if not session_id or not status or not gate:
        return jsonify({"error": "invalid payload"}), 400

    if session_id not in SESSIONS:
        return jsonify({"error": "unknown session"}), 400

    # Update session state
    SESSIONS[session_id]["status"] = status
    SESSIONS[session_id]["completed"] = time.time()

    # Release device
    set_device_free()

    return jsonify({"ok": True})


# ======================================
# SESSION STATUS POLL
# ======================================

@app.route("/status", methods=["GET"])
def status():
    session_id = request.args.get("id")
    if not session_id:
        return jsonify({"error": "missing id"}), 400

    if session_id not in SESSIONS:
        return jsonify({"error": "unknown session"}), 400

    session = SESSIONS[session_id]

    # Timeout check (30 seconds)
    if session["status"] == "pending":
        if time.time() - session["created"] > 30:
            session["status"] = "failed"
            session["reason"] = "device_timeout"
            set_device_free()

    return jsonify(session)


# ======================================
# MAIN (for local dev)
# ======================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
