import math, os
from utils import balances as B
from utils.logger import log_trade

def _bps(x): return x * 10000.0

def fees_bps(venue):
    if venue == "binance": return float(os.getenv("TAKER_FEE_BPS_BINANCE","6"))
    if venue == "kucoin":  return float(os.getenv("TAKER_FEE_BPS_KUCOIN","8"))
    return 8.0

def maybe_trade(pair_book, path, notional_usdc):
    """
    path: ("A->B", {"A":"binance","B":"kucoin"}) nozīmē  Buy A @ ask, Sell B @ bid
    pair_book: {"A":{"bid":..,"ask":..},"B":{"bid":..,"ask":..}}
    DRY_RUN only: uzreiz pārrēķina bilances un PnL.
    """
    A = path["A"]; Bv = path["B"]
    a_bid, a_ask = pair_book["A"]["bid"], pair_book["A"]["ask"]
    b_bid, b_ask = pair_book["B"]["bid"], pair_book["B"]["ask"]

    feeA = fees_bps(A) / 10000.0
    feeB = fees_bps(Bv) / 10000.0

    # Buy @ A ask -> size_btc
    size_btc = notional_usdc / a_ask
    cost_usdc = notional_usdc * (1.0 + feeA)  # taker fee on quote

    # Sell @ B bid -> proceeds
    proceeds_usdc = (b_bid * size_btc) * (1.0 - feeB)

    pnl = proceeds_usdc - cost_usdc

    # Risk: pietiekams USDC A un pietiekams BTC B (simultānais cross bez pārskaitīšanas)
    if B.get(A, "USDC") < cost_usdc: return False, "NO_USDC_A"
    if B.get(Bv, "BTC") < size_btc: return False, "NO_BTC_B"

    # Apply balances
    B.adjust(A, "USDC", -cost_usdc)
    B.adjust(A, "BTC",  +size_btc)

    B.adjust(Bv, "BTC", -size_btc)
    B.adjust(Bv, "USDC", +proceeds_usdc)

    # Log
    log_trade("A->B", notional_usdc, size_btc, a_ask, b_bid, (cost_usdc+proceeds_usdc) - (notional_usdc + b_bid*size_btc), pnl)
    return True, pnl
