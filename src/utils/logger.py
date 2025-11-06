import time, csv, os
from pathlib import Path

def _open(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    first = not os.path.exists(path)
    f = open(path, "a", newline="")
    w = csv.writer(f)
    return f, w, first

class CsvLog:
    def __init__(self, path, header):
        self.path = path
        self.f, self.w, first = _open(path)
        if first: self.w.writerow(header); self.f.flush()
    def row(self, *vals):
        self.w.writerow([time.time(), *vals]); self.f.flush()
    def close(self):
        try: self.f.close()
        except: pass
