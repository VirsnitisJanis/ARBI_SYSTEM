# src/utils/balances.py
import json
import os

BAL_FILE = "data/balances.json"

# sākotnējās bilances glabāšana atmiņā
s = {
    "binance": {"USDC": 0.0, "BTC": 0.0},
    "kucoin": {"USDC": 0.0, "BTC": 0.0},
    "kraken": {"USDC": 0.0, "BTC": 0.0},
}

# ─────────────────────────────────────────────
def snapshot():
    """Atgriež bilances kopiju kā JSON stringu."""
    return json.loads(json.dumps(s))

# ─────────────────────────────────────────────
def get(venue, asset):
    """Droši saņem aktīva bilanci. Ja neeksistē, inicializē 0."""
    if venue not in s:
        s[venue] = {"USDC": 0.0, "BTC": 0.0}
    if asset not in s[venue]:
        s[venue][asset] = 0.0
    return float(s[venue][asset])

# ─────────────────────────────────────────────
def adjust(venue, asset, delta):
    """Maina bilanci (piem., pēc hedžiem)."""
    if venue not in s:
        s[venue] = {"USDC": 0.0, "BTC": 0.0}
    if asset not in s[venue]:
        s[venue][asset] = 0.0
    s[venue][asset] += delta
    return s[venue][asset]

# ─────────────────────────────────────────────
def save():
    """Saglabā bilances failā."""
    os.makedirs(os.path.dirname(BAL_FILE), exist_ok=True)
    with open(BAL_FILE, "w") as f:
        json.dump(s, f, indent=2)
