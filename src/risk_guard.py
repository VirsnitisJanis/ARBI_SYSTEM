import os
import json
import time
from notify import send
from utils.balances import snapshot

# Configurable thresholds
STOP_PNL = float(os.getenv("STOP_PNL_USD", "-0.10"))
MAX_LOSS_COUNT = int(os.getenv("MAX_LOSS_COUNT", "3"))
ORDERS_FILE = "logs/open_orders.json"
PNL_FILE = "logs/pnl_state.json"

# Internal state
loss_streak = 0

def read_json_safe(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}

def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def check_orders():
    """Remove stuck orders (older than 180s)"""
    orders = read_json_safe(ORDERS_FILE)
    now = time.time()
    cleared = []
    for oid, info in list(orders.items()):
        if now - info.get("ts", now) > 180:
            cleared.append(oid)
            del orders[oid]
    if cleared:
        send(f"⚠️ Cleared {len(cleared)} stuck orders:\n{cleared}")
        write_json(ORDERS_FILE, orders)

def check_pnl():
    """Stop bot if cumulative PnL is below threshold"""
    global loss_streak
    pnl_state = read_json_safe(PNL_FILE)
    total_pnl = sum(pnl_state.get("pnl_history", []))
    if total_pnl < STOP_PNL:
        loss_streak += 1
        send(f"🚨 RISK ALERT\nPnL={total_pnl:.4f} USD (streak {loss_streak})")
        if loss_streak >= MAX_LOSS_COUNT:
            send(f"🛑 TRADING HALT — cumulative loss {total_pnl:.4f} USD")
            print("[HALT] Trading stopped due to PnL threshold breach.")
            with open("logs/HALT_FLAG", "w") as f:
                f.write(f"halted {time.ctime()} | PnL={total_pnl:.4f}")
            return False
    else:
        loss_streak = 0
    return True

def guard_loop(interval_s=60):
    print("[BOOT] Risk Guard active — monitoring PnL and stuck orders.")
    send("🧠 Risk Guard module active (Stage-18).")
    while True:
        check_orders()
        ok = check_pnl()
        if not ok:
            break
        print(f"[CHECK] OK @ {time.strftime('%H:%M:%S')} | snapshot {snapshot()}")
        time.sleep(interval_s)

if __name__ == "__main__":
    guard_loop(60)
