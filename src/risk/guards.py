import os
MAX_GROSS = float(os.getenv("MAX_GROSS_NOTIONAL", "100"))
MIN_USDC  = float(os.getenv("MIN_AVAIL_USDC", "10"))

def check_balances(bnz_usdc, kuc_usdc):
    if bnz_usdc < MIN_USDC or kuc_usdc < MIN_USDC:
        return False, f"MIN_AVAIL guard: binance={bnz_usdc}, kucoin={kuc_usdc}"
    return True, "OK"

def check_gross(open_gross):
    if open_gross > MAX_GROSS:
        return False, f"MAX_GROSS guard: {open_gross} > {MAX_GROSS}"
    return True, "OK"
