import os, ccxt

def get_kucoin():
    """Izveido KuCoin klientu ar visiem credentials."""
    return ccxt.kucoin({
        'apiKey': os.getenv('KUCOIN_API_KEY'),
        'secret': os.getenv('KUCOIN_SECRET_KEY'),
        'password': os.getenv('KUCOIN_PASSPHRASE'),
        'enableRateLimit': True,
    })

def get_ticker_kucoin(pair="BTC/USDC"):
    """Atgriež bid/ask datus no KuCoin."""
    k = get_kucoin()
    t = k.fetch_ticker(pair)
    return {'bid': t['bid'], 'ask': t['ask']}
