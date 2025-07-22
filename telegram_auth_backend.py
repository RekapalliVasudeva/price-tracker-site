from flask import Flask, request, jsonify, redirect
import requests
import os

# Write FIREBASE_CREDENTIALS env variable to file if it exists
if os.environ.get("FIREBASE_CREDENTIALS"):
    with open("serviceAccountKey.json", "w") as f:
        f.write(os.environ["FIREBASE_CREDENTIALS"])

import firebase_admin
from firebase_admin import credentials, firestore

app = Flask(__name__)

# Environment variables
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR-BOT-TOKEN-HERE")

# Firebase initialization
if not firebase_admin._apps:
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    data = request.get_json()
    print("Incoming Telegram message:", data)
    try:
        if "message" in data:
            chat_id = data["message"]["chat"]["id"]
            message_text = data["message"].get("text", "")

            if message_text.strip().lower() in ["/start", "hi", "hello"]:
                reply_text = f"👋 Hello!\nYour Chat ID is: {chat_id}\nPaste this Chat ID in the website to receive product alerts."
            else:
                reply_text = f"📩 You said: {message_text}\nYour Chat ID is: {chat_id}"

            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": chat_id, "text": reply_text}
            )
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        print("Webhook Error:", e)
        return jsonify({"error": "Webhook processing failed"}), 500

@app.route("/telegram-login")
def telegram_login():
    return redirect("https://t.me/pricealert_ai_bot")

@app.route("/save-telegram-id", methods=["POST"])
def save_telegram_id():
    data = request.get_json()
    telegram_id = data.get("telegram_id")
    email = data.get("email")
    if not telegram_id or not email:
        return jsonify({"error": "Missing fields"}), 400
    
    db.collection("users").document(email).set({"telegram_id": telegram_id}, merge=True)
    return jsonify({"status": "saved"})

@app.route("/track-price", methods=["POST"])
def track_price():
    data = request.get_json()
    url = data.get("product_url")
    alert_price = data.get("alert_price")
    email = data.get("email")

    if not url or not alert_price or not email:
        return jsonify({"error": "Missing required fields"}), 400

    user_doc = db.collection("users").document(email).get()
    if not user_doc.exists:
        return jsonify({"error": "User not found"}), 404

    telegram_id = user_doc.to_dict().get("telegram_id")
    db.collection("tracked_items").document().set({
        "email": email,
        "telegram_id": telegram_id,
        "product_url": url,
        "alert_price": float(alert_price),
        "last_checked_price": None
    })
    return jsonify({"success": True, "message": "Tracking started"})

@app.route("/health")
def health_check():
    return jsonify({"status": "healthy", "service": "price-tracker-backend"})

if __name__ == "__main__":
    app.run(debug=True, port=5000, host='0.0.0.0')
