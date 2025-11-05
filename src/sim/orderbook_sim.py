import random
import time


class SimOrderBook:
    def __init__(self, mid):
        self.mid = mid
        self.spread_bps = 1.5    # ~1.5 bps typical BTC spread sim
        self.volatility = 0.0005 # random walk step size
        self.update_ts = time.time()

        self._recalc()

    def _recalc(self):
        spread = self.mid * self.spread_bps / 10000
        self.bid = self.mid - spread/2
        self.ask = self.mid + spread/2

    def step(self):
        # simulate random walk
        move = self.mid * self.volatility * random.uniform(-1, 1)
        self.mid += move
        self._recalc()
