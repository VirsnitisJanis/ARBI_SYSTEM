import os, json, ccxt
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent.parent / "data_balances.json"

def load_snapshot():
    if DATA_FILE.exists():
        with open(DATA_FILE) as f:
            return json.load(f)
    return {}

def save_snapshot(data):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)
    print(f"[SAVE] Balances saved to {DATA_FILE}")

def sync_from_ccxt():
    import os
    exchs = {
        "binance": ccxt.binance({
            "apiKey": os.getenv("BINANCE_API_KEY"),
            "secret": os.getenv("BINANCE_SECRET_KEY")
        }),
        "kucoin": ccxt.kucoin({
            "apiKey": os.getenv("KUCOIN_API_KEY"),
            "secret": os.getenv("KUCOIN_SECRET_KEY"),
            "password": os.getenv("KUCOIN_PASSPHRASE")
        }),
        "kraken": ccxt.kraken({
            "apiKey": os.getenv("KRAKEN_API_KEY"),
            "secret": os.getenv("KRAKEN_SECRET_KEY")
        })
    }

    snap = {}
    for name, ex in exchs.items():
        try:
            bal = ex.fetch_balance()
            snap[name] = {
                "USDC": float(bal["free"].get("USDC", 0)),
                "BTC": float(bal["free"].get("BTC", 0)),
                "ETH": float(bal["free"].get("ETH", 0))
            }
            print(f"[SYNC] {name} ok:", snap[name])
        except Exception as e:
            snap[name] = {"USDC": 0.0, "BTC": 0.0, "ETH": 0.0}
            print(f"[SYNC] {name} ERR:", e)

    save_snapshot(snap)
    return snap

# === Legacy compatibility alias ===
def snapshot():
    """Saglabāta saderība ar veco kodu — atgriež aktuālo bilances snapshot"""
    return load_snapshot()
