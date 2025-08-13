# telegram_auth_backend.py
import os
import time
import json
import traceback
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from flask import Flask, request, jsonify, redirect
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Firebase
import firebase_admin
from firebase_admin import credentials, firestore

# Load .env in local dev
load_dotenv()

# Write FIREBASE_CREDENTIALS env variable to file if provided (Render/Heroku style)
if os.environ.get("FIREBASE_CREDENTIALS"):
    with open("serviceAccountKey.json", "w", encoding="utf-8") as f:
        f.write(os.environ["FIREBASE_CREDENTIALS"])

# Initialize Firebase
if not firebase_admin._apps:
    cred = credentials.Certificate("firebase.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

app = Flask(__name__)
CORS(app)

# Config/env
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
DEFAULT_USER_AGENT = os.environ.get("DEFAULT_USER_AGENT", "Mozilla/5.0")
BACKEND_URL = os.environ.get("BACKEND_URL", "")
SMTP_HOST = os.environ.get("SMTP_HOST")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
SMTP_USERNAME = os.environ.get("SMTP_USERNAME")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
EMAIL_FROM = os.environ.get("EMAIL_FROM", "no-reply@example.com")
USE_PLAYWRIGHT = os.environ.get("USE_PLAYWRIGHT", "false").lower() == "true"

# Security headers
@app.after_request
def add_security_headers(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private, max-age=0"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    # Minimal CSP; tweak as required for resources
    response.headers["Content-Security-Policy"] = "default-src 'self' 'unsafe-inline' https:; img-src 'self' data: https:;"
    return response

def send_email(to_email, subject, html_body):
    if not SMTP_HOST or not SMTP_USERNAME or not SMTP_PASSWORD:
        print("Email config missing; skipping email send.")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = EMAIL_FROM
        msg["To"] = to_email
        part = MIMEText(html_body, "html")
        msg.attach(part)

        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10)
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.sendmail(EMAIL_FROM, to_email, msg.as_string())
        server.quit()
        print(f"✅ Email sent to {to_email}")
        return True
    except Exception as e:
        print("❌ Email send failed:", e)
        return False

def send_telegram_message(chat_id, message):
    if not BOT_TOKEN:
        print("Telegram token not set, skipping telegram send.")
        return False
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        resp = requests.post(url, json=payload, timeout=10)
        data = resp.json()
        if data.get("ok"):
            print(f"✅ Telegram sent to {chat_id}")
            return True
        else:
            print("⚠️ Telegram API returned:", data)
            return False
    except Exception as e:
        print("❌ Telegram send error:", e)
        return False

# ---------- Scraping helpers ----------
def safe_requests_get(url, headers=None, timeout=15):
    headers = headers or {"User-Agent": DEFAULT_USER_AGENT}
    tries = 3
    backoff = 1.5
    for i in range(tries):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp
        except Exception as e:
            print(f"Request error ({i+1}/{tries}) for {url}: {e}")
            time.sleep(backoff * (i+1))
    return None

def normalize_price_text(price_text):
    if not price_text:
        return None
    # Remove non-numeric except dot
    s = ''.join(ch for ch in price_text if (ch.isdigit() or ch == '.' or ch == ','))
    s = s.replace(',', '')
    # keep only first numeric group
    parts = s.split()
    if not s:
        return None
    # extract digits and dots
    digits = ''.join(ch for ch in s if ch.isdigit() or ch == '.')
    try:
        if digits:
            # convert to float safely: ignore leftover dots
            if digits.count('.') > 1:
                digits = digits.split('.')[0]
            return float(digits)
    except:
        return None
    return None

def extract_flipkart_data_from_soup(soup):
    # CSS selectors (try many)
    price_selectors = [
        "div._30jeq3", "div._1vC4OE", "div._1_WHN1", "div._25b18c",
        "span._30jeq3", "div._16Jk6d", "._1vC4OE ._1vC4OE"
    ]
    title_selectors = ["span.B_NuCI", "h1._1AtVbE", "span._35KyD6", "h1"]

    current_price = None
    product_title = None

    for sel in price_selectors:
        tag = soup.select_one(sel)
        if tag and tag.get_text(strip=True):
            current_price = normalize_price_text(tag.get_text(strip=True))
            if current_price:
                break

    for sel in title_selectors:
        tag = soup.select_one(sel)
        if tag and tag.get_text(strip=True):
            product_title = tag.get_text(strip=True)[:200]
            break

    return current_price, product_title

def extract_amazon_data_from_soup(soup):
    price_selectors = [
        "#priceblock_ourprice", "#priceblock_dealprice",
        ".a-price .a-offscreen", "#price_inside_buybox", ".a-offscreen"
    ]
    title_selectors = ["#productTitle", "h1#title", "span#productTitle", "h1"]

    current_price = None
    product_title = None

    for sel in price_selectors:
        tag = soup.select_one(sel)
        if tag and tag.get_text(strip=True):
            current_price = normalize_price_text(tag.get_text(strip=True))
            if current_price:
                break

    for sel in title_selectors:
        tag = soup.select_one(sel)
        if tag and tag.get_text(strip=True):
            product_title = tag.get_text(strip=True)[:200]
            break

    return current_price, product_title

def safe_scrape_price(url):
    # Attempt requests first
    resp = safe_requests_get(url)
    if resp:
        soup = BeautifulSoup(resp.content, "lxml")
        url_low = url.lower()
        if 'flipkart.com' in url_low:
            price, title = extract_flipkart_data_from_soup(soup)
            if price:
                return {"success": True, "current_price": price, "product_title": title}
        elif 'amazon.in' in url_low or 'amazon.com' in url_low:
            price, title = extract_amazon_data_from_soup(soup)
            if price:
                return {"success": True, "current_price": price, "product_title": title}
    # Playwright fallback if enabled
    if USE_PLAYWRIGHT:
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, timeout=30000)
                html = page.content()
                soup = BeautifulSoup(html, "lxml")
                url_low = url.lower()
                if 'flipkart.com' in url_low:
                    price, title = extract_flipkart_data_from_soup(soup)
                else:
                    price, title = extract_amazon_data_from_soup(soup)
                browser.close()
                if price:
                    return {"success": True, "current_price": price, "product_title": title}
        except Exception as e:
            print("Playwright fallback failed:", e)
    return {"success": False, "error": "Price extraction failed"}

# ---------- API endpoints ----------
@app.route("/")
def root():
    return jsonify({
        "message": "Price Tracker API",
        "endpoints": {
            "check_price_now": "/check-price-now (POST)",
            "save_telegram_id": "/save-telegram-id (POST)",
            "track_price": "/track-price (POST)",
            "product_history": "/product-history?product_id=<id> (GET)",
            "health": "/health (GET)"
        }
    }), 200

@app.route("/check-price-now", methods=["POST"])
def check_price_now():
    data = request.get_json() or {}
    url = data.get("product_url")
    if not url:
        return jsonify({"success": False, "error": "product_url required"}), 400
    result = safe_scrape_price(url)
    if result.get("success"):
        return jsonify({
            "success": True,
            "current_price": result["current_price"],
            "product_title": result.get("product_title")
        })
    else:
        return jsonify({"success": False, "error": result.get("error", "unknown")}), 500

@app.route("/save-telegram-id", methods=["POST"])
def save_telegram_id():
    data = request.get_json() or {}
    telegram_id = data.get("telegram_id")
    email = data.get("email")
    if not telegram_id or not email:
        return jsonify({"error": "telegram_id and email required"}), 400
    try:
        int(telegram_id)  # simple check
    except:
        return jsonify({"error": "invalid telegram_id"}), 400
    try:
        db.collection("users").document(email).set({
            "telegram_id": str(telegram_id),
            "email": email,
            "updated_at": firestore.SERVER_TIMESTAMP
        }, merge=True)
        return jsonify({"status": "saved"})
    except Exception as e:
        print("DB save error:", e)
        return jsonify({"error": "db_error"}), 500

@app.route("/track-price", methods=["POST"])
def track_price():
    data = request.get_json() or {}
    url = data.get("product_url")
    alert_price = data.get("alert_price")
    email = data.get("email")
    if not url or not alert_price or not email:
        return jsonify({"error": "product_url, alert_price, email required"}), 400
    try:
        alert_price = float(alert_price)
    except:
        return jsonify({"error": "invalid alert_price"}), 400
    if alert_price <= 0:
        return jsonify({"error": "alert_price must be positive"}), 400
    # confirm user exists
    user_doc = db.collection("users").document(email).get()
    if not user_doc.exists:
        return jsonify({"error": "user_not_found"}), 404
    user_data = user_doc.to_dict()
    telegram_id = user_data.get("telegram_id")
    if not telegram_id:
        return jsonify({"error": "telegram_id_missing"}), 400
    # Create tracked item
    try:
        doc_ref = db.collection("tracked_items").document()
        doc_ref.set({
            "email": email,
            "telegram_id": str(telegram_id),
            "product_url": url,
            "alert_price": alert_price,
            "created_at": firestore.SERVER_TIMESTAMP,
            "last_checked_at": None,
            "last_checked_price": None,
            "active": True,
            "alerts_sent": 0
        })
        return jsonify({"success": True, "message": "tracking_started"})
    except Exception as e:
        print("DB write error:", e)
        return jsonify({"error": "db_write_failed"}), 500

@app.route("/product-history", methods=["GET"])
def product_history():
    # Query price_points by product_id (passed via ?product_id=) OR by product_url
    product_id = request.args.get("product_id")
    product_url = request.args.get("product_url")
    if not product_id and not product_url:
        return jsonify({"error": "provide product_id or product_url"}), 400

    try:
        if product_id:
            q = db.collection("price_points").where("product_id", "==", product_id).order_by("timestamp")
        else:
            q = db.collection("price_points").where("product_url", "==", product_url).order_by("timestamp")
        docs = q.stream()
        points = []
        for d in docs:
            data = d.to_dict()
            ts = data.get("timestamp")
            # convert Firestore timestamp to ms
            if hasattr(ts, "timestamp"):
                t_ms = int(ts.timestamp() * 1000)
            else:
                t_ms = int(time.time() * 1000)
            points.append({"price": data.get("price"), "timestamp": t_ms})
        return jsonify({"success": True, "data": points})
    except Exception as e:
        print("History read error:", e)
        return jsonify({"error": "db_read_failed"}), 500

@app.route("/health", methods=["GET"])
def health():
    try:
        # quick DB read
        _ = db.collection("health_check").document("ping").get()
        return jsonify({"status": "healthy"}), 200
    except Exception as e:
        return jsonify({"status": "degraded", "error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
