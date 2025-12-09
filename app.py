from flask import Flask, request, jsonify
import requests
import os
import json
import time

app = Flask(__name__)

PUSHBULLET_API_KEY = os.getenv("PUSHBULLET_API_KEY")

# -----------------------------
# Helpers
# -----------------------------
def load_json(filename):
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


# -----------------------------
# HEALTH CHECK
# -----------------------------
@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "ok"}), 200


# -----------------------------
# GET ALLOWED GATES FOR USER
# -----------------------------
@app.route("/allowed_gates", methods=["POST"])
def allowed_gates():
    data = request.get_json()
    if not data or "user" not in data:
        return jsonify({"error": "user required"}), 400

    user = data["user"]

    users = load_json("users.json")
    if user not in users:
        return jsonify({"error": "unknown user"}), 403

    gates = load_json("gates.json")

    return jsonify({
        "user": user,
        "allowed_gates": users[user]["allowed"]
    }), 200


# -----------------------------
# OPEN GATE REQUEST
# -----------------------------
@app.route("/open", methods=["POST"])
def open_gate():
    data = request.get_json()

    if not data or "user" not in data or "gate" not in data:
        return jsonify({"error": "user and gate required"}), 400

    user = data["user"]
    gate = data["gate"]

    users = load_json("users.json")
    gates = load_json("gates.json")
    status = load_json("device_status.json")

    # ---- בדיקת משתמש ----
    if user not in users:
        return jsonify({"error": "unknown user"}), 403

    # ---- בדיקת הרשאה ----
    if gate not in users[user]["allowed"]:
        return jsonify({"error": "not allowed to open this gate"}), 403

    # ---- בדיקת שער זמין ----
    if gate not in gates:
        return jsonify({"error": "unknown gate"}), 400

    # ---- בדיקת שעות ----
    if "hours" in gates[gate]:
        hours = gates[gate]["hours"]
        now = time.strftime("%H:%M")

        if not (hours["from"] <= now <= hours["to"]):
            return jsonify({"error": "gate is closed at this hour"}), 403

    # ---- האם הטלפון עסוק ----
    if status["busy"]:
        return jsonify({"status": "busy", "message": "device is handling previous request"}), 409

    # ---- סימון עסוק ----
    status["busy"] = True
    status["current_gate"] = gate
    status["waiting_client"] = user
    status["timestamp"] = time.time()
    save_json("device_status.json", status)

    # ---- שליחת פקודה לטלפון ----
    push_data = {
        "type": "note",
        "title": "Open Gate",
        "body": f"gate={gate}"
    }

    headers = {
        "Access-Token": PUSHBULLET_API_KEY,
        "Content-Type": "application/json"
    }

    try:
        requests.post(
            "https://api.pushbullet.com/v2/pushes",
            json=push_data,
            headers=headers,
            timeout=5
        )
    except Exception:
        status["busy"] = False
        save_json("device_status.json", status)
        return jsonify({"error": "failed to send push notification"}), 500

    # ---- תשובה מיידית ללקוח ----
    return jsonify({"status": "accepted", "message": "opening request sent"}), 200


# -----------------------------
# RECEIVE CONFIRMATION FROM PHONE
# -----------------------------
@app.route("/confirm", methods=["POST"])
def confirm():
    data = request.get_json()
    print("CONFIRM RECEIVED:", data, flush=True)  # כדי שיראה בלוג Railway בזמן אמת

    if not data or "status" not in data or "gate" not in data:
        return jsonify({"error": "status and gate required"}), 400

    phone_status = data["status"]   # success / failed
    gate = data["gate"]

    # טען סטטוס
    status = load_json("device_status.json")

    if not status["busy"]:
        return jsonify({"error": "no active request"}), 400

    # ודא שהטלפון מאשר את השער הנכון
    if status["current_gate"] != gate:
        return jsonify({"error": "gate mismatch"}), 400

    user = status["waiting_client"]

    # אפס סטטוס
    status["busy"] = False
    status["current_gate"] = None
    status["waiting_client"] = None
    status["timestamp"] = None
    save_json("device_status.json", status)

    # תשובה
    if phone_status == "success":
        return jsonify({"status": "gate_opened", "gate": gate, "user": user}), 200
    else:
        return jsonify({"status": "failed", "gate": gate, "user": user}), 200


# -----------------------------
# TIMEOUT CHECK (optional call)
# -----------------------------
@app.route("/check_timeout", methods=["GET"])
def check_timeout():
    status = load_json("device_status.json")

    if not status["busy"]:
        return jsonify({"status": "idle"}), 200

    elapsed = time.time() - status["timestamp"]
    if elapsed > 30:
        # reset
        status["busy"] = False
        status["current_gate"] = None
        status["waiting_client"] = None
        status["timestamp"] = None
        save_json("device_status.json", status)
        return jsonify({"status": "timeout", "message": "operation canceled"}), 408

    return jsonify({"status": "waiting", "remaining": 30 - elapsed}), 200



# -----------------------------
# RUN LOCAL
# -----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print("PORT =", port)
    app.run(host="0.0.0.0", port=port)
