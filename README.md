# Moomoo Autonomous Trading Bot

An autonomous momentum trading bot for US stocks built on the Moomoo OpenAPI. Runs fully automated paper trades via a Python decision engine, with Claude as a conversational interface — no dashboard needed.

---

## What It Does

- Scans 17 US stocks every 5 minutes during market hours
- Detects momentum buy signals: price +2% above the 2-hour rolling low
- Pre-screens watchlist daily — only scans stocks with active turnover (avoids dormant names)
- Confirms buys with volume surge (1.5x avg) and institutional capital inflow (big money filter)
- Checks broad market regime (SPY uptrend) before any buy — no trading against the market
- Filters overbought entries (RSI > 70) and falling knives (RSI < 40) using existing kline data
- Skips stocks already up >3% or down >2% on the day (momentum exhausted / earnings proxy)
- Confirms sector trend before buying individual stocks (semis → SMH, tech → QQQ)
- Automatically places paper buy and sell orders via the Moomoo API
- Exits positions at +3% take profit or -1.5% stop loss
- Real-time TP/SL monitoring via quote push subscriptions — fires on every tick, not just every 5 min
- Force-closes all positions at 3:30pm ET daily — eliminates overnight gap risk
- 30-minute re-entry cooldown after any stop loss — prevents buying back into a falling stock
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
| Stock filter | Pre-screen watchlist at market open; only buy-scan symbols with turnover ≥ 0.3% |
| Volume filter | Current bar volume >= 1.5x avg bar volume (confirms real momentum) |
| Market regime | SPY must be above its 10-bar rolling avg — no buys in a market downtrend |
| RSI filter | RSI 40–70 only — avoids overbought entries and falling knives |
| Gap filter | Skip if stock already up >3% or down >2% today (also catches earnings events) |
| Sector confirmation | Sector ETF (SMH/QQQ) must also be in uptrend before buying individual stock |
| Capital flow filter | Net intraday institutional inflow must be positive (total + big money) |
| Take profit | +3% from entry price |
| Stop loss | -1.5% from entry price |
| TP/SL monitoring | Real-time push (every tick) via StockQuoteHandlerBase, not just 5-min scan |
| Risk/reward | 2:1 |
| Scan interval | Every 5 minutes |
| Max concurrent positions | 3 |
| Position size | $1,000 USD per trade |
| Trading hours | 10:00am – 3:45pm ET (avoids noisy open/close) |
| EOD close | Force-close all positions at 3:30pm ET — no overnight holds |
| SL cooldown | 30-minute re-entry block after any stop loss |
| Circuit breaker | Stop new buys if daily loss > $150 |

**Buy signal chain (8 stages):**
Stock active → Price breakout → Volume surge → Market uptrend → RSI in range → No gap → Sector uptrend → Institutional inflow → Buy

**Watchlist (17 symbols):**
- Mag 7: AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA
- ETFs: SMH, VOO, QQQ
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
├── risk.py                    # Position tracker, circuit breaker, daily P&L, sell guard
├── monitor.py                 # Real-time position monitor (quote push subscriptions)
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
| Big money filter | Checks super+large order net inflow via get_capital_distribution | Filters retail-driven moves with no institutional backing |
| Stock filter | get_market_snapshot turnover rate, refreshed once per day | Avoids dormant stocks; falls back to full list if < 3 pass |
| Real-time monitor | Separate OpenQuoteContext with StockQuoteHandlerBase push | Fires TP/SL on every tick; main loop still handles buys |
| Double-sell guard | mark_selling/unmark_selling with threading.Lock in risk.py | Prevents race between 5-min scan and real-time monitor |
| EOD close | Force-sell all positions at 15:30 ET via close_all_positions() | Eliminates overnight gap risk entirely |
| SL cooldown | 30-min block on re-entry after stop loss (record_stop_loss/is_in_cooldown) | Prevents re-buying a falling stock immediately after being stopped out |
| SPCX removed | Removed SpaceX IPO from watchlist | IPO-stage volatility caused -3.4%, -6.1%, -7.6% overnight gaps — incompatible with strategy |
| Market regime filter | SPY 10-bar rolling avg check before any buy | Prevents buying individual stocks when the broad market is falling |
| RSI filter | 5-min RSI computed from existing kline data | Zero extra API calls — reuses price history already in memory |
| Gap filter | Daily snapshot fetched once at open; checks day's % change | Skips exhausted/weak stocks and doubles as earnings proxy |
| Sector confirmation | SMH/QQQ rolling avg check before semi/tech buys | Avoids buying a strong stock in a weak sector |
| Filter ordering | In-memory checks first, API call last | 4 new filters cost nothing; expensive API call only fires if all 7 prior checks pass |
| Position persistence | JSON file on disk | Survives bot restarts without stale data |
| Max positions guard | Pending buys lock + position count | Prevents race condition double-buys |

---

## Risk Management

- Paper trading only — hardcoded, cannot go live without a code change in `executor.py`
- Max $1,000 per trade, max 3 concurrent positions ($3,000 max deployed)
- Stop loss at -1.5% per position (max ~$15 loss per trade)
- 30-minute re-entry cooldown after any stop loss — no buying back into a falling stock
- EOD close: all positions force-sold at 3:30pm ET — no overnight exposure
- Circuit breaker: no new buys if daily realized loss exceeds $150
- Time-of-day filter: only trades 10:00am–3:45pm ET

---

## Paper Trading Performance (as of Jun 18, 2026)

| Metric | Value |
|--------|-------|
| Starting capital | $1,000,000 (paper) |
| Realized P&L | ~-$16 (recovering) |
| Total closed trades | ~26 |
| Win rate | ~40% |
| Avg take profit | ~+$32 |
| Avg stop loss | ~-$25 (skewed by gap events) |

> ⚠️ **Gap risk incidents:** AVGO Jun 15 (-$171.40 / -17.9%), SPCX Jun 16–18 (multiple -3% to -8% overnight gaps). Root cause: SpaceX IPO stock included in watchlist. SPCX removed Jun 18. EOD close and SL cooldown added to prevent recurrence.

---

## Known Issues & Fixes

| Issue | Fix Applied |
|-------|-------------|
| Race condition causing double buys | Pending buys lock in `risk.py` + 300s scan throttle in `main.py` |
| Double-sell between scan and monitor | `mark_selling`/`unmark_selling` atomic guard in `risk.py` |
| Bot not auto-restarting on crash | macOS launchd service added (Jun 2026) |
| launchd blocked from `~/Desktop` | Bot moved to `~/MoomooTradingBot/` |
| AVGO gap-down -17.9% overnight | EOD close at 3:30pm ET now eliminates overnight exposure |
| SPCX consecutive overnight gaps (-3.4%, -6.1%, -7.6%) | SPCX (SpaceX IPO) removed from watchlist — IPO volatility incompatible with strategy |
| Bot re-entering immediately after stop loss | 30-min SL cooldown added — `record_stop_loss`/`is_in_cooldown` in `risk.py` |

---

## Roadmap

- **Phase 5 (complete):** Paper trading validation — 2+ weeks of live trade data collected
- **Phase 5b (complete):** launchd auto-restart for reliability
- **Phase 5c (complete):** Signal quality enhancements — volume, capital flow, big money filter, stock filter, real-time monitor
- **Phase 5d (complete):** Risk management fixes — EOD close, SL cooldown, SPCX removed
- **Phase 5e (complete):** Advanced signal filters — market regime, RSI, gap/earnings, sector confirmation
- **Phase 6:** AWS EC2 headless deployment (Ubuntu + Command Line OpenD) for 24/7 operation + email alerts via AWS SES. PDT $25K rule eliminated Jun 4, 2026 — standard $2,000 margin account sufficient (verify Moomoo has implemented).
- **Phase 7:** Questrade prototype — port strategy to Canadian broker API
