from flask import Flask, request, jsonify
import os, time, json
from datetime import datetime
import requests
import redis

app = Flask(__name__)

# =========================
# ENV
# =========================
DEVICE_SECRET = os.getenv("DEVICE_SECRET")
PUSHBULLET_API_KEY = os.getenv("PUSHBULLET_API_KEY")  # נשאר לעתיד
REDIS_URL = os.getenv("REDIS_URL")  # מגיע מ-Railway Redis service

USERS_JSON = os.getenv("USERS_JSON")
if not USERS_JSON:
    raise ValueError("USERS_JSON missing from environment")
USERS = json.loads(USERS_JSON)

rdb = redis.from_url(REDIS_URL, decode_responses=True)

# =========================
# CONFIG
# =========================
TASK_TTL = 20          # טלפון חייב לקחת/לבצע בתוך 20 שניות
RESULT_TTL = 10        # ללקוח יש 10 שניות לקרוא תוצאה
LOCK_TTL = 20

# Redis keys
K_TASK = "gate:task"
K_RESULT = "gate:result"
K_LOCK = "gate:lock"
K_LAST_PHONE = "gate:last_phone_seen"  # אופציונלי
K_PB_SENT = "gate:pb_alert_sent"       # אופציונלי

# =========================
# Gates configuration
# =========================
GATES = [
    {"name": "Main",      "phone_number": "972505471743", "open_hours": [{"from":"00:00","to":"23:59"}]},
    {"name": "Gay",       "phone_number": "972503403742", "open_hours": [{"from":"00:00","to":"23:59"}]},
    {"name": "Enter",     "phone_number": "972503924081", "open_hours": [{"from":"05:20","to":"21:00"}]},
    {"name": "Exit",      "phone_number": "972503924106", "open_hours": [{"from":"05:20","to":"21:00"}]},
    {"name": "EinCarmel", "phone_number": "972542688743", "open_hours": [{"from":"00:00","to":"23:59"}]},
    {"name": "Almagor",   "phone_number": "972503817647", "open_hours": [{"from":"00:00","to":"23:59"}]},
]

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

def get_gate(gate_name):
    return next((g for g in GATES if g["name"] == gate_name), None)

def set_result(status, gate, reason=None):
    payload = {"status": status, "gate": gate}
    if reason:
        payload["reason"] = reason
    rdb.setex(K_RESULT, RESULT_TTL, json.dumps(payload))

def clear_task_and_lock():
    rdb.delete(K_TASK)
    rdb.delete(K_LOCK)

def acquire_lock():
    # SET key value NX EX LOCK_TTL  => מחזיר True/False
    return rdb.set(K_LOCK, "1", nx=True, ex=LOCK_TTL)

# =========================
# ROUTES
# =========================
@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "ok"}), 200

@app.route("/allowed_gates", methods=["GET"])
def allowed_gates():
    token = request.args.get("token")
    user = next((u for u in USERS if u["token"] == token), None)
    if not user:
        return jsonify({"error": "invalid token"}), 401

    allowed = user["allowed_gates"]
    if allowed == "ALL":
        return jsonify({"allowed": [g["name"] for g in GATES]}), 200
    return jsonify({"allowed": allowed}), 200

@app.route("/open", methods=["POST"])
def open_gate():
    data = request.get_json(force=True) or {}
    token = data.get("token")
    gate_name = data.get("gate")

    if not token or not gate_name:
        return jsonify({"error": "token and gate required"}), 400

    user = next((u for u in USERS if u["token"] == token), None)
    if not user:
        return jsonify({"error": "invalid token"}), 401

    allowed = user["allowed_gates"]
    if allowed != "ALL" and gate_name not in allowed:
        return jsonify({"error": "not allowed"}), 403

    if not gate_is_open_now(gate_name):
        return jsonify({"error": "gate closed now"}), 403

    gate_obj = get_gate(gate_name)
    if not gate_obj:
        return jsonify({"error": "unknown gate"}), 400

    # אם כבר יש תוצאה שמחכה ללקוח לקרוא - תחזיר busy (או תן ללקוח לקרוא /status)
    if rdb.exists(K_RESULT):
        return jsonify({"error": "busy_result_waiting"}), 409

    # מנעול: מונע שתי פתיחות במקביל
    if not acquire_lock():
        return jsonify({"error": "device busy"}), 409

    task = {
        "task": "open",
        "gate": gate_obj["name"],
        "phone_number": gate_obj["phone_number"]
    }
    rdb.setex(K_TASK, TASK_TTL, json.dumps(task))

    return jsonify({"status": "task_created"}), 200

@app.route("/phone_task", methods=["GET"])
def phone_task():
    secret = request.args.get("device_secret")
    if secret != DEVICE_SECRET:
        return jsonify({"error": "unauthorized"}), 403

    # heartbeat
    rdb.set(K_LAST_PHONE, str(int(time.time())))

    task_json = rdb.get(K_TASK)
    if not task_json:
        return jsonify({"task": "none"}), 200

    return jsonify(json.loads(task_json)), 200

@app.route("/confirm", methods=["POST"])
def confirm():
    data = request.get_json(force=True) or {}
    if data.get("device_secret") != DEVICE_SECRET:
        return jsonify({"error": "unauthorized"}), 401

    gate = data.get("gate")
    status = (data.get("status") or "").lower()
    if not gate or status not in ("success", "failed"):
        return jsonify({"error": "invalid payload"}), 400

    # אם אין task כבר - עדיין נקבל confirm מאוחר; נשים result בכל זאת כדי שהלקוח ידע
    final_status = "opened" if status == "success" else "failed"
    set_result(final_status, gate)

    clear_task_and_lock()
    return jsonify({"ok": True}), 200

@app.route("/status", methods=["GET"])
def status():
    # 1) אם יש תוצאה - מחזירים אותה (היא תיעלם לבד תוך RESULT_TTL)
    res_json = rdb.get(K_RESULT)
    if res_json:
        return jsonify(json.loads(res_json)), 200

    # 2) אם יש משימה - עדיין pending
    task_json = rdb.get(K_TASK)
    if task_json:
        return jsonify({"status": "pending"}), 200

    # 3) אין משימה ואין תוצאה => ready (וכדי שלא תישאר נעילה תקועה, מנקים lock אם יש)
    rdb.delete(K_LOCK)
    return jsonify({"status": "ready"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
