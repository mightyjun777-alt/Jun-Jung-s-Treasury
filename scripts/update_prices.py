
"""
Fetches the latest price for each symbol in data.json from Yahoo Finance's
public chart endpoint and overwrites data.json with the new values —
including pre-market and after-hours prices when the market is closed.
 
Runs inside GitHub Actions (server-side), so it is not subject to the
browser CORS restrictions that block this same call from client-side JS.
"""
import json
import time
import urllib.request
import urllib.error
 
DATA_FILE = "data.json"
 
# Yahoo Finance uses different tickers for some assets than our app does.
YAHOO_SYMBOL_OVERRIDES = {
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
}
 
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; JunsTreasuryBot/1.0)"
}
 
 
def yahoo_symbol(sym):
    return YAHOO_SYMBOL_OVERRIDES.get(sym, sym)
 
 
def fetch_quote(sym):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol(sym)}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=10) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    meta = payload["chart"]["result"][0]["meta"]
 
    price = meta.get("regularMarketPrice")
    if price is None:
        raise ValueError(f"No regularMarketPrice for {sym}")
 
    return {
        "price": round(float(price), 2),
        "marketState": meta.get("marketState"),  # PRE, REGULAR, POST, CLOSED
        "preMarketPrice": (
            round(float(meta["preMarketPrice"]), 2)
            if meta.get("preMarketPrice") is not None else None
        ),
        "postMarketPrice": (
            round(float(meta["postMarketPrice"]), 2)
            if meta.get("postMarketPrice") is not None else None
        ),
    }
 
 
def main():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
 
    # Support both the old flat format {"AAPL": 123.45} and the new
    # object format {"AAPL": {"price": 123.45, ...}} for a smooth migration.
    def old_price(entry):
        return entry if isinstance(entry, (int, float)) else entry.get("price")
 
    updated = {}
    failed = []
 
    for sym in data.keys():
        try:
            quote = fetch_quote(sym)
            updated[sym] = quote
            print(f"OK  {sym}: {quote}")
        except Exception as e:
            updated[sym] = {"price": old_price(data[sym]), "marketState": None,
                             "preMarketPrice": None, "postMarketPrice": None}
            failed.append(sym)
            print(f"FAIL {sym}: {e}")
        time.sleep(0.5)  # be polite to the API
 
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(updated, f, ensure_ascii=False, indent=2)
        f.write("\n")
 
    print(f"\nDone. {len(updated) - len(failed)} updated, {len(failed)} failed: {failed}")
 
 
if __name__ == "__main__":
    main()
 
