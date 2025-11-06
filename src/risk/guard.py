import os, time, json
from pathlib import Path

LOG_DIR = Path(os.getenv("LOG_DIR", "logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)
PNL_FILE = LOG_DIR / "pnl_daily.json"

def _load():
    if PNL_FILE.exists():
        try: return json.loads(PNL_FILE.read_text())
        except: return {"day": _day(), "pnl": 0.0}
    return {"day": _day(), "pnl": 0.0}

def _save(s): PNL_FILE.write_text(json.dumps(s, indent=2))
def _day(): return time.strftime("%Y-%m-%d", time.gmtime())

def add_pnl(delta):
    s = _load()
    if s.get("day") != _day(): s = {"day": _day(), "pnl": 0.0}
    s["pnl"] = float(s.get("pnl", 0.0)) + float(delta)
    _save(s)
    return s["pnl"]

def get_day_pnl():
    s = _load()
    if s.get("day") != _day(): return 0.0
    return float(s.get("pnl", 0.0))
