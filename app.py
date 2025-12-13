from flask import Flask, request, jsonify
import os, json, time
import redis

app = Flask(__name__)

REDIS_URL = os.getenv("REDIS_URL")
DEVICE_SECRET = os.getenv("DEVICE_SECRET")

rdb = redis.from_url(REDIS_URL, decode_responses=True)

K_TASK = "gate:task"

@app.route("/open", methods=["POST"])
def open_gate():
    data = request.get_json(force=True)
    task = {
        "gate": data.get("gate"),
        "created_at": time.time()
    }

    print("OPEN: writing task", task, flush=True)
    rdb.set(K_TASK, json.dumps(task))

    print("OPEN: redis now:", rdb.get(K_TASK), flush=True)
    return jsonify({"status": "ok"}), 200


@app.route("/phone_task", methods=["GET"])
def phone_task():
    secret = request.args.get("device_secret")
    print("PHONE_TASK: secret =", secret, flush=True)

    if secret != DEVICE_SECRET:
        return jsonify({"error": "unauthorized"}), 403

    raw = rdb.get(K_TASK)
    print("PHONE_TASK: read =", raw, flush=True)

    if not raw:
        return jsonify({"task": "none"}), 200

    return jsonify(json.loads(raw)), 200


@app.route("/clear", methods=["POST"])
def clear():
    rdb.delete(K_TASK)
    print("CLEAR: task deleted", flush=True)
    return jsonify({"ok": True}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
