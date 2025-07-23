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

@app.route("/")
def home():
    """Root endpoint to avoid 404 errors"""
    return jsonify({
        "message": "Price Tracker API is running!",
        "endpoints": {
            "webhook": "/webhook",
            "save_telegram_id": "/save-telegram-id",
            "track_price": "/track-price",
            "telegram_login": "/telegram-login",
            "health": "/health"
        },
        "status": "healthy"
    }), 200

@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    data = request.get_json()
    print("Incoming Telegram message:", data)
    try:
        if "message" in data:
            chat_id = data["message"]["chat"]["id"]
            message_text = data["message"].get("text", "").strip()

            if message_text.lower() in ["/start", "hi", "hello"]:
                reply_text = (
                    f"👋 Hello! Welcome to Price Tracker Bot!\n\n"
                    f"🆔 Your Chat ID is: {chat_id}\n\n"
                    f"📋 Instructions:\n"
                    f"1. Copy your Chat ID above\n"
                    f"2. Go to the website\n"
                    f"3. Paste your Chat ID in the form\n"
                    f"4. Set your price alerts\n\n"
                    f"💡 You'll receive notifications here when prices drop!"
                )
            else:
                reply_text = (
                    f"📩 You said: {message_text}\n\n"
                    f"🆔 Your Chat ID is: {chat_id}\n"
                    f"💡 Use this Chat ID on the website to receive price alerts!"
                )

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
    try:
        data = request.get_json()
        telegram_id = data.get("telegram_id")
        email = data.get("email")
        
        if not telegram_id or not email:
            return jsonify({"error": "Missing telegram_id or email"}), 400
        
        # Validate telegram_id is numeric
        try:
            int(telegram_id)
        except ValueError:
            return jsonify({"error": "Invalid Telegram ID format"}), 400
        
        db.collection("users").document(email).set({
            "telegram_id": str(telegram_id),
            "email": email,
            "created_at": firestore.SERVER_TIMESTAMP
        }, merge=True)
        
        print(f"✅ Saved Telegram ID {telegram_id} for email {email}")
        return jsonify({"status": "saved"})
        
    except Exception as e:
        print(f"❌ Error saving Telegram ID: {e}")
        return jsonify({"error": "Failed to save Telegram ID"}), 500

@app.route("/track-price", methods=["POST"])
def track_price():
    try:
        data = request.get_json()
        url = data.get("product_url")
        alert_price = data.get("alert_price")
        email = data.get("email")

        if not url or not alert_price or not email:
            return jsonify({"error": "Missing required fields: product_url, alert_price, email"}), 400

        # Validate URL
        if not (url.startswith('http://') or url.startswith('https://')):
            return jsonify({"error": "Invalid URL format"}), 400
            
        if not ('flipkart.com' in url.lower() or 'amazon.in' in url.lower() or 'amazon.com' in url.lower()):
            return jsonify({"error": "Only Flipkart and Amazon URLs are supported"}), 400

        # Get user's telegram ID
        user_doc = db.collection("users").document(email).get()
        if not user_doc.exists:
            return jsonify({"error": "User not found. Please save your Telegram ID first."}), 404

        telegram_id = user_doc.to_dict().get("telegram_id")
        if not telegram_id:
            return jsonify({"error": "Telegram ID not found for this email"}), 404

        # Save tracking info
        tracking_data = {
            "email": email,
            "telegram_id": telegram_id,
            "product_url": url,
            "alert_price": float(alert_price),
            "last_checked_price": None,
            "created_at": firestore.SERVER_TIMESTAMP,
            "active": True
        }
        
        db.collection("tracked_items").document().set(tracking_data)
        
        print(f"✅ Price tracking started for {email} - Target: ₹{alert_price}")
        return jsonify({"success": True, "message": "Price tracking started successfully!"})
        
    except Exception as e:
        print(f"❌ Error setting up price tracking: {e}")
        return jsonify({"error": "Failed to set up price tracking"}), 500

@app.route("/health")
def health_check():
    return jsonify({
        "status": "healthy", 
        "service": "price-tracker-backend",
        "timestamp": firestore.SERVER_TIMESTAMP
    })

if __name__ == "__main__":
    app.run(debug=True, port=5000, host='0.0.0.0')
