import os, json, ccxt
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent.parent / "data_balances.json"

def load_snapshot():
    """Load balances snapshot from JSON file"""
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text())
        except Exception:
            return {}
    return {}

def save_snapshot(data):
    """Save balances snapshot"""
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(data, indent=2))

def get(exchange: str, asset: str) -> float:
    """Return specific balance value"""
    snap = load_snapshot()
    return float(snap.get(exchange, {}).get(asset, 0.0))

def adjust(exchange: str, asset: str, delta: float):
    """Adjust stored balance after simulated or real trade"""
    snap = load_snapshot()
    snap.setdefault(exchange, {}).setdefault(asset, 0.0)
    snap[exchange][asset] += delta
    save_snapshot(snap)

def snapshot():
    """Legacy-compatible accessor"""
    return load_snapshot()

def sync_from_ccxt():
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
        }),
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
