import math

def round_price(p, tick):
    return math.floor(p / tick) * tick

def round_amount(a, step):
    return math.floor(a / step) * step

def bps(x):  # 1 bps = 0.0001
    return x * 1e-4
