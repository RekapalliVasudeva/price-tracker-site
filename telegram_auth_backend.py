from flask import Flask, redirect, request, jsonify
import firebase_admin
from firebase_admin import credentials, firestore
import os

app = Flask(__name__)

# Initialize Firebase
if not firebase_admin._apps:
    cred = credentials.Certificate("serviceAccountKey.json")  # Make sure this file is present
    firebase_admin.initialize_app(cred)

db = firestore.client()

# 1. Telegram Login Route
@app.route("/telegram-login")
def telegram_login():
    return redirect("https://t.me/YourBotUsername")  # Replace with your bot's username

# 2. Save Telegram ID
@app.route("/save-telegram-id", methods=["POST"])
def save_telegram_id():
    data = request.get_json()
    telegram_id = data.get("telegram_id")
    email = data.get("email")

    if not telegram_id or not email:
        return jsonify({"error": "Missing fields"}), 400

    # Save to Firestore
    doc_ref = db.collection("users").document(email)
    doc_ref.set({"telegram_id": telegram_id}, merge=True)

    return jsonify({"status": "saved"})

# 3. Track Product Price Route
@app.route("/track-price", methods=["POST"])
def track_price():
    data = request.get_json()
    product_url = data.get("product_url")
    alert_price = data.get("alert_price")
    email = data.get("email")

    if not product_url or not alert_price or not email:
        return jsonify({"error": "Missing required fields"}), 400

    # Fetch user's Telegram ID from Firestore
    user_doc = db.collection("users").document(email).get()
    if not user_doc.exists:
        return jsonify({"error": "User not found"}), 404

    telegram_id = user_doc.to_dict().get("telegram_id")

    # Save price tracking record
    track_ref = db.collection("tracked_items").document()
    track_ref.set({
        "email": email,
        "telegram_id": telegram_id,
        "product_url": product_url,
        "alert_price": float(alert_price),
        "last_checked_price": None
    })

    return jsonify({"success": True, "message": "Tracking started"})

# App runner
if __name__ == "__main__":
    app.run(debug=True, port=5000)
