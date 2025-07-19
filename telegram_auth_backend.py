from flask import Flask, request, jsonify, redirect
import requests
import firebase_admin
from firebase_admin import credentials, firestore

app = Flask(__name__)

# === CONFIG ===
FIREBASE_CERT_PATH = "serviceAccountKey.json"  # Ensure it's in Render secrets
BOT_TOKEN = "8169575352:AAFIk2ip4GSAQKFlISa90DeT492y2LuIbas"

# === Firebase Initialization ===
if not firebase_admin._apps:
    cred = credentials.Certificate(FIREBASE_CERT_PATH)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# === 1. Telegram Webhook Route ===
@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    data = request.get_json()
    print("Incoming Telegram message:", data)

    try:
        if "message" in data:
            chat_id = data["message"]["chat"]["id"]
            message_text = data["message"].get("text", "")

            # Bot reply logic
            if message_text.lower() in ["/start", "hi", "hello"]:
                reply_text = "👋 Hello! I’m your Price Tracker bot.\nUse the website to save your Telegram ID and track product prices."
            else:
                reply_text = f"📩 You said: {message_text}"

            # Send reply to user
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": chat_id, "text": reply_text}
            )

        return jsonify({"status": "ok"}), 200

    except Exception as e:
        print("Webhook Error:", e)
        return jsonify({"error": "Webhook processing failed"}), 500

# === 2. Telegram Login Redirect ===
@app.route("/telegram-login")
def telegram_login():
    return redirect("https://t.me/pricealert_ai_bot")  # Replace with your actual bot

# === 3. Save Telegram ID ===
@app.route("/save-telegram-id", methods=["POST"])
def save_telegram_id():
    data = request.get_json()
    telegram_id = data.get("telegram_id")
    email = data.get("email")

    if not telegram_id or not email:
        return jsonify({"error": "Missing fields"}), 400

    # Save Telegram ID under user's email
    doc_ref = db.collection("users").document(email)
    doc_ref.set({"telegram_id": telegram_id}, merge=True)

    return jsonify({"status": "saved"})

# === 4. Track Product Price ===
@app.route("/track-price", methods=["POST"])
def track_price():
    data = request.get_json()
    product_url = data.get("product_url")
    alert_price = data.get("alert_price")
    email = data.get("email")

    if not product_url or not alert_price or not email:
        return jsonify({"error": "Missing required fields"}), 400

    user_doc = db.collection("users").document(email).get()
    if not user_doc.exists:
        return jsonify({"error": "User not found"}), 404

    telegram_id = user_doc.to_dict().get("telegram_id")

    # Save tracking info
    track_ref = db.collection("tracked_items").document()
    track_ref.set({
        "email": email,
        "telegram_id": telegram_id,
        "product_url": product_url,
        "alert_price": float(alert_price),
        "last_checked_price": None
    })

    return jsonify({"success": True, "message": "Tracking started"})

# === App Runner (used in local dev) ===
if __name__ == "__main__":
    app.run(debug=True, port=5000)
