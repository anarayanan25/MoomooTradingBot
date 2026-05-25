"""
Position tracker — persists open positions to disk so the bot survives restarts.
Includes daily P&L circuit breaker.
"""
import json
import logging
import os
from datetime import date
import config

log = logging.getLogger(__name__)

_POSITIONS_FILE = os.path.join(os.path.dirname(__file__), "logs", "positions.json")

# In-memory positions: {symbol: {"entry_price": float, "quantity": int, "order_id": str}}
_positions: dict = {}

# Pending buys — symbols reserved the moment a buy decision is made, before order confirmation
_pending_buys: set = set()

# Circuit breaker — daily realized P&L tracking
_daily_pnl_usd: float = 0.0
_circuit_breaker_date: date = None  # Date the circuit breaker was last reset


def load():
    """Load persisted positions from disk on startup."""
    global _positions
    if os.path.exists(_POSITIONS_FILE):
        try:
            with open(_POSITIONS_FILE, "r") as f:
                _positions = json.load(f)
            log.info("Loaded %d open positions from disk", len(_positions))
        except Exception as e:
            log.warning("Could not load positions file: %s", e)
            _positions = {}
    else:
        _positions = {}


def _save():
    """Persist positions to disk."""
    try:
        with open(_POSITIONS_FILE, "w") as f:
            json.dump(_positions, f, indent=2)
    except Exception as e:
        log.error("Could not save positions file: %s", e)


def can_buy(symbol: str) -> bool:
    """Returns True if we're allowed to open a new position."""
    if symbol in _positions:
        return False  # Already holding this symbol
    if symbol in _pending_buys:
        return False  # Buy already in flight for this symbol
    if len(_positions) + len(_pending_buys) >= config.MAX_POSITIONS:
        log.info("Max positions (%d) reached — skipping %s", config.MAX_POSITIONS, symbol)
        return False
    return True


def add_pending(symbol: str):
    """Reserve a symbol immediately when a buy decision is made (before order placement)."""
    _pending_buys.add(symbol)


def remove_pending(symbol: str):
    """Release the pending reservation (call after order confirmed or failed)."""
    _pending_buys.discard(symbol)


def add_position(symbol: str, entry_price: float, quantity: int, order_id: str):
    """Record a newly opened position."""
    _positions[symbol] = {
        "entry_price": entry_price,
        "quantity": quantity,
        "order_id": order_id,
    }
    _save()
    log.info("Position opened: %s x%d @ %.4f (order %s)", symbol, quantity, entry_price, order_id)


def remove_position(symbol: str):
    """Remove a closed position."""
    if symbol in _positions:
        del _positions[symbol]
        _save()
        log.info("Position closed: %s", symbol)


def get_position(symbol: str) -> dict | None:
    """Return position dict or None."""
    return _positions.get(symbol)


def open_symbols() -> list[str]:
    """Return list of symbols with open positions."""
    return list(_positions.keys())


def position_count() -> int:
    return len(_positions)


def calc_quantity(current_price: float) -> int:
    """Calculate share quantity to buy based on POSITION_SIZE_USD."""
    qty = max(1, int(config.POSITION_SIZE_USD / current_price))
    return qty


# ============================================================
# Circuit breaker
# ============================================================

def record_trade_pnl(entry_price: float, exit_price: float, quantity: int):
    """Record realized P&L from a closed trade. Resets daily at midnight."""
    global _daily_pnl_usd, _circuit_breaker_date
    today = date.today()
    if _circuit_breaker_date != today:
        _daily_pnl_usd = 0.0
        _circuit_breaker_date = today
        log.info("Circuit breaker reset for new trading day (%s)", today)
    pnl = (exit_price - entry_price) * quantity
    _daily_pnl_usd += pnl
    log.info("Daily P&L updated: $%.2f (limit: -$%.2f)", _daily_pnl_usd, config.MAX_DAILY_LOSS_USD)


def is_circuit_breaker_triggered() -> bool:
    """Returns True if daily losses have hit the max limit — stop all new buys."""
    global _daily_pnl_usd, _circuit_breaker_date
    today = date.today()
    if _circuit_breaker_date != today:
        _daily_pnl_usd = 0.0
        _circuit_breaker_date = today
    if _daily_pnl_usd <= -config.MAX_DAILY_LOSS_USD:
        log.warning(
            "CIRCUIT BREAKER TRIGGERED — daily loss $%.2f exceeds limit -$%.2f. No new buys today.",
            _daily_pnl_usd, config.MAX_DAILY_LOSS_USD,
        )
        return True
    return False


def daily_pnl() -> float:
    """Return today's realized P&L in USD."""
    return _daily_pnl_usd
