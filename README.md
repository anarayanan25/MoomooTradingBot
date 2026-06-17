# Moomoo Autonomous Trading Bot

An autonomous momentum trading bot for US stocks built on the Moomoo OpenAPI. Runs fully automated paper trades via a Python decision engine, with Claude as a conversational interface — no dashboard needed.

---

## What It Does

- Scans 18 US stocks every 5 minutes during market hours
- Detects momentum buy signals: price +2% above the 2-hour rolling low
- Automatically places paper buy and sell orders via the Moomoo API
- Exits positions at +3% take profit or -1.5% stop loss
- Tracks daily P&L with a circuit breaker that stops new buys if losses exceed $150/day
- Persists open positions to disk — survives bot restarts
- Auto-restarts on crash or Mac reboot via macOS launchd

**Trading mode: SIMULATE only (paper trading hardcoded — cannot accidentally go live)**

---

## Architecture

```
Claude (conversational interface)
        |
moomooapi skill (~/.claude/skills/moomooapi)
        |
Decision Engine (this repo)
        |
moomoo Python SDK (moomoo-api pip package)
        |
OpenD GUI v10.5.6508 (local gateway, port 11111)
        |
Moomoo Servers / Exchange
```

---

## Requirements

- Python 3.13
- [Moomoo OpenD GUI](https://www.moomoo.com/download) v10.5.6508 running locally on port 11111
- `moomoo-api` Python SDK

```bash
pip install moomoo-api
```

---

## Setup

1. Download and launch **Moomoo OpenD GUI** — must be running before starting the bot
2. Log in to your Moomoo account in OpenD
3. Clone this repo and install dependencies:

```bash
git clone https://github.com/anarayanan25/MoomooTradingBot
cd MoomooTradingBot
pip install moomoo-api
```

4. Run the bot manually:

```bash
python3 main.py
```

5. Stop the bot:

```
Ctrl+C
```

### Auto-restart with launchd (macOS)

To run the bot as a background service that auto-restarts on crash or Mac reboot:

```bash
# Copy the plist to LaunchAgents
cp com.anand.moomoobot.plist ~/Library/LaunchAgents/

# Load and start the service
launchctl load ~/Library/LaunchAgents/com.anand.moomoobot.plist

# Check status
launchctl list | grep moomoobot

# Stop the service
launchctl unload ~/Library/LaunchAgents/com.anand.moomoobot.plist
```

> **Note:** The bot directory must be outside `~/Desktop` and `~/Documents` for launchd to have access. Recommended location: `~/MoomooTradingBot/`

---

## Trading Strategy

**Momentum strategy** — buys stocks breaking upward from a 2-hour base with volume and institutional flow confirmation.

| Parameter | Value |
|-----------|-------|
| Buy signal | Price >= +2% above 2hr rolling low |
| Volume filter | Current bar volume >= 1.5x avg bar volume (confirms real momentum) |
| Capital flow filter | Net intraday institutional inflow must be positive |
| Take profit | +3% from entry price |
| Stop loss | -1.5% from entry price |
| Risk/reward | 2:1 |
| Scan interval | Every 5 minutes |
| Max concurrent positions | 3 |
| Position size | $1,000 USD per trade |
| Trading hours | 10:00am – 3:45pm ET (avoids noisy open/close) |
| Circuit breaker | Stop new buys if daily loss > $150 |

**Buy signal chain:** Price breakout → Volume surge → Institutional inflow → Buy

**Watchlist (18 symbols):**
- Mag 7: AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA
- ETFs: SMH, VOO, QQQ, SPCX
- Others: TSM, AVGO, BABA, PANW, MU, MRVL, ANET

---

## File Structure

```
MoomooTradingBot/
├── main.py                    # Entry point — scheduler and main scan loop
├── config.py                  # Watchlist, strategy thresholds, risk parameters
├── market_data.py             # Live quote fetching, market open detection, kline preload
├── strategy.py                # Buy/sell signal logic, rolling 2hr price history
├── executor.py                # Order placement (hardcoded SIMULATE — paper only)
├── risk.py                    # Position tracker, circuit breaker, daily P&L
├── start_bot.sh               # Shell wrapper for launchd auto-restart
├── com.anand.moomoobot.plist  # macOS launchd service definition
└── logs/
    ├── bot.log                # Full runtime log
    ├── positions.json         # Open positions (persisted across restarts)
    ├── launchd_stdout.log     # stdout when running as launchd service
    └── launchd_stderr.log     # stderr when running as launchd service
```

---

## Key Design Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| Trading lock | Hardcoded `TrdEnv.SIMULATE` in executor.py | Config file too easy to accidentally change |
| Interface | Claude conversational via skills | No UI to build, fully natural language |
| Price history | Kline preload at startup + live rolling window | Signals ready immediately, no 2hr wait |
| Volume history | Kline preload + per-bar delta from cumulative day volume | Tracks actual bar activity without extra API calls |
| Capital flow timing | Only called after price + volume signals pass | Minimises API calls — only fires on real candidates |
| Capital flow fail-open | Returns True if API errors | Never blocks a trade due to a connectivity issue |
| Position persistence | JSON file on disk | Survives bot restarts without stale data |
| Max positions guard | Pending buys lock + position count | Prevents race condition double-buys |

---

## Risk Management

- Paper trading only — hardcoded, cannot go live without a code change in `executor.py`
- Max $1,000 per trade, max 3 concurrent positions ($3,000 max deployed)
- Stop loss at -1.5% per position (max ~$15 loss per trade)
- Circuit breaker: no new buys if daily realized loss exceeds $150
- Time-of-day filter: only trades 10:00am–3:45pm ET

---

## Paper Trading Performance (as of Jun 15, 2026)

| Metric | Value |
|--------|-------|
| Starting capital | $1,000,000 (paper) |
| Account value | $1,001,464.59 |
| Realized P&L | -$103.72 |
| Total closed trades | 20 |
| Wins (take profit) | 8 |
| Losses (stop loss) | 12 |
| Win rate | 40% |
| Avg take profit | +$31.62 |
| Avg stop loss | -$29.72 |

> ⚠️ **Note:** Avg stop loss heavily skewed by a single AVGO gap-down event on Jun 15 (-$171.40 / -17.9%). Excluding that outlier: avg stop loss -$15.13, win rate 40%, net realized P&L +$67.68. Overnight gap risk is the primary outstanding issue with the current strategy.

---

## Known Issues & Fixes

| Issue | Fix Applied |
|-------|-------------|
| Race condition causing double buys | Pending buys lock in `risk.py` + 300s scan throttle in `main.py` |
| Bot not auto-restarting on crash | macOS launchd service added (Jun 2026) |
| launchd blocked from `~/Desktop` | Bot moved to `~/MoomooTradingBot/` |

---

## Roadmap

- **Phase 5 (complete):** Paper trading validation — 2+ weeks of live trade data collected
- **Phase 5b (current):** launchd auto-restart for reliability
- **Phase 6:** AWS EC2 deployment for 24/7 operation + email alerts via AWS SES
- **Phase 7:** Questrade prototype — port strategy to Canadian broker API
