# src/hedge_recovery.py
import csv
import os
import time

from notify import send
from utils.balances import adjust, get, snapshot

# Konfigurācija caur ENV
PAIR      = os.getenv("PAIR", "BTC/USDC")
A         = os.getenv("VENUE_A", "binance")
B         = os.getenv("VENUE_B", "kucoin")

# Trigeri / limiti
IMB_THRESH_BTC   = float(os.getenv("IMB_THRESH_BTC",   "0.00030"))  # kad sākam balansēt
MAX_RECOVER_USDC = float(os.getenv("MAX_RECOVER_USDC", "50"))       # max notional vienā atjaunošanā
TAKER_FEE_BPS_A  = float(os.getenv("TAKER_FEE_BPS_A",  "6"))        # 0.06%
TAKER_FEE_BPS_B  = float(os.getenv("TAKER_FEE_BPS_B",  "8"))        # 0.08%
SLIPPAGE_BPS     = float(os.getenv("RECOV_SLIPPAGE_BPS","1.0"))     # “market” polsteris
LOG              = "logs/recovery.csv"

def _write_log(row):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a", newline="") as f:
        csv.writer(f).writerow(row)

def _taker_sell(venue:str, qty:float, bid_px:float, fee_bps:float):
    # pārdod BTC → +USDC, −BTC (par BID), atņem fee
    fee = bid_px * qty * (fee_bps / 10_000.0)
    adjust(venue, "BTC",  -qty)
    adjust(venue, "USDC",  bid_px*qty - fee)
    return -(fee)

def _taker_buy(venue:str, qty:float, ask_px:float, fee_bps:float):
    # pērk BTC → −USDC, +BTC (par ASK), atņem fee
    fee = ask_px * qty * (fee_bps / 10_000.0)
    adjust(venue, "BTC",   qty)
    adjust(venue, "USDC", -(ask_px*qty + fee))
    return -(fee)

def check_and_recover(a_bid:float, a_ask:float, b_bid:float, b_ask:float):
    """
    Vienkārša, droša hedstilpuma atjaunošana:
      • Ja A pusē BTC > sliekšņa → pārdod daļu uz A (taker sell pie BID)
      • Ja B pusē BTC < −slieksnis (t.i., “parāds”) → pērk daļu uz B (taker buy pie ASK)
      • Ciena MAX_RECOVER_USDC limitu
      • Logē un sūta Telegram ziņu
    Atgriež: True ja veikta darbība, citādi False.
    """
    now = time.time()
    snap = snapshot()
    btcA = get(A, "BTC")
    btcB = get(B, "BTC")

    acted = False
    msgs  = []

    # A: pārpalikums BTC → taker SELL uz A
    if btcA > IMB_THRESH_BTC and a_bid:
        max_qty = MAX_RECOVER_USDC / (a_bid * (1.0 - SLIPPAGE_BPS/10_000.0))
        qty = min(btcA - IMB_THRESH_BTC, max(0.0, max_qty))
        if qty > 0:
            eff_bid = a_bid * (1.0 - SLIPPAGE_BPS/10_000.0)
            fee_pnl = _taker_sell(A, qty, eff_bid, TAKER_FEE_BPS_A)
            acted = True
            msg = (f"🛠 Hedge Recovery SELL @ {A}\n"
                   f"Pair: {PAIR}\nQty: {qty:.8f} BTC @ {eff_bid:.2f}\n"
                   f"FeePnL: {fee_pnl:.6f}\nSnap: {snapshot()}")
            msgs.append(msg)
            _write_log([now,"A_SELL",qty,eff_bid,fee_pnl,snapshot()])

    # B: negatīvs BTC (short) → taker BUY uz B
    if btcB < -IMB_THRESH_BTC and b_ask:
        deficit = (-IMB_THRESH_BTC) - btcB  # cik jāpaceļ līdz slieksnim
        max_qty = MAX_RECOVER_USDC / (b_ask * (1.0 + SLIPPAGE_BPS/10_000.0))
        qty = min(deficit, max(0.0, max_qty))
        if qty > 0:
            eff_ask = b_ask * (1.0 + SLIPPAGE_BPS/10_000.0)
            fee_pnl = _taker_buy(B, qty, eff_ask, TAKER_FEE_BPS_B)
            acted = True
            msg = (f"🛠 Hedge Recovery BUY @ {B}\n"
                   f"Pair: {PAIR}\nQty: {qty:.8f} BTC @ {eff_ask:.2f}\n"
                   f"FeePnL: {fee_pnl:.6f}\nSnap: {snapshot()}")
            msgs.append(msg)
            _write_log([now,"B_BUY",qty,eff_ask,fee_pnl,snapshot()])

    # paziņojumi (sūtām apvienoti, ja bija vairākas darbības)
    if acted and msgs:
        try:
            send("\n\n".join(msgs)[:4000])
        except Exception:
            pass

    return acted
