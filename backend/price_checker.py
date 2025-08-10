# price_checker.py
import os
import time
import traceback
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Firebase
import firebase_admin
from firebase_admin import credentials, firestore

load_dotenv()

# Write firebase file if provided
if os.environ.get("FIREBASE_CREDENTIALS"):
    with open("serviceAccountKey.json", "w", encoding="utf-8") as f:
        f.write(os.environ["FIREBASE_CREDENTIALS"])

if not firebase_admin._apps:
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
DEFAULT_USER_AGENT = os.environ.get("DEFAULT_USER_AGENT", "Mozilla/5.0")
USE_PLAYWRIGHT = os.environ.get("USE_PLAYWRIGHT", "false").lower() == "true"
SMTP_HOST = os.environ.get("SMTP_HOST")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587)) if os.environ.get("SMTP_PORT") else 587
SMTP_USERNAME = os.environ.get("SMTP_USERNAME")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
EMAIL_FROM = os.environ.get("EMAIL_FROM", "no-reply@example.com")
BACKEND_URL = os.environ.get("BACKEND_URL", "")

# helper functions reused from backend
def safe_requests_get(url, headers=None, timeout=15):
    headers = headers or {"User-Agent": DEFAULT_USER_AGENT}
    tries = 3
    for i in range(tries):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp
        except Exception as e:
            print(f"Request failed ({i+1}/{tries}) for {url}: {e}")
            time.sleep(2 * (i+1))
    return None

def normalize_price_text(price_text):
    if not price_text:
        return None
    s = ''.join(ch for ch in price_text if (ch.isdigit() or ch == '.' or ch == ','))
    s = s.replace(',', '')
    digits = ''.join(ch for ch in s if ch.isdigit() or ch == '.')
    if not digits:
        return None
    if digits.count('.') > 1:
        digits = digits.split('.')[0]
    try:
        return float(digits)
    except:
        return None

def extract_flipkart_data_from_soup(soup):
    price_selectors = [
        "div._30jeq3", "div._1vC4OE", "div._1_WHN1", "div._25b18c",
        "span._30jeq3", "div._16Jk6d"
    ]
    title_selectors = ["span.B_NuCI", "h1._1AtVbE", "span._35KyD6", "h1"]
    price = None
    title = None
    for sel in price_selectors:
        tag = soup.select_one(sel)
        if tag:
            price = normalize_price_text(tag.get_text(strip=True))
            if price:
                break
    for sel in title_selectors:
        tag = soup.select_one(sel)
        if tag:
            title = tag.get_text(strip=True)[:200]
            break
    return price, title

def extract_amazon_data_from_soup(soup):
    price_selectors = [
        "#priceblock_ourprice", "#priceblock_dealprice",
        ".a-price .a-offscreen", "#price_inside_buybox", ".a-offscreen"
    ]
    title_selectors = ["#productTitle", "h1#title", "span#productTitle", "h1"]
    price = None
    title = None
    for sel in price_selectors:
        tag = soup.select_one(sel)
        if tag:
            price = normalize_price_text(tag.get_text(strip=True))
            if price:
                break
    for sel in title_selectors:
        tag = soup.select_one(sel)
        if tag:
            title = tag.get_text(strip=True)[:200]
            break
    return price, title

def safe_scrape_price(url):
    resp = safe_requests_get(url)
    if resp:
        soup = BeautifulSoup(resp.content, "lxml")
        url_low = url.lower()
        if "flipkart.com" in url_low:
            p, t = extract_flipkart_data_from_soup(soup)
        else:
            p, t = extract_amazon_data_from_soup(soup)
        if p:
            return p, t
    # Playwright fallback
    if USE_PLAYWRIGHT:
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, timeout=30000)
                html = page.content()
                soup = BeautifulSoup(html, "lxml")
                url_low = url.lower()
                if "flipkart.com" in url_low:
                    p, t = extract_flipkart_data_from_soup(soup)
                else:
                    p, t = extract_amazon_data_from_soup(soup)
                browser.close()
                if p:
                    return p, t
        except Exception as e:
            print("Playwright fallback error:", e)
    return None, None

def send_telegram_message(chat_id, message):
    if not TELEGRAM_BOT_TOKEN:
        print("No telegram token; skip")
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
        resp = requests.post(url, json=payload, timeout=10)
        return resp.ok
    except Exception as e:
        print("Telegram send error:", e)
        return False

def send_email(to_email, subject, html_body):
    if not SMTP_HOST or not SMTP_USERNAME or not SMTP_PASSWORD:
        print("Email not configured; skip")
        return False
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = EMAIL_FROM = os.environ.get("EMAIL_FROM", "no-reply@example.com")
        msg["To"] = to_email
        msg.attach(MIMEText(html_body, "html"))
        s = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10)
        s.starttls()
        s.login(SMTP_USERNAME, SMTP_PASSWORD)
        s.sendmail(msg["From"], [to_email], msg.as_string())
        s.quit()
        return True
    except Exception as e:
        print("Email send error:", e)
        return False

def process_item(doc_snapshot, doc_id):
    data = doc_snapshot.to_dict()
    url = data.get("product_url")
    alert_price = data.get("alert_price")
    telegram_id = data.get("telegram_id")
    email = data.get("email")
    if not url or not alert_price or not telegram_id:
        print(f"Skipping invalid tracked item {doc_id}")
        return False, None

    print(f"Checking {url} for target {alert_price}")

    current_price, title = safe_scrape_price(url)
    if current_price is None:
        print("Could not extract price for", url)
        return False, None

    # write price point
    try:
        db.collection("price_points").add({
            "product_id": doc_id,
            "product_url": url,
            "price": current_price,
            "currency": "INR",
            "timestamp": firestore.SERVER_TIMESTAMP
        })
    except Exception as e:
        print("Failed to write price point:", e)

    # update tracked item
    try:
        db.collection("tracked_items").document(doc_id).update({
            "last_checked_price": current_price,
            "last_checked_at": firestore.SERVER_TIMESTAMP,
            "check_count": firestore.Increment(1)
        })
    except Exception as e:
        print("Failed to update tracked item:", e)

    # check alert condition
    alerts_sent = data.get("alerts_sent", 0)
    if current_price <= alert_price:
        # deduplicate: check last notification time or count
        try:
            # Send telegram
            message = (f"🔥 Price Drop!\n\n<b>{title or 'Product'}</b>\n"
                       f"💸 Current Price: ₹{current_price}\n"
                       f"🎯 Your Target: ₹{alert_price}\n"
                       f"🔗 {url}")
            send_telegram_message(telegram_id, message)
            # send email
            if email:
                html = f"<p><b>{title or 'Product'}</b></p><p>Current Price: ₹{current_price}</p><p>Target Price: ₹{alert_price}</p><p><a href='{url}'>Buy Now</a></p>"
                send_email(email, "Price Drop Alert", html)
            # increment alerts_sent
            db.collection("tracked_items").document(doc_id).update({
                "alerts_sent": firestore.Increment(1),
                "last_alerted_at": firestore.SERVER_TIMESTAMP
            })
            print("Alert sent for", doc_id)
            return True, current_price
        except Exception as e:
            print("Alert send failure:", e)
            return False, current_price
    else:
        print(f"No alert. Current: {current_price}, Target: {alert_price}")
    return False, current_price

def main():
    print("Starting price checker")
    try:
        docs = db.collection("tracked_items").where("active", "==", True).stream()
        checked = 0
        alerts = 0
        for d in docs:
            try:
                ok, price = process_item(d, d.id)
                checked += 1
                if ok:
                    alerts += 1
                time.sleep(2)  # polite delay
            except Exception as e:
                print("Error processing doc:", e)
                traceback.print_exc()
        print(f"Checked: {checked}, Alerts: {alerts}")
    except Exception as e:
        print("Main loop error:", e)
        traceback.print_exc()

if __name__ == "__main__":
    main()
