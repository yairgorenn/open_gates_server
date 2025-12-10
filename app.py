from flask import Flask, request, jsonify
import requests
import os
import json
import time
from datetime import datetime

app = Flask(__name__)

PUSHBULLET_API_KEY = os.getenv("PUSHBULLET_API_KEY")

# ============================================================
# Internal in-memory state
# ============================================================

DEVICE_BUSY = False
DEVICE_LAST_GATE = None
DEVICE_TIMESTAMP = 0
LAST_RESULT = None


def log(msg):
    print(f"[SERVER LOG] {datetime.now().strftime('%H:%M:%S')} - {msg}", flush=True)

def device_is_busy():
    return DEVICE_BUSY

def set_device_busy(gate_name):
    global DEVICE_BUSY, DEVICE_LAST_GATE, DEVICE_TIMESTAMP
    DEVICE_BUSY = True
    DEVICE_LAST_GATE = gate_name
    DEVICE_TIMESTAMP = time.time()
    log(f"Device marked BUSY for gate '{gate_name}'")

def set_device_free():
    global DEVICE_BUSY, DEVICE_LAST_GATE
    DEVICE_BUSY = False
    DEVICE_LAST_GATE = None
    log("Device marked FREE")


# ============================================================
# Hardcoded USERS + GATES
# ============================================================

USERS = [
    {"name": "Yair", "token": "482913", "allowed_gates": "ALL"},
    {"name": "Miki", "token": "173025", "allowed_gates": ["Main", "Enter", "Exit", "Gay"]},
    {"name": "Raz", "token": "650391", "allowed_gates": ["Main", "Enter", "Exit", "Gay"]},
    {"name": "Nofar", "token": "902574", "allowed_gates": "ALL"},
    {"name": "Liat", "token": "315760", "allowed_gates": "ALL"},
    {"name": "Alon", "token": "768204", "allowed_gates": "ALL"}
]

GATES = [
    {"name": "Main", "open_hours": [{"from": "00:00", "to": "23:59"}]},
    {"name": "Gay", "open_hours": [{"from": "00:00", "to": "23:59"}]},
    {"name": "Enter", "open_hours": [{"from": "05:20", "to": "21:00"}]},
    {"name": "Exit", "open_hours": [{"from": "05:20", "to": "21:00"}]},
    {"name": "EinCarmel", "open_hours": [{"from": "00:00", "to": "23:59"}]},
    {"name": "Almagor", "open_hours": [{"from": "00:00", "to": "23:59"}]}
]


# ============================================================
# Allowed gates
# ============================================================

@app.route("/allowed_gates", methods=["GET"])
def allowed_gates():
    token = request.args.get("token")
    log(f"/allowed_gates called with token={token}")

    if not token:
        return jsonify({"error": "token required"}), 400

    user = next((u for u in USERS if u["token"] == token), None)
    if not user:
        log("Invalid token")
        return jsonify({"error": "invalid token"}), 401

    allowed = user["allowed_gates"]
    if allowed == "ALL":
        result = [g["name"] for g in GATES]
        log(f"Returning ALL gates: {result}")
        return jsonify({"allowed": result}), 200

    log(f"Returning allowed gates: {allowed}")
    return jsonify({"allowed": allowed}), 200


# ============================================================
# Validate gate time
# ============================================================

def gate_is_open_now(gate_name):
    gate = next((g for g in GATES if g["name"] == gate_name), None)
    if not gate:
        return False

    now = datetime.now().time()
    hours_list = gate["open_hours"]

    for rule in hours_list:
        t_from = datetime.strptime(rule["from"], "%H:%M").time()
        t_to = datetime.strptime(rule["to"], "%H:%M").time()
        if t_from <= now <= t_to:
            return True

    return False


# ============================================================
# OPEN request
# ============================================================

@app.route("/open", methods=["POST"])
def open_gate():
    global DEVICE_BUSY

    data = request.get_json()
    log(f"/open received payload: {data}")

    token = data.get("token")
    gate_name = data.get("gate")

    if not token or not gate_name:
        log("Missing token or gate")
        return jsonify({"error": "token and gate required"}), 400

    user = next((u for u in USERS if u["token"] == token), None)
    if not user:
        log("Invalid token")
        return jsonify({"error": "invalid token"}), 401

    allowed = user["allowed_gates"]
    if allowed == "ALL":
        allowed = [g["name"] for g in GATES]

    if gate_name not in allowed:
        log(f"Gate '{gate_name}' not allowed for user")
        return jsonify({"error": "not allowed"}), 403

    if not gate_is_open_now(gate_name):
        log(f"Gate '{gate_name}' is currently closed")
        return jsonify({"error": "gate closed now"}), 403

    if device_is_busy():
        log("Device is busy")
        return jsonify({"error": "device busy"}), 409

    # Mark busy
    set_device_busy(gate_name)

    # Push to phone
    pb_body = f"gate={gate_name}"
    log(f"Sending Pushbullet: {pb_body}")

    pb_res = requests.post(
        "https://api.pushbullet.com/v2/pushes",
        json={"type": "note", "title": "Open Gate", "body": pb_body},
        headers={"Access-Token": PUSHBULLET_API_KEY, "Content-Type": "application/json"},
        timeout=5
    )

    log(f"Pushbullet response: {pb_res.status_code}")

    if pb_res.status_code != 200:
        log("Pushbullet failed → freeing device")
        set_device_free()
        return jsonify({"error": "pushbullet failure"}), 500

    return jsonify({"status": "received"}), 200


# ============================================================
# CONFIRM from phone
# ============================================================

@app.route("/confirm", methods=["POST"])
def confirm():
    global LAST_RESULT

    data = request.get_json()
    status = data.get("status")
    gate = data.get("gate")

    if not status or not gate:
        return jsonify({"error": "invalid payload"}), 400

    # Convert phone status → server status
    if status.lower() == "success":
        server_status = "opened"
    else:
        server_status = "failed"

    # Save final result so client can read it
    LAST_RESULT = {
        "status": server_status,
        "gate": gate
    }

    # Free device
    set_device_free()

    return jsonify({"ok": True}), 200


# ============================================================
# STATUS
# ============================================================

@app.route("/status", methods=["GET"])
def status():
    global LAST_RESULT, DEVICE_TIMESTAMP

    # If phone already reported success/fail → return it once
    if LAST_RESULT is not None:
        result = LAST_RESULT
        LAST_RESULT = None   # erase after read
        return jsonify(result), 200

    # Device still processing
    if DEVICE_BUSY:
        age = time.time() - DEVICE_TIMESTAMP
        if age > 30:
            set_device_free()
            return jsonify({"status": "failed"}), 200
        return jsonify({"status": "pending"}), 200

    # Nothing happening
    return jsonify({"status": "ready"}), 200


# ============================================================
# Run local
# ============================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
