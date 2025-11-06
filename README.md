# ARBI_SYSTEM — Multi-Exchange Smart Hedging Framework

**Version:** Stage-20 (Auto-Scaler Manager Complete)  
**Author:** Jānis Virsnītis  
**Goal:** Fully autonomous arbitrage & hedging system operating across multiple exchanges (Binance, KuCoin, Kraken).  

---

## 🚀 Overview
ARBI_SYSTEM is a modular **cross-exchange arbitrage framework** that automatically identifies profitable spreads, executes hedge orders, manages risk, and scales to multiple assets and venues.  
It is built with Python + CCXT and includes its own routing, PnL tracking, Telegram notifications, and adaptive intelligence layers.

---

## 🧩 Architecture


ARBI_SYSTEM/
├── src/
│ ├── main_cross_live_safe.py # Stage-9–14 safe live trading core
│ ├── smart_hedge_router.py # Stage-16 adaptive routing simulation
│ ├── smart_hedge_router_live.py # Stage-17 real post-only hedge logic
│ ├── smart_hedge_router_protected.py # Stage-19 protected mode with stop-PnL
│ ├── auto_scaler_manager.py # Stage-20 auto-spawns hedge agents
│ ├── pnl_dashboard.py # PnL summary
│ ├── pnldash_plot.py # Stage-15 PnL chart with alerts
│ ├── utils/ # balance, heartbeat, risk, notify tools
│ ├── engine/ # maker logic, PnL tracker
│ ├── exchanges/
│ │ ├── binance_client.py
│ │ ├── kucoin_client.py
│ │ └── kraken_client.py
│ └── notify.py # Telegram notifier
│
├── logs/ # runtime logs, fills, PnL, system stats
├── .env.local # API keys & parameters
└── README.md

---

## 🧠 Stage Summary (1–20)

| Stage | Title | Key Outcome |
|-------|--------|-------------|
| 1 | Init repo + venv | Basic structure, logging & CCXT integration |
| 2 | Core live loop | Live feed between exchanges |
| 3 | Maker–Maker test | Local simulator for post-only orders |
| 4 | Safe balances | JSON ledger simulation |
| 5 | CCXT ticker sync | Real-time bid/ask polling |
| 6 | PnL tracking | CSV-based trade accounting |
| 7 | Telegram alerts | Notifications for fills & restarts |
| 8 | Circuit breaker | Auto-restart after errors |
| 9 | Heartbeat system | Regular system health ping |
| 10 | Hedge Recovery | Detects imbalance and re-hedges |
| 11 | Kraken integration | Added 3rd exchange |
| 12 | Smart edge filter | Adaptive spread logic |
| 13 | Multi-venue coordinator | Tri-exchange routing control |
| 14 | Real-time PnL dashboard | ASCII monitor with live data |
| 15 | PnL plot dashboard | Graphical matplotlib tracking |
| 16 | Smart Hedge Router | Adaptive route simulation |
| 17 | Live hedge router | Real execution with order errors handled |
| 18 | Protected router | Stop-loss and recovery logic |
| 19 | Risk Guard | Monitors PnL & halts on threshold breach |
| 20 | Auto-Scaler Manager | Spawns & monitors multiple hedge bots |

---

## ⚙️ Run Example

```bash
source venv/bin/activate
export $(grep -v '^#' .env.local | xargs)

# start the auto-scaler
python3 src/auto_scaler_manager.py




---

## 🧠 Stage-21 — Dynamic Pair Discovery + TG Summary

Automātiski atrod USDC pārus, kas pieejami vismaz uz 2 biržām, respektē `pairs.json` (ja ir), WL/BL un budžetu.

### Palaišana
```bash
source venv/bin/activate
export $(grep -v '^#' .env.local | xargs)

# (brīvprātīgi) manuāls saraksts ar prioritāti
cat > pairs.json << 'JSON'
{ "monitor": ["BTC/USDC", "ETH/USDC", "SOL/USDC"] }
JSON

# parametri
export DISCOVERY_SEC=120
export MIN_QUOTES_USDC=10
export MAX_AGENTS=6
export USE_EXCHANGES="binance,kucoin,kraken"

# router skripts un tā parametri (Stage-17/19)
export ROUTER_SCRIPT="src/smart_hedge_router_protected.py"
export EDGE_OPEN_BPS=2.0
export HEDGE_SIZE_BTC=0.0004
export ADAPTIVE_COEFF=0.6
export CHECK_INTERVAL_S=2.0
export STOP_PNL_USD=-0.10
export RECOVERY_WAIT_S=90

# start
python3 src/auto_scaler_manager.py

