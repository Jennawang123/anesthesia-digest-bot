import logging
import yfinance as yf


def get_price(ticker: str, market: str) -> float:
    """
    market: 'TW' or 'US'
    TW: '2330' → yfinance ticker '2330.TW', price in TWD
    US: 'AAPL' → yfinance ticker 'AAPL', price in USD
    Returns 0.0 on failure.
    """
    yf_ticker = f"{ticker}.TW" if market == "TW" else ticker
    for period in ("5d", "1mo", "3mo"):
        try:
            hist = yf.Ticker(yf_ticker).history(period=period)
            if not hist.empty:
                return float(hist["Close"].iloc[-1])
            logging.warning("yfinance: empty for %s period=%s", yf_ticker, period)
        except Exception as e:
            logging.error("yfinance error for %s period=%s: %s", yf_ticker, period, e)
    # Last resort: use .info regularMarketPrice
    try:
        info = yf.Ticker(yf_ticker).info
        price = info.get("regularMarketPrice") or info.get("currentPrice") or 0.0
        if price:
            return float(price)
    except Exception as e:
        logging.error("yfinance .info error for %s: %s", yf_ticker, e)
    return 0.0


def get_usd_twd_rate() -> float:
    """Fetch real-time USD/TWD from Yahoo Finance (TWD=X). Falls back to 31.0."""
    try:
        hist = yf.Ticker("TWD=X").history(period="2d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception as e:
        logging.error("USD/TWD fetch error: %s", e)
    return 31.0
