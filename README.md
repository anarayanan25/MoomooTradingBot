# Moomoo Autonomous Trading Bot

An autonomous momentum trading bot for US stocks built on the Moomoo OpenAPI. Runs fully automated paper trades via a Python decision engine, with Claude as a conversational interface — no dashboard needed.

---

## What It Does

- Scans 17 US stocks every 5 minutes during market hours
- Detects momentum buy signals: price +2% above the 2-hour rolling low
- Pre-screens watchlist daily — only scans stocks with active turnover (avoids dormant names)
- Confirms buys with volume surge (1.5x avg) and institutional capital inflow (big money filter)
- Checks broad market regime (SPY uptrend) before any buy — no trading against the market
- Filters overbought entries (RSI > 80) and falling knives (RSI < 40) using existing kline data
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
| Volume filter | Current bar volume >= 1.2x avg bar volume (confirms real momentum) |
| Market regime | SPY must be above its 10-bar rolling avg (tolerance: -0.5%) — no buys in a meaningful market downtrend |
| Sector confirmation | Sector ETF (SMH/QQQ) must be in uptrend (tolerance: -0.5%) before buying individual stock |
| RSI filter | RSI 40–80 only — avoids overbought entries and falling knives |
| Gap filter | Skip if stock already up >3% or down >2% today (also catches earnings events) |
| Sector ETF proxy | SMH for semis (MU, MRVL, NVDA, AVGO, TSM); QQQ for broad tech (AAPL, MSFT, TSLA, etc.) |
| Capital flow filter | Net intraday institutional inflow must be positive (total + big money) |
| Take profit | +3% from entry price |
| Stop loss | -1.5% from entry price |
| Trailing stop | Arms at +1% above entry; trails 1% below highest price reached — locks in partial profit before TP |
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

**Exit priority order:** Take profit (+3%) → Trailing stop (trail 1% below highest, armed at +1%) → Stop loss (-1.5%)

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
| EOD close | Force-sell all positions at 15:30 ET via close_all_positions() | Eliminates overnight gap risk entirely; also runs every loop tick to prevent missing the window |
| Daily history reset | reset_daily_history() clears price + volume history each morning | Prevents stale bars from prior days inflating avg_vol and anchoring 2hr_low to multi-day lows |
| Volume multiplier 1.5x → 1.2x | Lowered Aug 26, 2026 | 1.5x caused 7 consecutive no-trade days in low-volatility tape; 1.2x still filters genuinely thin bars |
| Sector filter tolerance | SECTOR_FILTER_MIN_GAP_PCT = -0.5 | SMH/QQQ trivially below avg (-0.1% to -0.4%) blocked all semi/tech buys for 7+ days; mirrors regime filter fix |
| EOD loop hammering OpenD | Removed is_market_open() from 1s EOD tick — plain time check instead | is_market_open() opens a new OpenD connection every second (~3,600/hr), saturating the connection pool and causing subscribe failures that killed afternoon scanning |
| Avg win < avg loss despite 2:1 RR | Trailing stop added — arms at +1%, trails 1% below highest price | Realized avg win ($27) was below avg loss ($29) because reversals from near-TP gave back gains; trailing stop locks in partial profit before full reversal |
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

## Paper Trading Performance (as of Sep 2, 2026)

| Metric | Value |
|--------|-------|
| Starting capital | $1,000,000 (paper) |
| Realized P&L | **+$193.30** |
| Trading days | 24 (May 21 – Aug 17) |
| Total closed trades | 52 |
| Win rate | 52% (27W / 25L) |
| Avg win | ~+$27 |
| Avg loss | ~-$29 |
| Best day | Jun 16 +$84.09 |
| Worst day | Jun 17 -$51.14 |

> ⚠️ **Gap risk incidents:** AVGO Jun 15 (-$171.40 / -17.9%), SPCX Jun 16–18 (multiple -3% to -8% overnight gaps). Root cause: SpaceX IPO stock included in watchlist. SPCX removed Jun 18. EOD close and SL cooldown added to prevent recurrence. Post-Jun-18 losses are capped at ~-$15/trade.

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
| Stale `avg_vol` blocking volume filter | `reset_daily_history()` clears volume history each morning — prior days' bars were inflating avg_vol |
| Stale 2hr_low spanning multiple days | `reset_daily_history()` clears price history each morning — 24-bar deque was holding weeks of data at 1–3 scans/day |
| Regime filter too aggressive on small SPY dips | `MARKET_REGIME_MIN_GAP_PCT = -0.5` added — only blocks if SPY is >0.5% below avg |
| RSI 70 ceiling blocking entire rallies | `RSI_MAX` raised from 70 → 80 (Jul 9, 2026) |

---

## Roadmap

- **Phase 5 (complete):** Paper trading validation — 2+ weeks of live trade data collected
- **Phase 5b (complete):** launchd auto-restart for reliability
- **Phase 5c (complete):** Signal quality enhancements — volume, capital flow, big money filter, stock filter, real-time monitor
- **Phase 5d (complete):** Risk management fixes — EOD close, SL cooldown, SPCX removed
- **Phase 5e (complete):** Advanced signal filters — market regime, RSI, gap/earnings, sector confirmation
- **Phase 5f (complete):** Data reset & filter tuning — daily history reset, RSI_MAX 70→80, regime filter tolerance, enhanced logging
- **Phase 5g (complete):** Filter tuning round 2 — volume multiplier 1.5x→1.2x, sector filter tolerance (-0.5%), enhanced sector logging
- **Phase 5h (complete):** EOD loop bug fix — removed is_market_open() from 1-second tick (was opening 3,600 OpenD connections/hr)
- **Phase 5i (complete):** Trailing stop — arms at +1% above entry, trails 1% below highest price reached; fixes avg-win < avg-loss problem
- **Phase 6:** AWS EC2 headless deployment (Ubuntu + Command Line OpenD) for 24/7 operation + email alerts via AWS SES. PDT $25K rule eliminated Jun 4, 2026 — confirmed by Moomoo; standard $2,000 margin account sufficient, unlimited day trades.
- **Phase 7:** Questrade prototype — port strategy to Canadian broker API
