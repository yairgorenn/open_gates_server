from flask import Flask, request, jsonify
import requests
import os
import json
import time
from datetime import datetime

app = Flask(__name__)

PUSHBULLET_API_KEY = os.getenv("PUSHBULLET_API_KEY")


BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# Load static data
USERS = load_json("users.json")["users"]
GATES = load_json("gates.json")

# ============================================================
# Device State – in memory only
# ============================================================

DEVICE_BUSY = False
DEVICE_LAST_GATE = None
DEVICE_TIMESTAMP = 0


def device_is_busy():
    return DEVICE_BUSY


def set_device_busy(gate_name):
    global DEVICE_BUSY, DEVICE_LAST_GATE, DEVICE_TIMESTAMP
    DEVICE_BUSY = True
    DEVICE_LAST_GATE = gate_name
    DEVICE_TIMESTAMP = time.time()


def set_device_free():
    global DEVICE_BUSY, DEVICE_LAST_GATE
    DEVICE_BUSY = False
    DEVICE_LAST_GATE = None


# ============================================================
# Basic route
# ============================================================

@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "ok"}), 200


# ============================================================
# Return allowed gates for a user
# ============================================================

@app.route("/allowed_gates", methods=["GET"])
def allowed_gates():
    token = request.args.get("token")
    if not token:
        return jsonify({"error": "token required"}), 400

    user = next((u for u in USERS if u["token"] == token), None)
    if not user:
        return jsonify({"error": "invalid token"}), 401

    allowed = user.get("allowed_gates")

    if isinstance(allowed, str) and allowed.upper() == "ALL":
        return jsonify({"allowed": [g["name"] for g in GATES]}), 200

    return jsonify({"allowed": allowed}), 200


# ============================================================
# Validate gate hours
# ============================================================

def gate_is_open_now(gate_name):
    gate = next((g for g in GATES if g["name"] == gate_name), None)
    if not gate:
        return False

    hours_list = gate.get("open_hours", [])
    if not hours_list:
        return True  # always open

    now = datetime.now().time()

    for rule in hours_list:
        t_from = datetime.strptime(rule["from"], "%H:%M").time()
        t_to = datetime.strptime(rule["to"], "%H:%M").time()

        if t_from <= now <= t_to:
            return True

    return False


# ============================================================
# /open – client wants to open a gate
# ============================================================

@app.route("/open", methods=["POST"])
def open_gate():
    global DEVICE_BUSY

    data = request.get_json()
    token = data.get("token")
    gate_name = data.get("gate")

    if not token or not gate_name:
        return jsonify({"error": "token and gate required"}), 400

    # Validate user
    user = next((u for u in USERS if u["token"] == token), None)
    if not user:
        return jsonify({"error": "invalid token"}), 401

    # Validate allowed gates
    allowed = user.get("allowed_gates")
    if isinstance(allowed, str) and allowed.upper() == "ALL":
        allowed = [g["name"] for g in GATES]

    if gate_name not in allowed:
        return jsonify({"error": "not allowed"}), 403

    # Validate gate exists
    gate_obj = next((g for g in GATES if g["name"] == gate_name), None)
    if gate_obj is None:
        return jsonify({"error": "unknown gate"}), 400

    # Validate time window
    if not gate_is_open_now(gate_name):
        return jsonify({"error": "gate closed now"}), 403

    # Check device availability
    if device_is_busy():
        return jsonify({"error": "device busy"}), 409

    # Mark device busy
    set_device_busy(gate_name)

    # Prepare push message
    pb_payload = {
        "type": "note",
        "title": "Open Gate",
        "body": f"gate={gate_name}"
    }

    headers = {
        "Access-Token": PUSHBULLET_API_KEY,
        "Content-Type": "application/json"
    }

    # Send to Pushbullet
    pb_response = requests.post(
        "https://api.pushbullet.com/v2/pushes",
        json=pb_payload,
        headers=headers,
        timeout=5
    )

    if pb_response.status_code != 200:
        set_device_free()
        return jsonify({"error": "pushbullet failure"}), 500

    # Return immediate acknowledgment
    return jsonify({"status": "received"}), 200


# ============================================================
# /confirm – phone reports success/failure
# ============================================================

@app.route("/confirm", methods=["POST"])
def confirm():
    data = request.get_json()

    status = data.get("status")
    gate = data.get("gate")

    if not status or not gate:
        return jsonify({"error": "invalid payload"}), 400

    # Release device immediately
    set_device_free()

    return jsonify({"ok": True, "received": {"gate": gate, "status": status}}), 200


# ============================================================
# /status – only checks whether device is busy or free
# ============================================================

@app.route("/status", methods=["GET"])
def status():
    if DEVICE_BUSY:
        # if stuck for > 30 seconds → force reset
        if time.time() - DEVICE_TIMESTAMP > 30:
            set_device_free()
            return jsonify({"status": "failed", "reason": "device_timeout"}), 200

        return jsonify({"status": "pending"}), 200

    return jsonify({"status": "ready"}), 200


# ============================================================
# Run locally
# ============================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
