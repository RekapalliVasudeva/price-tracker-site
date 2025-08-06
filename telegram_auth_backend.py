from flask import Flask, request, jsonify, redirect
from flask_cors import CORS
import requests
import os
import time
from bs4 import BeautifulSoup

# Write FIREBASE_CREDENTIALS env variable to file if it exists
if os.environ.get("FIREBASE_CREDENTIALS"):
    with open("serviceAccountKey.json", "w") as f:
        f.write(os.environ["FIREBASE_CREDENTIALS"])

import firebase_admin
from firebase_admin import credentials, firestore

app = Flask(__name__)
CORS(app)  # Enable CORS for frontend-backend communication

# Environment variables
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR-BOT-TOKEN-HERE")

# Firebase initialization
if not firebase_admin._apps:
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

# Security headers
@app.after_request
def add_security_headers(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = "frame-ancestors 'none';"
    return response

def safe_scrape_price(url):
    """Safely scrape price with comprehensive error handling"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        
        current_price = None
        product_title = None
        
        if "flipkart.com" in url.lower():
            current_price, product_title = extract_flipkart_data(soup)
        elif "amazon.in" in url.lower() or "amazon.com" in url.lower():
            current_price, product_title = extract_amazon_data(soup)
        else:
            raise ValueError("Unsupported website")
            
        return {
            "success": True,
            "current_price": current_price,
            "product_title": product_title,
            "error": None
        }
        
    except requests.exceptions.HTTPError as e:
        return {"success": False, "error": f"HTTP Error {e.response.status_code}: Page not accessible"}
    except requests.exceptions.ConnectionError:
        return {"success": False, "error": "Network connection failed"}
    except requests.exceptions.Timeout:
        return {"success": False, "error": "Request timed out"}
    except Exception as e:
        return {"success": False, "error": f"Scraping error: {str(e)}"}

def extract_flipkart_data(soup):
    """Extract price and title from Flipkart"""
    price_selectors = [
        "div._30jeq3", "div._1_WHN1", "div._3I9_wc", "div._25b18c", "div._16Jk6d"
    ]
    title_selectors = ["span.B_NuCI", "h1.yhB1nd", "span.yhB1nd"]
    
    current_price = None
    product_title = None
    
    for selector in price_selectors:
        try:
            price_tag = soup.find("div", {"class": selector})
            if price_tag:
                price_text = price_tag.text.replace("₹", "").replace(",", "").strip()
                price_numbers = ''.join(filter(str.isdigit, price_text.split('.')))
                if price_numbers:
                    current_price = float(price_numbers)
                    break
        except (AttributeError, ValueError):
            continue
    
    for selector in title_selectors:
        try:
            title_tag = soup.find("span", {"class": selector}) or soup.find("h1", {"class": selector})
            if title_tag:
                product_title = title_tag.text.strip()[:100]
                break
        except AttributeError:
            continue
    
    return current_price, product_title

def extract_amazon_data(soup):
    """Extract price and title from Amazon"""
    price_selectors = [
        "#priceblock_ourprice", "#priceblock_dealprice", ".a-price-whole",
        "#price_inside_buybox", ".a-offscreen", "#corePrice_feature_div .a-price .a-offscreen"
    ]
    title_selectors = ["#productTitle", "h1.a-size-large", ".product-title"]
    
    current_price = None
    product_title = None
    
    for selector in price_selectors:
        try:
            price_tag = soup.select_one(selector)
            if price_tag:
                price_text = price_tag.text.replace("₹", "").replace(",", "").strip()
                price_numbers = ''.join(filter(str.isdigit, price_text.split('.')))
                if price_numbers:
                    current_price = float(price_numbers)
                    break
        except (AttributeError, ValueError):
            continue
    
    for selector in title_selectors:
        try:
            title_tag = soup.select_one(selector)
            if title_tag:
                product_title = title_tag.text.strip()[:100]
                break
        except AttributeError:
            continue
    
    return current_price, product_title

@app.route("/")
def home():
    """Root endpoint with API documentation"""
    return jsonify({
        "message": "Price Tracker API is running!",
        "status": "healthy",
        "endpoints": {
            "webhook": "/webhook",
            "save_telegram_id": "/save-telegram-id", 
            "track_price": "/track-price",
            "check_price_now": "/check-price-now",
            "health": "/health"
        },
        "supported_sites": ["flipkart.com", "amazon.in", "amazon.com"]
    }), 200

@app.route("/check-price-now", methods=["POST"])
def check_price_now():
    """Instant price check endpoint"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No data provided"}), 400
            
        url = data.get("product_url")
        if not url:
            return jsonify({"success": False, "error": "Product URL is required"}), 400
        
        if not (url.startswith('http://') or url.startswith('https://')):
            return jsonify({"success": False, "error": "Invalid URL format"}), 400
        
        result = safe_scrape_price(url)
        
        if result["success"]:
            return jsonify({
                "success": True,
                "current_price": result["current_price"],
                "product_title": result["product_title"],
                "message": "Price fetched successfully"
            })
        else:
            return jsonify({"success": False, "error": result["error"]}), 400
            
    except Exception as e:
        print(f"❌ Error in check_price_now: {e}")
        return jsonify({"success": False, "error": "Internal server error"}), 500

@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    """Enhanced Telegram webhook"""
    try:
        data = request.get_json()
        print("Incoming Telegram message:", data)
        
        if not data or "message" not in data:
            return jsonify({"status": "ok"}), 200
            
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

        try:
            response = requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": chat_id, "text": reply_text},
                timeout=10
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"Failed to send Telegram message: {e}")
            
        return jsonify({"status": "ok"}), 200
        
    except Exception as e:
        print("Webhook Error:", e)
        return jsonify({"error": "Webhook processing failed"}), 500

@app.route("/telegram-login")
def telegram_login():
    return redirect("https://t.me/pricealert_ai_bot")

@app.route("/save-telegram-id", methods=["POST"])
def save_telegram_id():
    """Enhanced save Telegram ID with validation"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
            
        telegram_id = data.get("telegram_id")
        email = data.get("email")
        
        if not telegram_id or not email:
            return jsonify({"error": "Both telegram_id and email are required"}), 400
        
        try:
            int(telegram_id)
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid Telegram ID format"}), 400
        
        if "@" not in email or "." not in email:
            return jsonify({"error": "Invalid email format"}), 400
        
        try:
            doc_ref = db.collection("users").document(email)
            doc_ref.set({
                "telegram_id": str(telegram_id),
                "email": email,
                "created_at": firestore.SERVER_TIMESTAMP,
                "last_updated": firestore.SERVER_TIMESTAMP
            }, merge=True)
            
            print(f"✅ Saved Telegram ID {telegram_id} for email {email}")
            return jsonify({"status": "saved"})
            
        except Exception as db_error:
            print(f"Database error: {db_error}")
            return jsonify({"error": "Failed to save to database"}), 500
        
    except Exception as e:
        print(f"❌ Error saving Telegram ID: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route("/track-price", methods=["POST"])
def track_price():
    """Enhanced price tracking setup"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
            
        url = data.get("product_url")
        alert_price = data.get("alert_price")
        email = data.get("email")

        if not url or not alert_price or not email:
            return jsonify({"error": "Missing required fields"}), 400

        if not (url.startswith('http://') or url.startswith('https://')):
            return jsonify({"error": "Invalid URL format"}), 400
            
        if not ('flipkart.com' in url.lower() or 'amazon.in' in url.lower() or 'amazon.com' in url.lower()):
            return jsonify({"error": "Only Flipkart and Amazon URLs are supported"}), 400

        try:
            alert_price = float(alert_price)
            if alert_price <= 0:
                return jsonify({"error": "Alert price must be greater than 0"}), 400
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid alert price format"}), 400

        try:
            user_doc = db.collection("users").document(email).get()
            if not user_doc.exists:
                return jsonify({"error": "User not found. Please save your Telegram ID first."}), 404

            user_data = user_doc.to_dict()
            telegram_id = user_data.get("telegram_id")
            
            if not telegram_id:
                return jsonify({"error": "Telegram ID not found for this email"}), 404

        except Exception as db_error:
            print(f"Database read error: {db_error}")
            return jsonify({"error": "Failed to retrieve user data"}), 500

        try:
            tracking_data = {
                "email": email,
                "telegram_id": telegram_id,
                "product_url": url,
                "alert_price": alert_price,
                "last_checked_price": None,
                "created_at": firestore.SERVER_TIMESTAMP,
                "active": True,
                "check_count": 0
            }
            
            db.collection("tracked_items").document().set(tracking_data)
            
            print(f"✅ Price tracking started for {email} - Target: ₹{alert_price}")
            return jsonify({"success": True, "message": "Price tracking started successfully!"})
            
        except Exception as db_error:
            print(f"Database write error: {db_error}")
            return jsonify({"error": "Failed to save tracking data"}), 500
        
    except Exception as e:
        print(f"❌ Error setting up price tracking: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route("/health")
def health_check():
    """Health check with database connectivity test"""
    try:
        test_collection = db.collection("health_check")
        test_doc = test_collection.document("test").get()
        
        return jsonify({
            "status": "healthy", 
            "service": "price-tracker-backend",
            "database": "connected",
            "timestamp": time.time()
        })
    except Exception as e:
        return jsonify({
            "status": "degraded",
            "service": "price-tracker-backend", 
            "database": "error",
            "error": str(e),
            "timestamp": time.time()
        }), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000, host='0.0.0.0')
