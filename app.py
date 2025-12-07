from flask import Flask, request, jsonify
import requests
import os

app = Flask(__name__)

PUSHBULLET_API_KEY = os.getenv("PUSHBULLET_API_KEY")

print("🔥 Flask server is starting...")

@app.route('/', methods=['GET'])
def home():
    return "✅ Open Gates Server Running"

@app.route('/open', methods=['POST'])
def open_gate():
    data = request.get_json()

    gate = data.get('gate')
    device = data.get('device')

    if not gate:
        return jsonify({"error": "gate is required"}), 400

    if not PUSHBULLET_API_KEY:
        return jsonify({"error": "Missing PUSHBULLET_API_KEY"}), 500

    push_data = {
        "type": "note",
        "title": "Open Gate",
        "body": f"gate={gate};device={device}"
    }

    headers = {
        'Access-Token': PUSHBULLET_API_KEY,
        'Content-Type': 'application/json',
    }

    response = requests.post(
        'https://api.pushbullet.com/v2/pushes',
        json=push_data,
        headers=headers
    )

    if response.status_code == 200:
        return jsonify({"status": "sent"}), 200
    else:
        return jsonify({"error": response.text}), 500


# ---------------------------
# MAIN – required for Railway
# ---------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
