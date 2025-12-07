from flask import Flask, request, jsonify
import requests
import os

app = Flask(__name__)

PUSHBULLET_API_KEY = os.getenv("PUSHBULLET_API_KEY")  # שים במשתנים ב־Railway
print("🔥 Flask server is starting...")


# ------------------------
# ROOT ROUTE
# ------------------------
@app.route('/', methods=['GET'])
def home():
    print("✅ GET / called")
    return "✅ Open Gates Server Running"


# ------------------------
# OPEN GATE ROUTE
# ------------------------
@app.route('/open', methods=['POST'])
def open_gate():
    data = request.get_json()
    gate = data.get('gate')

    if not gate:
        return jsonify({"error": "gate is required"}), 400

    push_data = {
        "type": "note",
        "title": "Open Gate",
        "body": f"gate={gate}"
    }

    headers = {
        'Access-Token': PUSHBULLET_API_KEY,
        'Content-Type': 'application/json',
    }

    response = requests.post('https://api.pushbullet.com/v2/pushes',
                             json=push_data,
                             headers=headers)

    if response.status_code == 200:
        return jsonify({"status": "sent"}), 200
    else:
        return jsonify({"error": response.text}), 500


# ------------------------
# LOCAL DEV MODE
# ------------------------
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
