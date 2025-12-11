from flask import Flask, request, jsonify
import requests
import os
import time
from datetime import datetime

app = Flask(__name__)

PUSHBULLET_API_KEY = os.getenv("PUSHBULLET_API_KEY")


# ============================================================
# Internal in-memory state
# ============================================================

DEVICE_BUSY = False        # האם הטלפון כרגע מבצע פעולה
DEVICE_LAST_GATE = None    # איזה שער נפתח כעת
DEVICE_TIMESTAMP = 0       # זמן תחילת הפעולה
LAST_RESULT = None         # תוצאה שהטלפון שלח (opened/failed)


def log(msg):
    """Utility printing function (currently unused)."""
    print(f"[SERVER LOG] {datetime.now().strftime('%H:%M:%S')} - {msg}", flush=True)


def device_is_busy():
    """Return True if the device is locked performing a gate action."""
    return DEVICE_BUSY


def set_device_busy(gate_name):
    """Mark device as BUSY and store timestamp."""
    global DEVICE_BUSY, DEVICE_LAST_GATE, DEVICE_TIMESTAMP
    DEVICE_BUSY = True
    DEVICE_LAST_GATE = gate_name
    DEVICE_TIMESTAMP = time.time()


def set_device_free():
    """Release device lock and clear last gate."""
    global DEVICE_BUSY, DEVICE_LAST_GATE
    DEVICE_BUSY = False
    DEVICE_LAST_GATE = None


# ============================================================
# Hardcoded USERS + GATES
# ============================================================

#USERS = [
   # {"name": "Yair", "token": "482913", "allowed_gates": "ALL"},
    #{"name": "Miki", "token": "173025", "allowed_gates": ["Main", "Enter", "Exit", "Gay"]},
    #{"name": "Raz", "token": "650391", "allowed_gates": ["Main", "Enter", "Exit", "Gay"]},
    #{"name": "Nofar", "token": "902574", "allowed_gates": "ALL"},
    #{"name": "Liat", "token": "315760", "allowed_gates": "ALL"},
    #{"name": "Tomer", "token": "319702", "allowed_gates": "ALL"},
    #{"name": "Alon", "token": "768204", "allowed_gates": "ALL"}
#]
# Load USERS from Railway environment variable
USERS_JSON = os.getenv("USERS_JSON")

if USERS_JSON:
    try:
        USERS = json.loads(USERS_JSON)
    except json.JSONDecodeError:
        raise ValueError("❌ USERS_JSON is invalid JSON")
else:
    raise ValueError("❌ USERS_JSON is missing from environment variables")


GATES = [
    {"name": "Main", "open_hours": [{"from": "00:00", "to": "23:59"}]},
    {"name": "Gay", "open_hours": [{"from": "00:00", "to": "23:59"}]},
    {"name": "Enter", "open_hours": [{"from": "05:20", "to": "21:00"}]},
    {"name": "Exit", "open_hours": [{"from": "05:20", "to": "21:00"}]},
    {"name": "EinCarmel", "open_hours": [{"from": "00:00", "to": "23:59"}]},
    {"name": "Almagor", "open_hours": [{"from": "00:00", "to": "23:59"}]}
]


# ============================================================
# Allowed gates endpoint
# ============================================================

@app.route("/allowed_gates", methods=["GET"])
def allowed_gates():
    """Return list of gates the user is allowed to open."""
    token = request.args.get("token")
    if not token:
        return jsonify({"error": "token required"}), 400

    user = next((u for u in USERS if u["token"] == token), None)
    if not user:
        return jsonify({"error": "invalid token"}), 401

    allowed = user["allowed_gates"]
    if allowed == "ALL":
        return jsonify({"allowed": [g["name"] for g in GATES]}), 200

    return jsonify({"allowed": allowed}), 200


# ============================================================
# Gate time validation
# ============================================================

def gate_is_open_now(gate_name):
    """Return True if current time falls inside gate's allowed hours."""
    gate = next((g for g in GATES if g["name"] == gate_name), None)
    if not gate:
        return False

    now = datetime.now().time()

    for rule in gate["open_hours"]:
        t_from = datetime.strptime(rule["from"], "%H:%M").time()
        t_to = datetime.strptime(rule["to"], "%H:%M").time()
        if t_from <= now <= t_to:
            return True

    return False


# ============================================================
# open gate
# ============================================================

@app.route("/open", methods=["POST"])
def open_gate():
    """Validate user → check gate → lock device → send Pushbullet."""
    global DEVICE_BUSY

    data = request.get_json()
    token = data.get("token")
    gate_name = data.get("gate")

    if not token or not gate_name:
        return jsonify({"error": "token and gate required"}), 400

    user = next((u for u in USERS if u["token"] == token), None)
    if not user:
        return jsonify({"error": "invalid token"}), 401

    allowed = user["allowed_gates"]
    if allowed == "ALL":
        allowed = [g["name"] for g in GATES]

    if gate_name not in allowed:
        return jsonify({"error": "not allowed"}), 403

    if not gate_is_open_now(gate_name):
        return jsonify({"error": "gate closed now"}), 403

    if device_is_busy():
        return jsonify({"error": "device busy"}), 409

    # Lock device
    set_device_busy(gate_name)

    # Send Pushbullet
    pb_body = f"gate={gate_name}"

    pb_res = requests.post(
        "https://api.pushbullet.com/v2/pushes",
        json={"type": "note", "title": "Open Gate", "body": pb_body},
        headers={"Access-Token": PUSHBULLET_API_KEY, "Content-Type": "application/json"},
        timeout=5
    )

    if pb_res.status_code != 200:
        set_device_free()
        return jsonify({"error": "pushbullet failure"}), 500

    return jsonify({"status": "received"}), 200


# ============================================================
# confirm
# ============================================================

@app.route("/confirm", methods=["POST"])
def confirm():
    """Called by phone. Save result and release device."""
    global LAST_RESULT

    data = request.get_json()
    status = data.get("status")
    gate = data.get("gate")

    if not status or not gate:
        return jsonify({"error": "invalid payload"}), 400

    # Map phone result → API result
    LAST_RESULT = {
        "status": "opened" if status.lower() == "success" else "failed",
        "gate": gate
    }

    set_device_free()

    return jsonify({"ok": True}), 200


# ============================================================
# status
# ============================================================

@app.route("/status", methods=["GET"])
def status():
    """Return pending/opened/failed or ready."""
    global LAST_RESULT, DEVICE_TIMESTAMP

    # Return final result once
    if LAST_RESULT is not None:
        result = LAST_RESULT
        LAST_RESULT = None
        return jsonify(result), 200

    if DEVICE_BUSY:
        age = time.time() - DEVICE_TIMESTAMP
        if age > 30:
            set_device_free()
            return jsonify({"status": "failed"}), 200
        return jsonify({"status": "pending"}), 200

    return jsonify({"status": "ready"}), 200


# ============================================================
# Local server run
# ============================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
