# ============================================================
# Trading Bot Configuration
# ============================================================

# Watchlist — all US-listed symbols
WATCHLIST = [
    # Mag 7
    "US.AAPL", "US.MSFT", "US.GOOGL", "US.AMZN", "US.NVDA", "US.META", "US.TSLA",
    # ETFs
    "US.SMH", "US.VOO", "US.QQQ",
    # Others
    "US.TSM", "US.AVGO", "US.BABA", "US.PANW", "US.MU", "US.MRVL", "US.ANET",
]

# Strategy thresholds
BUY_THRESHOLD_PCT  = 2.0   # Buy if current price is +2% above the 2hr rolling low
TAKE_PROFIT_PCT    = 3.0   # Sell if price rises +3% from entry
STOP_LOSS_PCT      = 1.5   # Sell if price falls -1.5% from entry

# How many 5-min scans to look back for the rolling low (24 x 5min = 2 hours)
LOOKBACK_BARS = 24

# Execution
SCAN_INTERVAL_SEC  = 300   # Scan every 5 minutes
MAX_POSITIONS      = 3     # Max concurrent open positions
POSITION_SIZE_USD  = 1000  # Approx USD value per trade

# Time-of-day filter (US Eastern Time)
TRADING_START_TIME = "10:00"   # Avoid first 30min of market open (9:30–10:00)
TRADING_END_TIME   = "15:45"   # Avoid last 15min before close (3:45–4:00)

# Circuit breaker — max daily realized loss before bot stops trading for the day
MAX_DAILY_LOSS_USD = 150.0     # ~3 max stop-loss hits on $1,000 positions

# Volume confirmation — current bar must exceed this multiple of the avg bar volume
VOLUME_MULTIPLIER = 1.5        # e.g. 1.5x avg = above-average activity required

# Capital flow filter — only buy if intraday net capital is flowing into the stock
CAPITAL_FLOW_FILTER = True

# Big money filter — also require super+large order net inflow to be positive
BIG_MONEY_FILTER = True        # Filters out retail-driven moves with no institutional backing

# Stock filter — pre-screen watchlist at market open, only scan active symbols for buys
STOCK_FILTER_ENABLED = True
MIN_TURNOVER_RATE = 0.3        # Minimum daily turnover rate % to be considered active

# Stop loss cooldown — prevent re-entering a symbol for this long after a stop loss
STOP_LOSS_COOLDOWN_SEC = 1800  # 30 minutes

# End-of-day close — force-close all open positions before overnight gap risk
EOD_CLOSE_ENABLED = True
EOD_CLOSE_TIME = "15:30"       # Close positions at 3:30pm ET (15min before trading window ends)

# Market regime filter — only buy when the broad market (SPY) is in an uptrend
MARKET_REGIME_FILTER = True
MARKET_REGIME_SYMBOL = "US.SPY"  # Tracked separately from watchlist
MARKET_REGIME_MIN_GAP_PCT = -0.5  # Only block if SPY is more than 0.5% below its rolling avg (blocks <0.5% noise)

# RSI filter — avoid overbought entries and falling-knife entries
RSI_FILTER = True
RSI_PERIOD = 14      # Standard RSI lookback (uses existing 5-min kline data — no extra API calls)
RSI_MIN    = 40      # Below this = falling knife, skip
RSI_MAX    = 80      # Above this = overbought, skip (raised from 70 → 80 Jul 9: RSI 70 blocked entire rally)

# Gap filter — skip stocks that have already moved too far today
# Also serves as earnings proxy: earnings gaps show up as large day changes
GAP_FILTER = True
GAP_MAX_UP_PCT   = 3.0   # Already up >3% today → momentum likely exhausted
GAP_MAX_DOWN_PCT = 2.0   # Already down >2% today → stock is weak, don't buy

# Sector confirmation — require the stock's sector ETF to also be in an uptrend
SECTOR_FILTER = True
SECTOR_PROXIES = {
    # Semiconductors → SMH (already on watchlist)
    "US.NVDA": "US.SMH", "US.MU": "US.SMH", "US.AVGO": "US.SMH",
    "US.MRVL": "US.SMH", "US.TSM": "US.SMH",
    # Broad tech → QQQ (already on watchlist)
    "US.AAPL": "US.QQQ", "US.MSFT": "US.QQQ", "US.GOOGL": "US.QQQ",
    "US.AMZN": "US.QQQ", "US.META": "US.QQQ", "US.TSLA": "US.QQQ",
    "US.PANW": "US.QQQ", "US.ANET": "US.QQQ", "US.BABA": "US.QQQ",
    # ETFs are their own sector — no proxy check needed
    "US.SMH": None, "US.VOO": None, "US.QQQ": None,
}

# OpenD connection
OPEND_HOST = "127.0.0.1"
OPEND_PORT = 11111

# Trading environment: locked to SIMULATE (paper trading only)
# DO NOT change to REAL until strategy is fully validated
TRD_ENV = "SIMULATE"
