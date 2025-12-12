from flask import Flask, request, jsonify
import os
import time
from datetime import datetime
import json

app = Flask(__name__)
LAST_RESULT = None
LAST_PHONE_SEEN = 0
PB_ALERT_SENT = False

PHONE_TIMEOUT_SECONDS = 10 * 60  # 10 דקות

# ============================================================
# ENV
# ============================================================

PUSHBULLET_API_KEY = os.getenv("PUSHBULLET_API_KEY")  # שמור לעתיד
DEVICE_SECRET = os.getenv("DEVICE_SECRET")

USERS_JSON = os.getenv("USERS_JSON")
if not USERS_JSON:
    raise ValueError("USERS_JSON missing from environment")

try:
    USERS = json.loads(USERS_JSON)
except json.JSONDecodeError:
    raise ValueError("USERS_JSON is invalid JSON")

# ============================================================
# Gates configuration
# ============================================================

GATES = [
    {"name": "Main",      "phone_number": "972505471743", "open_hours": [{"from": "00:00", "to": "23:59"}]},
    {"name": "Gay",       "phone_number": "972503403742", "open_hours": [{"from": "00:00", "to": "23:59"}]},
    {"name": "Enter",     "phone_number": "972503924081", "open_hours": [{"from": "05:20", "to": "21:00"}]},
    {"name": "Exit",      "phone_number": "972503924106", "open_hours": [{"from": "05:20", "to": "21:00"}]},
    {"name": "EinCarmel", "phone_number": "972542688743", "open_hours": [{"from": "00:00", "to": "23:59"}]},
    {"name": "Almagor",   "phone_number": "972503817647", "open_hours": [{"from": "00:00", "to": "23:59"}]},
]

# ============================================================
# In-memory state (single device, single task)
# ============================================================

DEVICE_BUSY = False
CURRENT_TASK = None        # {"task": "open", "gate": "...", "phone_number": "..."}
TASK_TIMESTAMP = 0

# ============================================================
# Helpers
# ============================================================
def send_pushbullet(title, body):
    if not PUSHBULLET_API_KEY:
        return

    try:
        requests.post(
            "https://api.pushbullet.com/v2/pushes",
            json={
                "type": "note",
                "title": title,
                "body": body
            },
            headers={
                "Access-Token": PUSHBULLET_API_KEY,
                "Content-Type": "application/json"
            },
            timeout=5
        )
    except Exception:
        pass  # לא מפיל שרת בגלל התראה



def gate_is_open_now(gate_name):
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


def device_busy():
    return DEVICE_BUSY


def lock_device(task):
    global DEVICE_BUSY, CURRENT_TASK, TASK_TIMESTAMP
    DEVICE_BUSY = True
    CURRENT_TASK = task
    TASK_TIMESTAMP = time.time()


def release_device():
    global DEVICE_BUSY, CURRENT_TASK
    DEVICE_BUSY = False
    CURRENT_TASK = None


# ============================================================
# Health check
# ============================================================
def check_phone_alive():
    global PB_ALERT_SENT

    if LAST_PHONE_SEEN == 0:
        return  # עוד לא דיבר איתנו אף פעם

    silence = time.time() - LAST_PHONE_SEEN

    if silence > PHONE_TIMEOUT_SECONDS and not PB_ALERT_SENT:
        send_pushbullet(
            "⚠ Gate system alert",
            f"No phone heartbeat for {int(silence/60)} minutes"
        )
        PB_ALERT_SENT = True



@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "ok"}), 200


# ============================================================
# Allowed gates
# ============================================================

@app.route("/allowed_gates", methods=["GET"])
def allowed_gates():
    check_phone_alive()
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
# Client → Server : create task
# ============================================================

@app.route("/open", methods=["POST"])
def open_gate():
    check_phone_alive()
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

    if device_busy():
        return jsonify({"error": "device busy"}), 409

    gate_obj = next((g for g in GATES if g["name"] == gate_name), None)
    if not gate_obj:
        return jsonify({"error": "unknown gate"}), 400

    lock_device({
        "task": "open",
        "gate": gate_obj["name"],
        "phone_number": gate_obj["phone_number"]
    })

    return jsonify({"status": "task_created"}), 200


# ============================================================
# Phone → Server : polling for task
# ============================================================

@app.route("/phone_task", methods=["GET"])
def phone_task():
    check_phone_alive()
    secret = request.args.get("device_secret")
    if secret != DEVICE_SECRET:
        return jsonify({"error": "unauthorized"}), 403

    if CURRENT_TASK:
        return jsonify(CURRENT_TASK), 200

    return jsonify({"task": "none"}), 200


# ============================================================
# Phone → Server : confirm result
# ============================================================

@app.route("/confirm", methods=["POST"])
def confirm():
    global LAST_RESULT

    data = request.get_json()
    gate = data.get("gate")
    status = data.get("status")
    secret = data.get("device_secret")

    if not gate or not status or not secret:
        return jsonify({"error": "invalid payload"}), 400

    if secret != DEVICE_SECRET:
        return jsonify({"error": "unauthorized"}), 401

    LAST_RESULT = {
        "status": "opened" if status.lower() == "success" else "failed",
        "gate": gate
    }

    release_device()
    return jsonify({"ok": True}), 200


# ============================================================
# Status for client (optional)
# ============================================================

@app.route("/status", methods=["GET"])
def status():
    global LAST_RESULT
    check_phone_alive()

    if LAST_RESULT is not None:
        result = LAST_RESULT
        LAST_RESULT = None
        return jsonify(result), 200

    if DEVICE_BUSY:
        if time.time() - TASK_TIMESTAMP > 30:
            release_device()
            return jsonify({"status": "failed"}), 200
        return jsonify({"status": "pending"}), 200

    return jsonify({"status": "ready"}), 200


# ============================================================
# Local run
# ============================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
