✅ Projekta Roadmap
Stage 1: One-asset Cross-Exchange Hedge Engine (BTC)

Binance ↔ KuCoin
USDC as base
1 order + hedging leg
Sim + logs + balance check
→ 5–10 EUR/day potential on tiny capital

Mērķis:
Stabils, drošs, reproducējams piesitiens.

Stage 2: Multi-asset (BTC + ETH)

Tā pati arhitektūra
Pievienojam ETH kanālu
Labojam fee + slippage modeļus
→ 2x opportunities

Stage 3: Multi-exchange (Binance + KuCoin + Kraken)

Price stream sync
Balance map
Auto route cheapest fees

Stage 4: Cross-exchange Triangular

Examples:

Binance: USDC → BTC
KuCoin:  BTC → ETH
Binance: ETH → USDC


Un reverse flows.
Tas jau ir hedged triangle engine.

Stage 5: Full Agent Framework

Risk agent
Latency agent
Position sync
Auto size adjust
Telegram alerts
Rate-limit scheduler