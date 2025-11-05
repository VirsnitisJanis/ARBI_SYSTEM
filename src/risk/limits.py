class Limits:
    def __init__(self, balances, min_usdc: float, max_gross: float):
        self.bal = balances
        self.min_usdc = float(min_usdc)
        self.max_gross = float(max_gross)

    def can_open(self, venue_open: str, notional_usdc: float):
        snap = self.bal.snapshot()
        if snap[venue_open]["USDC"] < self.min_usdc: 
            return False, "MIN_USDC"
        if notional_usdc > self.max_gross:
            return False, "GROSS_LIMIT"
        return True, "OK"
