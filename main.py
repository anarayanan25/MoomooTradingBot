"""
Moomoo Autonomous Trading Bot — Main Loop

Runs every SCAN_INTERVAL_SEC seconds during US market hours.
Strategy: momentum — buy on +2% from 2hr rolling low, sell at +3% (TP) or -1.5% (SL).
Trading environment: controlled by config.TRD_ENV (default: SIMULATE / paper trading).

Usage:
    python3 main.py

Stop:
    Ctrl+C
"""
import logging
import os
import time
import signal
import sys
from datetime import datetime

import config
import market_data
import strategy
import risk
import executor

# ============================================================
# Logging setup
# ============================================================

LOG_FILE = os.path.join(os.path.dirname(__file__), "logs", "bot.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

# ============================================================
# Graceful shutdown
# ============================================================

_running = True

def _shutdown(sig, frame):
    global _running
    log.info("Shutdown signal received — stopping bot.")
    _running = False

signal.signal(signal.SIGINT, _shutdown)
signal.signal(signal.SIGTERM, _shutdown)

# ============================================================
# Core scan loop
# ============================================================

def scan():
    """One full scan cycle: fetch quotes, check signals, execute orders."""
    log.info("--- Scan started | positions=%d/%d ---",
             risk.position_count(), config.MAX_POSITIONS)

    quotes = market_data.get_quotes(config.WATCHLIST)
    if not quotes:
        log.warning("No quotes returned — skipping scan.")
        return

    log.info("Quotes received: %d symbols | sample: %s",
             len(quotes),
             ", ".join(f"{s.split('.')[1]}=${p:.2f}" for s, p in list(quotes.items())[:5]))

    for symbol in config.WATCHLIST:
        price = quotes.get(symbol)
        if price is None or price <= 0:
            continue

        # Always record price for rolling history
        strategy.record_price(symbol, price)

        # --- Check existing position: take profit or stop loss ---
        position = risk.get_position(symbol)
        if position:
            should_sell, reason = strategy.check_sell_signal(
                symbol, position["entry_price"], price
            )
            if should_sell:
                order_id = executor.place_sell(symbol, position["quantity"], price, reason)
                if order_id:
                    pnl_pct = (price - position["entry_price"]) / position["entry_price"] * 100
                    risk.record_trade_pnl(position["entry_price"], price, position["quantity"])
                    log.info(
                        "CLOSED %s | reason=%s | entry=%.4f | exit=%.4f | pnl=%.2f%% | daily_pnl=$%.2f",
                        symbol, reason, position["entry_price"], price, pnl_pct, risk.daily_pnl(),
                    )
                    risk.remove_position(symbol)
            continue  # Don't also check buy signal for held stocks

        # --- Check buy signal for unwatched symbols ---
        if (not risk.is_circuit_breaker_triggered()
                and risk.can_buy(symbol)
                and strategy.check_buy_signal(symbol, price)):
            quantity = risk.calc_quantity(price)
            risk.add_pending(symbol)  # Reserve slot immediately to prevent race condition
            order_id = executor.place_buy(symbol, quantity, price)
            if order_id:
                risk.add_position(symbol, price, quantity, order_id)
            risk.remove_pending(symbol)  # Release reservation once position is recorded

    log.info("--- Scan complete | positions=%d/%d ---",
             risk.position_count(), config.MAX_POSITIONS)


# ============================================================
# Main entry point
# ============================================================

def main():
    log.info("=" * 60)
    log.info("Moomoo Trading Bot starting")
    log.info("Environment : %s", config.TRD_ENV)
    log.info("Watchlist   : %d symbols", len(config.WATCHLIST))
    log.info("Buy signal  : +%.1f%% from 2hr rolling low", config.BUY_THRESHOLD_PCT)
    log.info("Take profit : +%.1f%% from entry", config.TAKE_PROFIT_PCT)
    log.info("Stop loss   : -%.1f%% from entry", config.STOP_LOSS_PCT)
    log.info("Scan every  : %ds", config.SCAN_INTERVAL_SEC)
    log.info("Max positions: %d", config.MAX_POSITIONS)
    log.info("=" * 60)

    risk.load()

    _last_scan_time = 0.0  # monotonic timestamp of last completed scan

    # Pre-populate rolling price history from historical 5-min candles
    # so buy signals can fire from the first scan instead of after 2 hours
    log.info("Pre-loading 2hr price history from historical candles...")
    history = market_data.preload_price_history(config.WATCHLIST)
    for symbol, prices in history.items():
        for price in prices:
            strategy.record_price(symbol, price)
    log.info("Price history ready for %d symbols", len(history))

    while _running:
        # Time-based throttle — never scan more often than SCAN_INTERVAL_SEC regardless of
        # market state flickering or any other loop restarts
        now = time.monotonic()
        if now - _last_scan_time < config.SCAN_INTERVAL_SEC:
            time.sleep(1)
            continue

        if not market_data.is_market_open():
            log.info("US market is closed — waiting %ds before next check.", config.SCAN_INTERVAL_SEC)
            _last_scan_time = time.monotonic()  # Reset timer so we recheck after full interval
            continue

        if not market_data.is_trading_hours():
            log.info("Outside trading window — waiting %ds.", config.SCAN_INTERVAL_SEC)
            _last_scan_time = time.monotonic()
            continue

        try:
            scan()
        except Exception as e:
            log.error("Unhandled error in scan: %s", e, exc_info=True)

        _last_scan_time = time.monotonic()

    log.info("Bot stopped.")


if __name__ == "__main__":
    main()
