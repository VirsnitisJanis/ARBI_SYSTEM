import csv, os, time

# Lasām parametrus no ENV (ar drošiem noklusējumiem)
MAKER_FEE_BPS_A   = float(os.getenv("MAKER_FEE_BPS_A",   "1.0"))   # birža A (maker)
TAKER_FEE_BPS_B   = float(os.getenv("TAKER_FEE_BPS_B",   "8.0"))   # birža B (taker hedge)
SLIPPAGE_BPS      = float(os.getenv("SLIPPAGE_BPS",      "1.0"))   # hedge slippage
MIN_SPREAD_BPS    = float(os.getenv("MIN_SPREAD_BPS",    "0.6"))   # minimālais iekšējais spreds (A & B)
MIN_NET_BPS       = float(os.getenv("MIN_NET_BPS",       "0.2"))   # drošības buferis virs nulles
DECISION_LOG      = os.getenv("EDGE_DECISION_LOG", "logs/edge_decisions.csv")

def _bps(x: float) -> float:
    return x * 10000.0

def _ensure_log():
    os.makedirs(os.path.dirname(DECISION_LOG), exist_ok=True)
    if not os.path.exists(DECISION_LOG):
        with open(DECISION_LOG, "w", newline="") as f:
            csv.writer(f).writerow([
                "ts",
                "a_bid","a_ask","b_bid","b_ask",
                "raw_edge_bps","fees_bps","slip_bps","net_bps",
                "min_spread_bps","decision","reason",
                "notional","est_pnl_usd"
            ])

def compute_edges(a_bid, a_ask, b_bid, b_ask):
    # “Raw” edge = (B.bid - A.ask)/mid
    mid = (a_bid + a_ask + b_bid + b_ask) / 4.0
    raw_edge_bps = _bps((b_bid - a_ask) / mid)
    # Iekšējie spredi
    spread_a_bps = _bps((a_ask - a_bid) / ((a_ask + a_bid)/2.0))
    spread_b_bps = _bps((b_ask - b_bid) / ((b_ask + b_bid)/2.0))
    min_internal_spread_bps = max(spread_a_bps, spread_b_bps)
    return raw_edge_bps, min_internal_spread_bps

def estimate_pnl_usd(a_bid, a_ask, b_bid, notional_usdc):
    """
    Pieņemam: maker BUY uz A apm. pie A.bid (ar pad) un hedge SELL uz B pie B.bid
    PnL ≈ (hedge_px - maker_px) * qty - komisijas
    qty = NOTIONAL / maker_px
    Kom.: maker_fee = maker_px*qty*(MAKER_FEE_BPS_A/1e4); taker_fee = hedge_px*qty*(TAKER_FEE_BPS_B/1e4)
    Slippage: hedge_px *= (1 - SLIPPAGE_BPS/1e4)
    """
    maker_px = a_bid
    hedge_px = b_bid * (1.0 - SLIPPAGE_BPS/10000.0)
    qty = notional_usdc / maker_px
    gross = (hedge_px - maker_px) * qty
    maker_fee = maker_px * qty * (MAKER_FEE_BPS_A/10000.0)
    taker_fee = hedge_px * qty * (TAKER_FEE_BPS_B/10000.0)
    pnl = gross - maker_fee - taker_fee
    # “kopējās izmaksas bps” aptuveni:
    fees_bps = MAKER_FEE_BPS_A + TAKER_FEE_BPS_B
    return pnl, fees_bps

def should_open(a_bid, a_ask, b_bid, b_ask, notional_usdc, edge_open_bps):
    """
    Atgriež: (bool open?, dict info)
    Kritēriji:
      1) Iekšējais spreds nav pārāk šaurs/haotisks: min_internal_spread_bps >= MIN_SPREAD_BPS
      2) raw_edge_bps - (fees+slip) >= max(edge_open_bps, MIN_NET_BPS)
      3) Estētā PnL USD > 0
    """
    _ensure_log()
    raw_edge_bps, min_internal_spread_bps = compute_edges(a_bid, a_ask, b_bid, b_ask)

    # aptuvenais “net” edge aprēķins
    fees_bps = MAKER_FEE_BPS_A + TAKER_FEE_BPS_B
    slip_bps = SLIPPAGE_BPS
    net_bps = raw_edge_bps - fees_bps - slip_bps

    reason = ""
    decision = "REJECT"
    est_pnl, _fees_bps_ = estimate_pnl_usd(a_bid, a_ask, b_bid, notional_usdc)

    if min_internal_spread_bps < MIN_SPREAD_BPS:
        reason = f"min_spread({min_internal_spread_bps:.2f})<{MIN_SPREAD_BPS:.2f}"
    elif net_bps < max(edge_open_bps, MIN_NET_BPS):
        reason = f"net_bps({net_bps:.2f})<thr({max(edge_open_bps, MIN_NET_BPS):.2f})"
    elif est_pnl <= 0:
        reason = f"est_pnl_usd({est_pnl:.6f})<=0"
    else:
        decision = "OPEN"
        reason = "ok"

    with open(DECISION_LOG, "a", newline="") as f:
        csv.writer(f).writerow([
            time.time(),
            a_bid, a_ask, b_bid, b_ask,
            raw_edge_bps, fees_bps, slip_bps, net_bps,
            MIN_SPREAD_BPS, decision, reason,
            notional_usdc, est_pnl
        ])

    return decision == "OPEN", {
        "raw_edge_bps": raw_edge_bps,
        "net_bps": net_bps,
        "min_internal_spread_bps": min_internal_spread_bps,
        "est_pnl_usd": est_pnl,
        "reason": reason
    }
