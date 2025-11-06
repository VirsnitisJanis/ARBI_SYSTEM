import os, asyncio, subprocess, time
from notify import send
from utils.balances import snapshot

# ========= CONFIG ==========
PAIRS = os.getenv("PAIRS", "BTC/USDC,ETH/USDC").split(",")
EDGE_MIN = float(os.getenv("EDGE_TRIGGER_BPS", "2.0"))
MAX_BOTS = int(os.getenv("MAX_BOTS", "4"))
CHECK_INTERVAL = float(os.getenv("CHECK_INTERVAL_S", "15"))
PY_PATH = os.getenv("PYTHON_PATH", "python3")
ROUTER = "src/smart_hedge_router_protected.py"
# ===========================

active = {}

async def spawn_bot(pair):
    """Palaiž jaunu hedge router procesu."""
    log = f"logs/auto_{pair.replace('/','-')}.log"
    cmd = [
        PY_PATH, ROUTER
    ]
    env = os.environ.copy()
    env["PAIR"] = pair
    p = subprocess.Popen(cmd, env=env, stdout=open(log, "a"), stderr=subprocess.STDOUT)
    active[pair] = p
    send(f"🚀 AUTO-SPAWN {pair} pid={p.pid}")
    print(f"[SPAWN] {pair} pid={p.pid}")

async def monitor():
    """Skenē edge, pārvalda procesus."""
    while True:
        snap = snapshot()
        # ja kāds bots beidzies
        for pair, proc in list(active.items()):
            if proc.poll() is not None:
                send(f"🧩 BOT EXIT {pair} code={proc.returncode}")
                active.pop(pair, None)

        # pārbaude vai jāsāk jauns bots
        for pair in PAIRS:
            if len(active) >= MAX_BOTS:
                break
            if pair not in active:
                # šeit varētu nākotnē lasīt no live edge monitor
                await spawn_bot(pair)

        send(f"📊 ACTIVE={list(active.keys())}\nSnap: {snap}")
        await asyncio.sleep(CHECK_INTERVAL)

async def main():
    print(f"[BOOT] Auto-Scaler Manager — monitoring {PAIRS}")
    send(f"🧠 Auto-Scaler started\nPairs: {PAIRS}")
    await monitor()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("exit")
