import json
import os
import time

import ccxt

from notify import send

THRESH = float(os.getenv("CROSS_REALLOC_THRESHOLD","0.15"))
DRY_RUN = os.getenv("DRY_RUN","1") == "1"
LIVE_CONFIRM = os.getenv("LIVE_CONFIRM","NO").upper() == "YES"

def load_book():
    path = os.path.join(os.path.dirname(__file__), "data", "address_book.json")
    with open(path) as f:
        return json.load(f)


def mk_clients():
    b = ccxt.binance({'apiKey':os.getenv('BINANCE_API_KEY'),'secret':os.getenv('BINANCE_SECRET_KEY')})
    k = ccxt.kucoin({'apiKey':os.getenv('KUCOIN_API_KEY'),
                     'secret':os.getenv('KUCOIN_SECRET_KEY'),
                     'password':os.getenv('KUCOIN_PASSPHRASE')})
    r = ccxt.kraken({'apiKey':os.getenv('KRAKEN_API_KEY'),'secret':os.getenv('KRAKEN_SECRET_KEY')})
    return {"binance":b,"kucoin":k,"kraken":r}

def fetch_balances(ex):
    out = {}
    for name, cli in ex.items():
        try:
            bal = cli.fetch_balance()
            out[name] = {
                "USDC": float(bal["free"].get("USDC",0.0)),
                "BTC":  float(bal["free"].get("BTC",0.0))
            }
        except Exception as e:
            out[name] = {"USDC":0.0,"BTC":0.0}
            print(f"[{name}] ERR:", e)
    return out

def plan_transfers(bals, asset):
    total = sum(b[asset] for b in bals.values())
    avg = total / len(bals)
    plan = []
    for ex, bal in bals.items():
        diff = bal[asset] - avg
        if abs(diff) > avg * THRESH:
            if diff > 0:
                plan.append((ex,"withdraw",diff))
            else:
                plan.append((ex,"deposit",abs(diff)))
    return plan

def main():
    ex = mk_clients()
    bals = fetch_balances(ex)
    book = load_book()

    msg = ["🏦 Stage-26 Cross-Allocator Summary\n"]
    for asset in ["USDC","BTC"]:
        plan = plan_transfers(bals, asset)
        if not plan:
            msg.append(f"✅ {asset}: all venues within ±{THRESH*100:.0f}%")
            continue

        msg.append(f"⚙️ {asset} reallocation plan:")
        for ex, act, amt in plan:
            rec = next((e for e in book[asset].keys() if e != ex), None)
            if not rec: continue
            dest = book[asset][rec]
            fee = book[asset][ex]["withdraw_fee"]
            net = max(0, amt - fee)
            txt = f"{ex.upper()} → {rec.upper()}: {amt:.4f} {asset} (fee {fee}, net {net:.4f})"
            msg.append("  "+txt)
            if DRY_RUN or not LIVE_CONFIRM:
                print("[PLAN]", txt)
                continue
            try:
                excli = ex[ex]
                txid = excli.withdraw(asset, amt, dest["address"], params={"network": dest["network"]})
                print(f"[EXEC {asset}] {ex} → {rec}: tx={txid}")
            except Exception as e:
                print(f"[ERR {asset}] {ex}: {e}")
    final = "\n".join(msg)
    print(final)
    send(final)

if __name__ == "__main__":
    main()
