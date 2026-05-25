"""
Momentum strategy — buy/sell signal logic.

Buy signal:  current price >= 2hr rolling low * (1 + BUY_THRESHOLD_PCT / 100)
Sell signal: take profit (+3% from entry) OR stop loss (-1.5% from entry)
"""
import logging
from collections import deque
import config

log = logging.getLogger(__name__)

# Rolling price history: {symbol: deque of floats, maxlen=LOOKBACK_BARS}
_price_history: dict[str, deque] = {}


def record_price(symbol: str, price: float):
    """Add the latest price to the rolling window for this symbol."""
    if symbol not in _price_history:
        _price_history[symbol] = deque(maxlen=config.LOOKBACK_BARS)
    _price_history[symbol].append(price)


def check_buy_signal(symbol: str, current_price: float) -> bool:
    """
    Returns True if current price is at least BUY_THRESHOLD_PCT above
    the rolling 2hr low AND we have enough history (>= LOOKBACK_BARS bars).
    """
    history = _price_history.get(symbol)
    if not history or len(history) < config.LOOKBACK_BARS:
        return False  # Not enough data yet

    two_hr_low = min(history)
    threshold_price = two_hr_low * (1 + config.BUY_THRESHOLD_PCT / 100)

    if current_price >= threshold_price:
        log.info(
            "BUY SIGNAL %s | price=%.4f | 2hr_low=%.4f | threshold=%.4f",
            symbol, current_price, two_hr_low, threshold_price,
        )
        return True
    return False


def check_sell_signal(symbol: str, entry_price: float, current_price: float) -> tuple[bool, str]:
    """
    Returns (should_sell, reason).
    Checks take profit and stop loss against entry price.
    """
    pct_change = (current_price - entry_price) / entry_price * 100

    if pct_change >= config.TAKE_PROFIT_PCT:
        log.info(
            "TAKE PROFIT %s | entry=%.4f | current=%.4f | pct=+%.2f%%",
            symbol, entry_price, current_price, pct_change,
        )
        return True, "take_profit"

    if pct_change <= -config.STOP_LOSS_PCT:
        log.info(
            "STOP LOSS %s | entry=%.4f | current=%.4f | pct=%.2f%%",
            symbol, entry_price, current_price, pct_change,
        )
        return True, "stop_loss"

    return False, ""
