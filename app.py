from flask import Flask, request, jsonify
import os, time, json
from datetime import datetime
import redis

app = Flask(__name__)

# =========================
# ENV
# =========================
DEVICE_SECRET = os.getenv("DEVICE_SECRET")
REDIS_URL = os.getenv("REDIS_URL")

USERS_JSON = os.getenv("USERS_JSON")
if not USERS_JSON:
    raise ValueError("USERS_JSON missing")
USERS = json.loads(USERS_JSON)

rdb = redis.from_url(REDIS_URL, decode_responses=True)

# =========================
# CONFIG
# =========================
TASK_TTL = 20          # ניקוי אוטומטי
CLIENT_TIMEOUT = 10    # אחרי 10 שניות – כישלון

K_TASK = "gate:task"
K_LOCK = "gate:lock"

# =========================
# GATES
# =========================
GATES = [
    {"name": "Main", "phone_number": "972505471743", "open_hours": [{"from":"00:00","to":"23:59"}]},
    {"name": "Gay", "phone_number": "972503403742", "open_hours": [{"from":"00:00","to":"23:59"}]},
    {"name": "Enter", "phone_number": "972503924081", "open_hours": [{"from":"05:20","to":"21:00"}]},
    {"name": "Exit", "phone_number": "972503924106", "open_hours": [{"from":"05:20","to":"21:00"}]},
    {"name": "EinCarmel", "phone_number": "972542688743", "open_hours": [{"from":"00:00","to":"23:59"}]},
    {"name": "Almagor", "phone_number": "972503817647", "open_hours": [{"from":"00:00","to":"23:59"}]},
]

def get_gate(name):
    return next((g for g in GATES if g["name"] == name), None)

def gate_is_open_now(name):
    gate = get_gate(name)
    if not gate:
        return False
    now = datetime.now().time()
    for r in gate["open_hours"]:
        if datetime.strptime(r["from"], "%H:%M").time() <= now <= datetime.strptime(r["to"], "%H:%M").time():
            return True
    return False

def acquire_lock():
    return rdb.set(K_LOCK, "1", nx=True, ex=TASK_TTL)

def clear_all():
    rdb.delete(K_TASK)
    rdb.delete(K_LOCK)

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

    if user["allowed_gates"] == "ALL":
        return jsonify({"allowed": [g["name"] for g in GATES]}), 200
    return jsonify({"allowed": user["allowed_gates"]}), 200

@app.route("/open", methods=["POST"])
def open_gate():
    data = request.get_json(force=True)
    token = data.get("token")
    gate_name = data.get("gate")

    user = next((u for u in USERS if u["token"] == token), None)
    if not user:
        return jsonify({"error": "invalid token"}), 401

    if user["allowed_gates"] != "ALL" and gate_name not in user["allowed_gates"]:
        return jsonify({"error": "not allowed"}), 403

    if not gate_is_open_now(gate_name):
        return jsonify({"error": "gate closed"}), 403

    gate = get_gate(gate_name)
    if not gate:
        return jsonify({"error": "unknown gate"}), 400

    if not acquire_lock():
        return jsonify({"error": "device busy"}), 409

    task = {
        "task": "open",
        "gate": gate["name"],
        "phone_number": gate["phone_number"],
        "created_at": time.time()
    }

    rdb.setex(K_TASK, TASK_TTL, json.dumps(task))
    return jsonify({"status": "task_created"}), 200

@app.route("/phone_task", methods=["GET"])
def phone_task():
    if request.args.get("device_secret") != DEVICE_SECRET:
        return jsonify({"error": "unauthorized"}), 403

    task = rdb.get(K_TASK)
    if not task:
        return jsonify({"task": "none"}), 200

    return jsonify(json.loads(task)), 200

@app.route("/confirm", methods=["POST"])
def confirm():
    data = request.get_json(force=True) or {}
    if data.get("device_secret") != DEVICE_SECRET:
        return jsonify({"error": "unauthorized"}), 401

    task_json = rdb.get(K_TASK)
    if not task_json:
        return jsonify({"error": "no active task"}), 400

    task = json.loads(task_json)

    status = (data.get("status") or "").lower()
    if status not in ("success", "failed"):
        return jsonify({"error": "invalid status"}), 400

    task["status"] = "opened" if status == "success" else "failed"

    # שומרים חזרה – לא מוחקים
    rdb.setex(K_TASK, TASK_TTL, json.dumps(task))

    return jsonify({"ok": True}), 200

@app.route("/status", methods=["GET"])
def status():
    now = time.time()

    # 1) יש תוצאה מוכנה
    res_json = rdb.get(K_RESULT)
    if res_json:
        result = json.loads(res_json)
        # הלקוח קרא → סוגרים הכל
        rdb.delete(K_RESULT)
        rdb.delete(K_TASK)
        rdb.delete(K_LOCK)
        return jsonify(result), 200

    # 2) יש משימה פעילה
    task_json = rdb.get(K_TASK)
    if task_json:
        task = json.loads(task_json)
        created_at = task.get("created_at", 0)

        # עברו יותר מ־10 שניות בלי confirm → כישלון
        if now - created_at > 10:
            result = {
                "status": "failed",
                "gate": task["gate"],
                "reason": "phone_timeout"
            }
            rdb.delete(K_TASK)
            rdb.delete(K_LOCK)
            rdb.setex(K_RESULT, RESULT_TTL, json.dumps(result))
            return jsonify(result), 200

        return jsonify({"status": "pending"}), 200

    # 3) אין כלום → ready
    return jsonify({"status": "ready"}), 200

# =========================
# RUN
# =========================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
