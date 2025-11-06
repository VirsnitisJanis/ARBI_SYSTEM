import asyncio
import os
import subprocess
import time

from notify import send

PAIRS = os.getenv("PAIRS", "BTC/USDC,ETH/USDC").split(",")
RUN_LIMIT_S = int(os.getenv("AGENT_RUN_LIMIT_S", "1800"))  # restart katras 30min

async def run_agent(pair):
    env = os.environ.copy()
    env["PAIR"] = pair
    proc = await asyncio.create_subprocess_exec(
        "python3", "src/main_cross_m2m.py",
        env=env
    )
    start = time.time()
    print(f"[SPAWN] {pair} pid={proc.pid}")
    while True:
        await asyncio.sleep(10)
        if proc.returncode is not None:
            print(f"[RESTART] {pair} exited.")
            send(f"⚠️ {pair} agent exited, restarting…")
            return
        if time.time() - start > RUN_LIMIT_S:
            proc.kill()
            print(f"[RESTART] {pair} timed out after {RUN_LIMIT_S}s")
            send(f"♻️ {pair} agent restarted after timeout.")
            return

async def heartbeat():
    while True:
        send("💓 SYSTEM ALIVE — all agents running.")
        await asyncio.sleep(600)  # ik pēc 10 minūtēm

async def main():
    send("🚀 Multi-pair M2M controller started.")
    await asyncio.gather(
        heartbeat(),
        *[run_agent(p.strip()) for p in PAIRS]
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("exit")
