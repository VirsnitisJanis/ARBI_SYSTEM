# src/main_cross_live_safe.py

import asyncio
import csv
import os
import time

import ccxt

from engine.maker_engine import place_maker, process_maker_order, settle_fill
from heartbeat import beat
from hedge_recovery import check_and_recover  # Stage-7 Hedge Recovery
from notify import send
from utils.balances import get, snapshot

# ─────────────────────────────────────────────────────────────
# Konfigurācija / ENV
# ─────────────────────────────────────────────────────────────
PAIR = os.getenv("PAIR", "BTC/USDC")
A = os.getenv("VENUE_A", "binance")
B = os.getenv("VENUE_B", "kucoin")

NOTIONAL = float(os.getenv("NOTIONAL_USDC", "25"))

EDGE_OPEN = float(os.getenv("EDGE_OPEN_BPS", "2.0"))      # min net edge (bps) lai atvērtu
EDGE_CANCEL = float(os.getenv("EDGE_CANCEL_BPS", "1.0"))  # ja nokrīt zem šī → atceļam

# Maksa / slippage parametri
FEE_BPS_A = float(os.getenv("MAKER_FEE_BPS_A", "1.0"))    # maker A (binance)
FEE_BPS_B = float(os.getenv("TAKER_FEE_BPS_B", "8.0"))    # taker B (kucoin)
PRICE_PAD_BPS = float(os.getenv("PRICE_PAD_BPS", "0.8"))  # maker cenu pabīde zem bid
HEDGE_SLIPPAGE_BPS = float(os.getenv("HEDGE_SLIPPAGE_BPS", "0.5"))

# Peļņas kontrole
EXPECTED_PNL_MIN = float(os.getenv("EXPECTED_PNL_MIN_USDC", "0.0005"))
VOL_PAD_FACTOR = float(os.getenv("VOL_PAD_FACTOR", "0.25"))  # cik agresīvi koriģēt pēc svārstībām
VOL_PAD_FLOOR = float(os.getenv("VOL_PAD_FLOOR_BPS", "0.5"))

# Drošības/servisa parametri
MAX_INV_BTC = float(os.getenv("MAX_INV_BTC", "0.0025"))
TTL = float(os.getenv("MAKER_TTL_S", "4"))
RESTART_DELAY = float(os.getenv("RESTART_DELAY_S", "60"))
LOG = os.getenv("LIVE_LOG_PATH", "logs/live_safe.csv")

# CCXT klienti
ca, cb = ccxt.binance(), ccxt.kucoin()


# ─────────────────────────────────────────────────────────────
# Stage-9: Telegram Heartbeat Ping
# ─────────────────────────────────────────────────────────────
async def heartbeat_ping(interval_s: float = 3600.0):
    """Ik stundu sūta sistēmas statusu Telegramā."""
    while True:
        try:
            send(f"💗 SYSTEM ALIVE — {PAIR}\nSnap: {snapshot()}")
        except Exception as e:
            print("[HB ERROR]", e)
        await asyncio.sleep(interval_s)


# ─────────────────────────────────────────────────────────────
# Edge/PnL aprēķins ar “smart gate”
# ─────────────────────────────────────────────────────────────
def compute_edges(a_bid, a_ask, b_bid, b_ask):
    mid = (a_bid + a_ask + b_bid + b_ask) / 4.0
    raw_bps = ((b_bid - a_ask) / mid) * 10000.0

    fees_bps = (FEE_BPS_A + FEE_BPS_B)
    vol_pad_bps = max(VOL_PAD_FLOOR, abs(raw_bps) * VOL_PAD_FACTOR)
    total_pad_bps = fees_bps + vol_pad_bps + HEDGE_SLIPPAGE_BPS

    net_bps = raw_bps - total_pad_bps
    exp_pnl_usdc = NOTIONAL * (net_bps / 10000.0)

    return raw_bps, net_bps, exp_pnl_usdc


# ─────────────────────────────────────────────────────────────
# Galvenais tirdzniecības cikls
# ─────────────────────────────────────────────────────────────
async def run_cycle():
    maker = None

    print(f"[BOOT SAFE LIVE] {A}<->{B} {PAIR}")
    print("[INIT SNAP]", snapshot())

    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a"):
        pass

    while True:
        beat()

        # Fetch tirgus datus paralēli
        ta, tb = await asyncio.gather(
            asyncio.to_thread(ca.fetch_ticker, PAIR),
            asyncio.to_thread(cb.fetch_ticker, PAIR),
        )

        a_bid, a_ask = ta.get("bid"), ta.get("ask")
        b_bid, b_ask = tb.get("bid"), tb.get("ask")

        if not all(v is not None for v in (a_bid, a_ask, b_bid, b_ask)):
            print("[TICK SKIP] missing quotes")
            await asyncio.sleep(0.35)
            continue

        # Edge + paredzamais PnL
        raw_bps, net_bps, exp_pnl = compute_edges(a_bid, a_ask, b_bid, b_ask)
        print(f"[EDGE] raw={raw_bps:.2f}bps net={net_bps:.2f}bps expPnL={exp_pnl:.6f} | maker={maker}")

        # Log tick
        try:
            with open(LOG, "a", newline="") as f:
                csv.writer(f).writerow([time.time(), a_bid, a_ask, b_bid, b_ask, raw_bps, net_bps, exp_pnl, "TICK"])
        except Exception as e:
            print("[LOG ERROR]", e)

        # Inventory drošība
        if get(A, "BTC") > MAX_INV_BTC or get(B, "BTC") > MAX_INV_BTC:
            msg = f"⚠️ HALT — inventory limit hit.\nSnap: {snapshot()}"
            print(msg)
            try:
                send(msg)
            except Exception as e:
                print("[TG ERROR]", e)
            raise RuntimeError("inventory limit")

        # Stage-7: Hedge Recovery (pirms jauna ordera)
        try:
            recovered = check_and_recover(a_bid, a_ask, b_bid, b_ask)
        except Exception as e:
            print("[RECOVERY ERROR]", e)
            recovered = False
        if recovered:
            await asyncio.sleep(0.25)
            continue

        # Jauna maker ordera atvēršana — profit-sensitive gate
        if (
            maker is None
            and net_bps >= EDGE_OPEN
            and exp_pnl >= EXPECTED_PNL_MIN
            and get(A, "USDC") >= NOTIONAL
        ):
            size = NOTIONAL / a_ask
            price = a_bid * (1.0 - PRICE_PAD_BPS / 10000.0)
            maker = place_maker("buy", A, price, size)
            maker["ts"] = time.time()
            print("[PLACE A]", maker)

        # Maker ordera pārvaldība
        if maker:
            status, reason = process_maker_order(maker, {"bid": a_bid, "ask": a_ask})

            # Timeout vai edge sabrukums → atceļam
            if time.time() - maker["ts"] > TTL or net_bps < EDGE_CANCEL:
                maker["expiry"] = 0
                status, reason = (False, "CANCEL")

            if status is True:
                pnl = settle_fill(maker, b_bid)  # hedge uz B taker
                print("[FILL]", pnl, snapshot())
                try:
                    send(
                        "✅ HEDGE FILL\n"
                        f"Pair: {PAIR}\n"
                        f"VenueA: {A}\n"
                        f"VenueB: {B}\n"
                        f"PnL: {pnl:.6f}\n"
                        f"Wallets: {snapshot()}"
                    )
                except Exception as e:
                    print("[TG ERROR]", e)
                try:
                    with open(LOG, "a", newline="") as f:
                        csv.writer(f).writerow([time.time(), "FILL", pnl, snapshot()])
                except Exception as e:
                    print("[LOG ERROR]", e)
                maker = None

            elif status is False:
                print("[EXPIRE]", reason)
                maker = None

        await asyncio.sleep(0.35)


# ─────────────────────────────────────────────────────────────
# Auto-restart cilpa (Stage-8: Circuit Breaker + Restart)
# ─────────────────────────────────────────────────────────────
async def loop():
    asyncio.create_task(heartbeat_ping(3600.0))  # Stage-9 heartbeat
    while True:
        try:
            await run_cycle()
        except Exception as e:
            print(f"[CIRCUIT BREAK] {e}")
            try:
                send(f"🚨 CIRCUIT BREAK — {e}\nSystem cooling {RESTART_DELAY}s.")
            except Exception as te:
                print("[TG ERROR]", te)
            await asyncio.sleep(RESTART_DELAY)
            print("[RESTART] Attempting to resume trading…")
            try:
                send("🔁 Restarting trading cycle…")
            except Exception as te:
                print("[TG ERROR]", te)
            # turpinām cilpu


# ─────────────────────────────────────────────────────────────
# Palaišana
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        asyncio.run(loop())
    except KeyboardInterrupt:
        print("exit")
