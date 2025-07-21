import requests
from bs4 import BeautifulSoup
import firebase_admin
from firebase_admin import credentials, firestore
import time
import os
# ✅ Telegram Bot Info
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR-BOT-TOKEN-HERE")


# ✅ Firebase Initialization
if not firebase_admin._apps:
    cred = credentials.Certificate("serviceAccountKey.json")  # File must be in same folder
    firebase_admin.initialize_app(cred)

db = firestore.client()

# ✅ Send Telegram Message
def send_telegram_message(chat_id, message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": message}
    response = requests.post(url, data=payload)
    print(f"🔔 Telegram response: {response.json()}")

# ✅ Scrape Flipkart Price
def extract_price_flipkart(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        page = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(page.content, "html.parser")
        price_tag = soup.find("div", {"class": "_30jeq3"})
        if price_tag:
            price_text = price_tag.text.replace("₹", "").replace(",", "").strip()
            return float(price_text)
    except Exception as e:
        print(f"⚠️ Error scraping Flipkart: {e}")
    return None

# ✅ Scrape Amazon Price
def extract_price_amazon(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        page = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(page.content, "html.parser")
        price_tag = soup.find(id="priceblock_ourprice") or soup.find(id="priceblock_dealprice")
        if price_tag:
            price_text = price_tag.text.replace("₹", "").replace(",", "").strip()
            return float(price_text)
    except Exception as e:
        print(f"⚠️ Error scraping Amazon: {e}")
    return None

# ✅ Main Price Check Logic
def check_prices():
    items_ref = db.collection("tracked_items").stream()
    for doc in items_ref:
        data = doc.to_dict()
        url = data.get("product_url")
        alert_price = data.get("alert_price")
        telegram_id = data.get("telegram_id")

        current_price = None
        if "flipkart.com" in url:
            current_price = extract_price_flipkart(url)
        elif "amazon.in" in url:
            current_price = extract_price_amazon(url)

        print(f"🔍 Checking: {url}")
        print(f"📉 Current Price: ₹{current_price} | 🎯 Target Price: ₹{alert_price}")

        if current_price is not None and alert_price is not None:
            if current_price <= alert_price:
                send_telegram_message(
                    telegram_id,
                    f"🔥 Price Drop Alert!\n💸 Your product is now ₹{current_price}\n🔗 {url}"
                )
            else:
                print("ℹ️ Price is still above target.")
        else:
            print("❌ Could not fetch price or target price is missing.")

# ✅ Entry Point
if __name__ == "__main__":
    print("📡 Starting Price Check...")
    check_prices()
    print("✅ Done.")
