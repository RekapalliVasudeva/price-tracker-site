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

# Complete security headers addressing all issues
@app.after_request
def add_security_headers(response):
    # Cache control (fixes cache-control missing error)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private, max-age=0"
    
    # Security headers (fixes missing x-content-type-options)
    response.headers["X-Content-Type-Options"] = "nosniff"
    
    # Modern CSP instead of X-Frame-Options (fixes deprecated header warning)
    response.headers["Content-Security-Policy"] = "frame-ancestors 'none'; default-src 'self' 'unsafe-inline' 'unsafe-eval' https:; img-src 'self' data: https:;"
    
    # Remove deprecated/unneeded headers
    response.headers.pop("X-XSS-Protection", None)
    response.headers.pop("X-Frame-Options", None)
    response.headers.pop("Expires", None)
    
    # Additional security headers
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    
    return response

def safe_scrape_price(url):
    """Safely scrape price with comprehensive error handling"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none"
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
    """Extract price and title from Flipkart with enhanced selectors"""
    price_selectors = [
        "div._30jeq3", "div._1_WHN1", "div._3I9_wc", "div._25b18c", 
        "div._16Jk6d", "span._30jeq3", "div._1vC4OE", "div._3tbKJL"
    ]
    title_selectors = [
        "span.B_NuCI", "h1.yhB1nd", "span.yhB1nd", "h1._6EBuvT", 
        "span._35KyD6", "h1.x2Vkzk"
    ]
    
    current_price = None
    product_title = None
    
    # Extract price
    for selector in price_selectors:
        try:
            price_tag = soup.find("div", {"class": selector}) or soup.find("span", {"class": selector})
            if price_tag:
                price_text = price_tag.text.replace("₹", "").replace(",", "").strip()
                price_numbers = ''.join(filter(str.isdigit, price_text.split('.')))
                if price_numbers:
                    current_price = float(price_numbers)
                    break
        except (AttributeError, ValueError):
            continue
    
    # Extract title
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
    """Extract price and title from Amazon with enhanced selectors"""
    price_selectors = [
        "#priceblock_ourprice", "#priceblock_dealprice", ".a-price-whole",
        "#price_inside_buybox", ".a-offscreen", "#corePrice_feature_div .a-price .a-offscreen",
        ".a-price.a-text-price.a-size-medium.apexPriceToPay .a-offscreen",
        "#apex_desktop .a-price .a-offscreen", ".a-price-range .a-offscreen"
    ]
    title_selectors = [
        "#productTitle", "h1.a-size-large", ".product-title", 
        "h1#title", "span#productTitle"
    ]
    
    current_price = None
    product_title = None
    
    # Extract price
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
    
    # Extract title
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
    """Root endpoint with comprehensive API documentation"""
    return jsonify({
        "message": "Price Tracker API is running!",
        "status": "healthy",
        "version": "2.0",
        "endpoints": {
            "webhook": "/webhook - Telegram bot webhook handler",
            "save_telegram_id": "/save-telegram-id - Save user Telegram ID", 
            "track_price": "/track-price - Set up price tracking alert",
            "check_price_now": "/check-price-now - Get current price instantly",
            "telegram_login": "/telegram-login - Redirect to Telegram bot",
            "health": "/health - Health check endpoint"
        },
        "supported_sites": ["flipkart.com", "amazon.in", "amazon.com"],
        "features": ["Real-time price checking", "Price drop alerts", "Telegram notifications"]
    }), 200

@app.route("/check-price-now", methods=["POST"])
def check_price_now():
    """Instant price check endpoint with enhanced validation"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No data provided"}), 400
            
        url = data.get("product_url")
        if not url:
            return jsonify({"success": False, "error": "Product URL is required"}), 400
        
        # Enhanced URL validation
        if not (url.startswith('http://') or url.startswith('https://')):
            return jsonify({"success": False, "error": "Invalid URL format. Must start with http:// or https://"}), 400
        
        if not ('flipkart.com' in url.lower() or 'amazon.in' in url.lower() or 'amazon.com' in url.lower()):
            return jsonify({"success": False, "error": "Only Flipkart and Amazon URLs are supported"}), 400
        
        # Scrape the price
        result = safe_scrape_price(url)
        
        if result["success"] and result["current_price"]:
            return jsonify({
                "success": True,
                "current_price": result["current_price"],
                "product_title": result["product_title"],
                "message": "Price fetched successfully",
                "timestamp": time.time()
            })
        else:
            return jsonify({
                "success": False,
                "error": result["error"] or "Could not extract price from the page"
            }), 400
            
    except Exception as e:
        print(f"❌ Error in check_price_now: {e}")
        return jsonify({"success": False, "error": "Internal server error"}), 500

@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    """Enhanced Telegram webhook with better error handling"""
    try:
        data = request.get_json()
        print("Incoming Telegram message:", data)
        
        if not data or "message" not in data:
            return jsonify({"status": "ok"}), 200
            
        chat_id = data["message"]["chat"]["id"]
        message_text = data["message"].get("text", "").strip()
        user_first_name = data["message"]["from"].get("first_name", "Friend")

        if message_text.lower() in ["/start", "hi", "hello", "start"]:
            reply_text = (
                f"👋 Hello {user_first_name}! Welcome to Price Tracker Bot!\n\n"
                f"🆔 Your Chat ID is: **{chat_id}**\n\n"
                f"📋 How to use:\n"
                f"1. Copy your Chat ID above\n"
                f"2. Visit our website\n"
                f"3. Paste your Chat ID in the form\n"
                f"4. Add product URL and target price\n"
                f"5. Get notified when prices drop!\n\n"
                f"🔍 Features:\n"
                f"• Instant price checking\n"
                f"• Automatic price monitoring\n"
                f"• Real-time Telegram alerts\n\n"
                f"💡 Ready to save money? Let's go!"
            )
        else:
            reply_text = (
                f"📩 You said: {message_text}\n\n"
                f"🆔 Your Chat ID is: **{chat_id}**\n\n"
                f"💡 Use this Chat ID on our website to receive price alerts!\n"
                f"Send /start for more information."
            )

        # Send reply with enhanced error handling
        try:
            response = requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": chat_id, 
                    "text": reply_text,
                    "parse_mode": "Markdown"
                },
                timeout=10
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"Failed to send Telegram message: {e}")
            # Try without markdown formatting as fallback
            try:
                requests.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    json={"chat_id": chat_id, "text": reply_text.replace("**", "")},
                    timeout=5
                )
            except:
                pass
            
        return jsonify({"status": "ok"}), 200
        
    except Exception as e:
        print("Webhook Error:", e)
        return jsonify({"error": "Webhook processing failed"}), 500

@app.route("/telegram-login")
def telegram_login():
    return redirect("https://t.me/pricealert_ai_bot")

@app.route("/save-telegram-id", methods=["POST"])
def save_telegram_id():
    """Enhanced save Telegram ID with comprehensive validation"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
            
        telegram_id = data.get("telegram_id")
        email = data.get("email")
        
        if not telegram_id or not email:
            return jsonify({"error": "Both telegram_id and email are required"}), 400
        
        # Enhanced validation
        try:
            telegram_id_int = int(telegram_id)
            if telegram_id_int <= 0:
                raise ValueError("Invalid ID")
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid Telegram ID format. Must be a positive number."}), 400
        
        # Enhanced email validation
        if "@" not in email or "." not in email or len(email) < 5:
            return jsonify({"error": "Invalid email format"}), 400
        
        # Save to database with enhanced error handling
        try:
            doc_ref = db.collection("users").document(email)
            doc_ref.set({
                "telegram_id": str(telegram_id),
                "email": email,
                "created_at": firestore.SERVER_TIMESTAMP,
                "last_updated": firestore.SERVER_TIMESTAMP,
                "status": "active"
            }, merge=True)
            
            print(f"✅ Saved Telegram ID {telegram_id} for email {email}")
            return jsonify({"status": "saved", "message": "Telegram ID saved successfully"})
            
        except Exception as db_error:
            print(f"Database error: {db_error}")
            return jsonify({"error": "Failed to save to database. Please try again."}), 500
        
    except Exception as e:
        print(f"❌ Error saving Telegram ID: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route("/track-price", methods=["POST"])
def track_price():
    """Enhanced price tracking setup with comprehensive validation"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
            
        url = data.get("product_url")
        alert_price = data.get("alert_price")
        email = data.get("email")

        if not url or not alert_price or not email:
            return jsonify({"error": "Missing required fields: product_url, alert_price, email"}), 400

        # Enhanced URL validation
        if not (url.startswith('http://') or url.startswith('https://')):
            return jsonify({"error": "Invalid URL format. Must start with http:// or https://"}), 400
            
        if not ('flipkart.com' in url.lower() or 'amazon.in' in url.lower() or 'amazon.com' in url.lower()):
            return jsonify({"error": "Only Flipkart and Amazon India URLs are currently supported"}), 400

        # Enhanced price validation
        try:
            alert_price = float(alert_price)
            if alert_price <= 0:
                return jsonify({"error": "Alert price must be greater than 0"}), 400
            if alert_price > 10000000:  # 1 crore limit
                return jsonify({"error": "Alert price too high. Please enter a reasonable amount."}), 400
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid alert price format. Must be a number."}), 400

        # Get user's telegram ID with enhanced error handling
        try:
            user_doc = db.collection("users").document(email).get()
            if not user_doc.exists:
                return jsonify({"error": "User not found. Please save your Telegram ID first."}), 404

            user_data = user_doc.to_dict()
            telegram_id = user_data.get("telegram_id")
            
            if not telegram_id:
                return jsonify({"error": "Telegram ID not found for this email. Please save it first."}), 404

        except Exception as db_error:
            print(f"Database read error: {db_error}")
            return jsonify({"error": "Failed to retrieve user data"}), 500

        # Save tracking info with enhanced data
        try:
            tracking_data = {
                "email": email,
                "telegram_id": telegram_id,
                "product_url": url,
                "alert_price": alert_price,
                "last_checked_price": None,
                "created_at": firestore.SERVER_TIMESTAMP,
                "last_checked_at": None,
                "active": True,
                "check_count": 0,
                "alerts_sent": 0,
                "website": "flipkart" if "flipkart.com" in url.lower() else "amazon"
            }
            
            db.collection("tracked_items").document().set(tracking_data)
            
            print(f"✅ Price tracking started for {email} - Target: ₹{alert_price}")
            return jsonify({
                "success": True, 
                "message": "Price tracking started successfully!",
                "alert_price": alert_price,
                "website": tracking_data["website"]
            })
            
        except Exception as db_error:
            print(f"Database write error: {db_error}")
            return jsonify({"error": "Failed to save tracking data. Please try again."}), 500
        
    except Exception as e:
        print(f"❌ Error setting up price tracking: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route("/health")
def health_check():
    """Comprehensive health check with database connectivity test"""
    try:
        # Test database connection
        test_collection = db.collection("health_check")
        test_doc = test_collection.document("test").get()
        
        return jsonify({
            "status": "healthy", 
            "service": "price-tracker-backend",
            "version": "2.0",
            "database": "connected",
            "features": ["CORS enabled", "Security headers", "Enhanced validation"],
            "timestamp": time.time(),
            "uptime": "running"
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
    app.run(debug=False, port=5000, host='0.0.0.0')
