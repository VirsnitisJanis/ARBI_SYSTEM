import os, ccxt

def get_binance():
    """Izveido Binance klientu ar visiem credentials."""
    return ccxt.binance({
        'apiKey': os.getenv('BINANCE_API_KEY'),
        'secret': os.getenv('BINANCE_SECRET_KEY'),
        'enableRateLimit': True,
    })

def get_ticker_binance(pair="BTC/USDC"):
    """Atgriež bid/ask no Binance."""
    b = get_binance()
    t = b.fetch_ticker(pair)
    return {'bid': t['bid'], 'ask': t['ask']}
