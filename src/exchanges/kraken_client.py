import os, ccxt

def get_kraken():
    key = os.getenv("KRAKEN_API_KEY","")
    sec = os.getenv("KRAKEN_API_SECRET","")
    kr = ccxt.kraken({
        "apiKey": key,
        "secret": sec,
        "enableRateLimit": True
    })
    return kr

def get_ticker_kraken(pair:str):
    kr = get_kraken()
    t = kr.fetch_ticker(pair)
    return {"bid": t["bid"], "ask": t["ask"]}
