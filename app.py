from flask import Flask, request, jsonify
import requests
import os

app = Flask(__name__)

# API KEY של Pushbullet
PUSHBULLET_API_KEY = os.getenv("PUSHBULLET_API_KEY")


# ------------------------
# HEALTH CHECK (Railway)
# ------------------------
@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "ok"}), 200


# ------------------------
# OPEN GATE
# ------------------------
@app.route("/open", methods=["POST"])
def open_gate():
    data = request.get_json()

    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    gate = data.get("gate")
    device = data.get("device")

    if not gate:
        return jsonify({"error": "gate is required"}), 400

    if not PUSHBULLET_API_KEY:
        return jsonify({"error": "Server missing PUSHBULLET_API_KEY"}), 500

    # הודעה ל־Pushbullet
    push_payload = {
        "type": "note",
        "title": "Open Gate",
        "body": f"gate={gate};device={device}"
    }

    headers = {
        "Access-Token": PUSHBULLET_API_KEY,
        "Content-Type": "application/json"
    }

    try:
        pb_response = requests.post(
            "https://api.pushbullet.com/v2/pushes",
            json=push_payload,
            headers=headers,
            timeout=5
        )
    except Exception as e:
        return jsonify({"error": f"Pushbullet error: {str(e)}"}), 500

    if pb_response.status_code == 200:
        return jsonify({"status": "sent"}), 200
    else:
        return jsonify({"error": pb_response.text}), 500


# ------------------------
# LOCAL RUN ONLY
# ------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
