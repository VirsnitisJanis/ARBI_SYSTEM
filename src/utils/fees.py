import os

def bps_from_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default

# Taker komisijas (bps)
TAKER_BPS_BINANCE = bps_from_env("TAKER_FEE_BPS_BINANCE", 6.0)   # 0.06%
TAKER_BPS_KUCOIN  = bps_from_env("TAKER_FEE_BPS_KUCOIN", 8.0)    # 0.08%

# Maker “rebate” netiek modelēts (pieņemam ~0)
MAKER_BPS = bps_from_env("MAKER_FEE_BPS", 0.0)

# Papildu drošības spilvens uz hedge legu
SLIPPAGE_BPS = bps_from_env("SLIPPAGE_BPS", 0.5)
