"""
Momentum strategy — buy/sell signal logic.

Buy signal:  current price >= 2hr rolling low * (1 + BUY_THRESHOLD_PCT / 100)
             AND current bar volume >= VOLUME_MULTIPLIER * avg bar volume
Sell signal: take profit (+3% from entry) OR stop loss (-1.5% from entry)
"""
import logging
from collections import deque
import config

log = logging.getLogger(__name__)

# Rolling price history: {symbol: deque of floats, maxlen=LOOKBACK_BARS}
_price_history: dict[str, deque] = {}

# Rolling per-bar volume history (deltas from cumulative day volume each scan)
_volume_history: dict[str, deque] = {}
_last_cumulative_volume: dict[str, float] = {}


def record_price(symbol: str, price: float):
    """Add the latest price to the rolling window for this symbol."""
    if symbol not in _price_history:
        _price_history[symbol] = deque(maxlen=config.LOOKBACK_BARS)
    _price_history[symbol].append(price)


def preload_volume_history(symbol: str, bar_volumes: list[float]):
    """Seed volume history from historical kline bar volumes at startup."""
    if symbol not in _volume_history:
        _volume_history[symbol] = deque(maxlen=config.LOOKBACK_BARS)
    for v in bar_volumes:
        _volume_history[symbol].append(v)


def record_volume(symbol: str, cumulative_volume: float):
    """
    Record the per-bar volume delta from today's cumulative day volume.
    Called each scan. Computes delta from previous cumulative value so we
    track how much volume traded in each 5-min bar.
    """
    if symbol not in _volume_history:
        _volume_history[symbol] = deque(maxlen=config.LOOKBACK_BARS)

    prev = _last_cumulative_volume.get(symbol)
    _last_cumulative_volume[symbol] = cumulative_volume

    if prev is None or cumulative_volume <= prev:
        return  # First scan or day reset — no delta yet

    _volume_history[symbol].append(cumulative_volume - prev)


def get_rsi(symbol: str) -> float | None:
    """
    Compute RSI from the rolling 5-min price history.
    Uses existing kline data — no extra API calls.
    Returns None if insufficient history (fails open).
    """
    prices = list(_price_history.get(symbol, []))
    period = config.RSI_PERIOD
    if len(prices) < period + 1:
        return None
    prices = prices[-(period + 1):]
    gains, losses = [], []
    for i in range(1, len(prices)):
        delta = prices[i] - prices[i - 1]
        gains.append(max(delta, 0))
        losses.append(max(-delta, 0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def is_above_rolling_avg(symbol: str, period: int = 10) -> bool:
    """
    Returns True if the symbol's latest price is above its N-bar rolling average.
    Used for market regime check (SPY) and sector confirmation (SMH, QQQ).
    Fails open — returns True if insufficient data so it never blocks when uninitialized.
    """
    prices = list(_price_history.get(symbol, []))
    if len(prices) < period:
        return True  # Not enough data yet — don't block trades
    avg = sum(prices[-period:]) / period
    return prices[-1] > avg


def check_buy_signal(symbol: str, current_price: float) -> bool:
    """
    Returns True if:
      1. Current price is at least BUY_THRESHOLD_PCT above the 2hr rolling low
      2. Current bar volume is at least VOLUME_MULTIPLIER * avg bar volume
    Both conditions must pass.
    """
    history = _price_history.get(symbol)
    if not history or len(history) < config.LOOKBACK_BARS:
        return False  # Not enough price history yet

    two_hr_low = min(history)
    threshold_price = two_hr_low * (1 + config.BUY_THRESHOLD_PCT / 100)

    if current_price < threshold_price:
        return False

    # Volume confirmation — only apply when we have enough bars to avg
    vol_history = _volume_history.get(symbol)
    if vol_history and len(vol_history) >= 3:
        avg_volume = sum(vol_history) / len(vol_history)
        latest_volume = vol_history[-1]
        if avg_volume > 0 and latest_volume < config.VOLUME_MULTIPLIER * avg_volume:
            log.info(
                "VOLUME FILTER %s | bar_vol=%.0f | avg_vol=%.0f | required=%.1fx — skipped",
                symbol, latest_volume, avg_volume, config.VOLUME_MULTIPLIER,
            )
            return False

    log.info(
        "BUY SIGNAL %s | price=%.4f | 2hr_low=%.4f | threshold=%.4f",
        symbol, current_price, two_hr_low, threshold_price,
    )
    return True


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
