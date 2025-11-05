def exec_tri(ab_ask, bc_ask, ac_bid, amount=100.0, fee=0.001):
    # buy BTC
    btc = (amount / ab_ask) * (1 - fee)

    # buy ETH
    eth = (btc / bc_ask) * (1 - fee)

    # sell ETH -> USDC
    final = (eth * ac_bid) * (1 - fee)

    pnl = final - amount
    edge = (pnl / amount) * 100

    return round(final, 6), round(edge, 5)
