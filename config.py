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

# OpenD connection
OPEND_HOST = "127.0.0.1"
OPEND_PORT = 11111

# Trading environment: locked to SIMULATE (paper trading only)
# DO NOT change to REAL until strategy is fully validated
TRD_ENV = "SIMULATE"
