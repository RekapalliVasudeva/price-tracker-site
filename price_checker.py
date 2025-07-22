import os
import requests
from bs4 import BeautifulSoup
import time

# Write FIREBASE_CREDENTIALS env variable to file if it exists
if os.environ.get("FIREBASE_CREDENTIALS"):
    with open("serviceAccountKey.json", "w") as f:
        f.write(os.environ["FIREBASE_CREDENTIALS"])

import firebase_admin
from firebase_admin import credentials, firestore

# Environment variables
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR-BOT-TOKEN-HERE")

# Firebase Initialization
if not firebase_admin._apps:
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

# Send Telegram Message
def send_telegram_message(chat_id, message):
    """Send notification message to user via Telegram"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": chat_id, "text": message}
        response = requests.post(url, data=payload, timeout=10)
        response_data = response.json()
        
        if response_data.get("ok"):
            print(f"🔔 Message sent successfully to {chat_id}")
        else:
            print(f"⚠️ Failed to send message: {response_data}")
            
    except Exception as e:
        print(f"❌ Error sending Telegram message: {e}")

# Scrape Flipkart Price
def extract_price_flipkart(url):
    """Extract current price from Flipkart product page"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        
        # Multiple selectors for different Flipkart layouts
        price_selectors = [
            "div._30jeq3",
            "div._1_WHN1", 
            "div._3I9_wc",
            "div._25b18c"
        ]
        
        for selector in price_selectors:
            price_tag = soup.find("div", {"class": selector})
            if price_tag:
                price_text = price_tag.text.replace("₹", "").replace(",", "").strip()
                # Extract only numeric part
                price_numbers = ''.join(filter(str.isdigit, price_text.split('.')[0]))
                if price_numbers:
                    return float(price_numbers)
                    
    except requests.RequestException as e:
        print(f"⚠️ Network error scraping Flipkart: {e}")
    except Exception as e:
        print(f"⚠️ Error scraping Flipkart: {e}")
    
    return None

# Scrape Amazon Price
def extract_price_amazon(url):
    """Extract current price from Amazon product page"""
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
        
        # Multiple selectors for different Amazon layouts
        price_selectors = [
            "#priceblock_ourprice",
            "#priceblock_dealprice",
            ".a-price-whole",
            "#price_inside_buybox",
            ".a-offscreen",
            "#corePrice_feature_div .a-price .a-offscreen"
        ]
        
        for selector in price_selectors:
            price_tag = soup.select_one(selector)
            if price_tag:
                price_text = price_tag.text.replace("₹", "").replace(",", "").strip()
                # Extract only numeric part
                price_numbers = ''.join(filter(str.isdigit, price_text.split('.')[0]))
                if price_numbers:
                    return float(price_numbers)
                    
    except requests.RequestException as e:
        print(f"⚠️ Network error scraping Amazon: {e}")
    except Exception as e:
        print(f"⚠️ Error scraping Amazon: {e}")
    
    return None

# Main Price Check Logic
def check_prices():
    """Check all tracked items and send alerts for price drops"""
    try:
        items_ref = db.collection("tracked_items").stream()
        checked_count = 0
        alerts_sent = 0
        
        for doc in items_ref:
            try:
                data = doc.to_dict()
                url = data.get("product_url")
                alert_price = data.get("alert_price")
                telegram_id = data.get("telegram_id")
                email = data.get("email", "Unknown")
                
                if not url or not alert_price or not telegram_id:
                    print(f"⚠️ Missing data for document {doc.id}")
                    continue
                
                print(f"\n🔍 Checking: {url[:50]}...")
                print(f"👤 User: {email}")
                
                current_price = None
                if "flipkart.com" in url.lower():
                    current_price = extract_price_flipkart(url)
                elif "amazon.in" in url.lower() or "amazon.com" in url.lower():
                    current_price = extract_price_amazon(url)
                else:
                    print("❌ Unsupported website")
                    continue
                
                checked_count += 1
                
                if current_price is not None:
                    print(f"📉 Current Price: ₹{current_price} | 🎯 Target Price: ₹{alert_price}")
                    
                    # Update last checked price
                    doc.reference.update({"last_checked_price": current_price})
                    
                    if current_price <= alert_price:
                        message = (
                            f"🔥 Price Drop Alert!\n\n"
                            f"💸 Current Price: ₹{current_price}\n"
                            f"🎯 Your Target: ₹{alert_price}\n"
                            f"💰 You Save: ₹{alert_price - current_price}\n\n"
                            f"🔗 Buy Now: {url}"
                        )
                        send_telegram_message(telegram_id, message)
                        alerts_sent += 1
                        print("✅ Alert sent!")
                    else:
                        print("ℹ️ Price is still above target")
                else:
                    print("❌ Could not fetch current price")
                
                # Add delay between requests to avoid rate limiting
                time.sleep(2)
                
            except Exception as e:
                print(f"❌ Error processing document {doc.id}: {e}")
                continue
        
        print(f"\n📊 Summary:")
        print(f"   Checked: {checked_count} items")
        print(f"   Alerts sent: {alerts_sent}")
        
    except Exception as e:
        print(f"❌ Error in check_prices: {e}")

# Entry Point
if __name__ == "__main__":
    print("📡 Starting Price Tracker...")
    print("=" * 50)
    check_prices()
    print("=" * 50)
    print("✅ Price check complete!")
