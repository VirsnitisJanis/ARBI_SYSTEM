from core.tri_core import make_tri_symbols, PriceBus, TriEngine

s = make_tri_symbols()
bus = PriceBus()
bus.update(s.a_b, 100, 101)
bus.update(s.b_c, 0.034, 0.035)
bus.update(s.a_c, 3400, 3401)

eng = TriEngine(s)
edge = eng.compute_edge(bus.get(s.a_b), bus.get(s.b_c), bus.get(s.a_c))

print("EDGE =", edge)
