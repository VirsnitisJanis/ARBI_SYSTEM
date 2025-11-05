import json, os, threading, time
from pathlib import Path

_STATE = Path("src/data/balances.json")
_LOCK = threading.Lock()

def _ensure():
    _STATE.parent.mkdir(parents=True, exist_ok=True)
    if not _STATE.exists():
        _STATE.write_text(json.dumps({"binance":{"USDC":0.0,"BTC":0.0},
                                      "kucoin":{"USDC":0.0,"BTC":0.0}}, indent=2))

def _load():
    _ensure()
    return json.loads(_STATE.read_text())

def _save(state):
    _STATE.write_text(json.dumps(state, indent=2))

def seed(venue, usdc=None, btc=None):
    with _LOCK:
        s = _load()
        if venue not in s: s[venue] = {"USDC":0.0,"BTC":0.0}
        if usdc is not None: s[venue]["USDC"] = float(usdc)
        if btc  is not None: s[venue]["BTC"]  = float(btc)
        _save(s)

def get(venue, asset):
    s = _load()
    return float(s[venue][asset])

def adjust(venue, asset, delta):
    with _LOCK:
        s = _load()
        s[venue][asset] = float(s[venue][asset]) + float(delta)
        _save(s)

def ensure_min(venue, asset, minimum):
    return get(venue, asset) >= float(minimum)

def snapshot():
    return _load()
