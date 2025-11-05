def mid_from_orderbook(ob):
    bid = ob['bids'][0][0] if ob['bids'] else None
    ask = ob['asks'][0][0] if ob['asks'] else None
    if bid is None or ask is None: return None
    return (bid + ask) / 2.0, bid, ask

def cross_edge_bps(b_mid, k_mid):
    # +ve => Binance dārgāks par KuCoin (pārdod BNB, pērc KUC)
    return ( (b_mid - k_mid) / ((b_mid + k_mid)/2.0) ) * 1e4
