
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
import urllib.parse
 
DATA_FILE = "data.json"
 
# Yahoo Finance uses different tickers for some assets than our app does.
YAHOO_SYMBOL_OVERRIDES = {
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "SPX": "^GSPC",
    "DJI": "^DJI",
    "IXIC": "^IXIC",
    "RUT": "^RUT",
    "VIX": "^VIX",
    "US10Y": "^TNX",
    "KRW": "KRW=X",
    "EURUSD": "EURUSD=X",
    "USDJPY": "JPY=X",
    "DXY": "DX-Y.NYB",
    "WTI": "CL=F",
    "BRENT": "BZ=F",
    "GOLD": "GC=F",
    "SILVER": "SI=F",
    "NATGAS": "NG=F",
    "COPPER": "HG=F",
}
 
# Sanity bounds — if a fetched price falls outside this range, treat it as a
# bad/mismapped response and fall back rather than writing an obviously wrong
# value (this is what caught the wrong WTI/GOLD prices in testing).
SANITY_RANGE = {
    "WTI": (20, 200), "BRENT": (20, 200), "GOLD": (1000, 8000),
    "SILVER": (5, 200), "NATGAS": (0.5, 30), "COPPER": (1, 20),
}
 
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; JunsTreasuryBot/1.0)"
}
 
 
def yahoo_symbol(sym):
    return YAHOO_SYMBOL_OVERRIDES.get(sym, sym)
 
 
def fetch_quote(sym):
    ysym = yahoo_symbol(sym)
    encoded = urllib.parse.quote(ysym, safe='')
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}"
           f"?range=5d&interval=1d")
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=10) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    result = payload["chart"]["result"][0]
    meta = result["meta"]
 
    price = meta.get("regularMarketPrice")
 
    # Fallback: some quote types (indices, FX, futures) omit
    # regularMarketPrice from meta. Use the most recent non-null close from
    # the chart series instead.
    if price is None:
        try:
            closes = result["indicators"]["quote"][0]["close"]
            for c in reversed(closes):
                if c is not None:
                    price = c
                    break
        except (KeyError, IndexError):
            pass
 
    if price is None:
        price = meta.get("previousClose") or meta.get("chartPreviousClose")
 
    if price is None:
        raise ValueError(f"No price field available for {sym} ({ysym})")
 
    price = float(price)
 
    lo_hi = SANITY_RANGE.get(sym)
    if lo_hi and not (lo_hi[0] <= price <= lo_hi[1]):
        raise ValueError(f"Price {price} for {sym} outside sane range {lo_hi} — likely bad data")
 
    prev_close = meta.get("chartPreviousClose") or meta.get("previousClose")
    change_pct = None
    if prev_close:
        change_pct = round((price / float(prev_close) - 1) * 100, 2)
 
    return {
        "price": round(price, 4 if sym in ("EURUSD",) else 2),
        "changePercent": change_pct,
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
            updated[sym] = {"price": old_price(data[sym]), "changePercent": None, "marketState": None,
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
 
