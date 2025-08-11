# app.py placeholder
from fastapi import FastAPI
import uvicorn
from price_checker import check_price  # assuming this function exists in price_checker.py

app = FastAPI()

@app.get("/")
def home():
    return {"message": "Price Tracker Backend is running!"}

@app.get("/check-price/")
def get_price(product_url: str):
    """
    Endpoint to check product price.
    Example: /check-price/?product_url=https://example.com/item
    """
    try:
        price = check_price(product_url)
        return {"url": product_url, "price": price}
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5000)
