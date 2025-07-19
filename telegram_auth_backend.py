from flask import Flask, redirect, request, jsonify
import firebase_admin
from firebase_admin import credentials, firestore
import requests
import os

app = Flask(__name__)

# === [1] FIREBASE SETUP ===
if not firebase_admin._apps:
    cred = credentials.Certificate("serviceAccountKey.json")  # Adjust path if needed
    firebase_admin.initialize_app(cred)

db = firestore.client()

# === [2] TELEGRAM LOGIN REDIRECT ===
@app.route("/telegram-login")
def telegram_login():
    return redirect("https://t.me/pricealert_ai_bot")  # Replace with your actual bot username

# === [3] SAVE TELEGRAM ID & EMAIL ===
@app.route("/save-telegram-id", methods=["POST"])
def save_telegram_id():
    data = request.get_json()
    telegram_id = data.get("telegram_id")
    email = data.get("email")

    if not telegram_id or not email:
        return jsonify({"error": "Missing fields"}), 400

    doc_ref = db.collection("users").document(email)
    doc_ref.set({"telegram_id": telegram_id}, merge=True)

    return jsonify({"status": "saved"})

# === [4] TRACK PRICE ===
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

    track_ref = db.collection("tracked_items").document()
    track_ref.set({
        "email": email,
        "telegram_id": telegram_id,
        "product_url": product_url,
        "alert_price": float(alert_price),
        "last_checked_price": None
    })

    return jsonify({"success": True, "message": "Tracking started"})

# === [5] TELEGRAM WEBHOOK HANDLER ===
BOT_TOKEN = "8169575352:AAFIk2ip4GSAQKFlISa90DeT492y2LuIbas"  # Replace with your actual token

@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    data = request.get_json()
    print("Incoming Telegram message:", data)

    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        message_text = data["message"].get("text", "")

        reply_text = f"Hello! You said: {message_text}"
        send_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(send_url, json={"chat_id": chat_id, "text": reply_text})

    return jsonify({"status": "ok"})

# === [6] LOCAL TEST MODE (not used in Render) ===
if __name__ == "__main__":
    app.run(debug=True, port=5000)
