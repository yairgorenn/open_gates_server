from flask import Flask, request, jsonify
import os
import time
from datetime import datetime
import json
import requests

app = Flask(__name__)

# ============================================================
# FSM STATE
# ============================================================

STATE = "IDLE"          # IDLE | PENDING | OPENED | FAILED

CURRENT_TASK = None     # {"gate": "...", "phone_number": "..."}
TASK_CREATED_AT = 0

LAST_RESULT = None      # {"status": "...", "gate": "...", "reason": "..."}
RESULT_CREATED_AT = 0

TASK_TIMEOUT = 20       # seconds – phone must act
CLIENT_READ_TIMEOUT = 10  # seconds – client must read result

# ============================================================
# PHONE MONITORING
# ============================================================

LAST_PHONE_SEEN = 0
PB_ALERT_SENT = False
PHONE_TIMEOUT_SECONDS = 10 * 60

# ============================================================
# ENV
# ============================================================

PUSHBULLET_API_KEY = os.getenv("PUSHBULLET_API_KEY")
DEVICE_SECRET = os.getenv("DEVICE_SECRET")

USERS = json.loads(os.getenv("USERS_JSON"))

# ============================================================
# GATES
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
# HELPERS
# ============================================================

def gate_is_open_now(gate_name):
    gate = next(g for g in GATES if g["name"] == gate_name)
    now = datetime.now().time()
    for rule in gate["open_hours"]:
        f = datetime.strptime(rule["from"], "%H:%M").time()
        t = datetime.strptime(rule["to"], "%H:%M").time()
        if f <= now <= t:
            return True
    return False


def send_pushbullet(title, body):
    if not PUSHBULLET_API_KEY:
        return
    try:
        requests.post(
            "https://api.pushbullet.com/v2/pushes",
            json={"type": "note", "title": title, "body": body},
            headers={"Access-Token": PUSHBULLET_API_KEY},
            timeout=5
        )
    except Exception:
        pass


def check_phone_alive():
    global PB_ALERT_SENT
    if LAST_PHONE_SEEN == 0:
        return

    silence = time.time() - LAST_PHONE_SEEN
    if silence > PHONE_TIMEOUT_SECONDS and not PB_ALERT_SENT:
        send_pushbullet(
            "⚠ Gate system alert",
            f"No phone heartbeat for {int(silence/60)} minutes"
        )
        PB_ALERT_SENT = True


# ============================================================
# ROUTES
# ============================================================

@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "ok"}), 200


@app.route("/allowed_gates", methods=["GET"])
def allowed_gates():
    check_phone_alive()
    token = request.args.get("token")

    user = next(u for u in USERS if u["token"] == token)
    allowed = user["allowed_gates"]

    if allowed == "ALL":
        return jsonify({"allowed": [g["name"] for g in GATES]}), 200

    return jsonify({"allowed": allowed}), 200


@app.route("/open", methods=["POST"])
def open_gate():
    global STATE, CURRENT_TASK, TASK_CREATED_AT

    check_phone_alive()

    if STATE != "IDLE":
        return jsonify({"error": "device busy"}), 409

    data = request.get_json()
    token = data["token"]
    gate_name = data["gate"]

    user = next(u for u in USERS if u["token"] == token)
    if user["allowed_gates"] != "ALL" and gate_name not in user["allowed_gates"]:
        return jsonify({"error": "not allowed"}), 403

    if not gate_is_open_now(gate_name):
        return jsonify({"error": "gate closed"}), 403

    gate = next(g for g in GATES if g["name"] == gate_name)

    CURRENT_TASK = {
        "task": "open",
        "gate": gate["name"],
        "phone_number": gate["phone_number"]
    }

    STATE = "PENDING"
    TASK_CREATED_AT = time.time()

    return jsonify({"status": "task_created"}), 200


@app.route("/phone_task", methods=["GET"])
def phone_task():
    global LAST_PHONE_SEEN, PB_ALERT_SENT

    if request.args.get("device_secret") != DEVICE_SECRET:
        return jsonify({"error": "unauthorized"}), 403

    LAST_PHONE_SEEN = time.time()
    PB_ALERT_SENT = False

    if STATE == "PENDING":
        return jsonify(CURRENT_TASK), 200

    return jsonify({"task": "none"}), 200


@app.route("/confirm", methods=["POST"])
def confirm():
    global STATE, LAST_RESULT, RESULT_CREATED_AT, CURRENT_TASK

    data = request.get_json()
    if data.get("device_secret") != DEVICE_SECRET:
        return jsonify({"error": "unauthorized"}), 401

    if STATE != "PENDING":
        return jsonify({"error": "no active task"}), 400

    LAST_RESULT = {
        "status": "opened" if data["status"] == "success" else "failed",
        "gate": data["gate"]
    }

    STATE = LAST_RESULT["status"].upper()
    RESULT_CREATED_AT = time.time()
    CURRENT_TASK = None

    return jsonify({"ok": True}), 200


@app.route("/status", methods=["GET"])
def status():
    global STATE, LAST_RESULT, CURRENT_TASK

    check_phone_alive()
    now = time.time()

    # טלפון לא ענה
    if STATE == "PENDING" and now - TASK_CREATED_AT > TASK_TIMEOUT:
        LAST_RESULT = {
            "status": "failed",
            "gate": CURRENT_TASK["gate"],
            "reason": "phone_timeout"
        }
        STATE = "FAILED"
        RESULT_CREATED_AT = now
        CURRENT_TASK = None

    # תוצאה זמינה
    if STATE in ("FAILED", "OPENED"):
        if now - RESULT_CREATED_AT > CLIENT_READ_TIMEOUT:
            STATE = "IDLE"
            LAST_RESULT = None
            return jsonify({"status": "ready"}), 200

        return jsonify(LAST_RESULT), 200

    if STATE == "PENDING":
        return jsonify({"status": "pending"}), 200

    return jsonify({"status": "ready"}), 200


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
