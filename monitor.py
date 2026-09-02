"""
Real-time position monitor — subscribes to QUOTE pushes for open positions.

Checks take profit and stop loss on every price tick instead of every 5 minutes.
Runs alongside the main scan loop (which continues to handle buy signals).

Thread safety: uses risk.mark_selling() to prevent double-sells with the main loop.
"""
import logging
import threading
from moomoo import OpenQuoteContext, StockQuoteHandlerBase, SubType, RET_OK, RET_ERROR
import config
import strategy
import executor
import risk

log = logging.getLogger(__name__)


class _QuoteHandler(StockQuoteHandlerBase):
    """Callback handler for real-time quote pushes."""

    def on_recv_rsp(self, rsp_pb):
        ret, data = super().on_recv_rsp(rsp_pb)
        if ret != RET_OK:
            return RET_ERROR, data

        try:
            for _, row in data.iterrows():
                symbol = row.get("code")
                raw_price = row.get("last_price")
                if not symbol or raw_price in (None, "", "N/A"):
                    continue
                try:
                    price = float(raw_price)
                except (ValueError, TypeError):
                    continue
                if price <= 0:
                    continue

                position = risk.get_position(symbol)
                if not position:
                    continue

                risk.update_highest_price(symbol, price)
                should_sell, reason = strategy.check_sell_signal(
                    symbol, position["entry_price"], price, position.get("highest_price")
                )
                if not should_sell:
                    continue

                # Atomically claim the sell to prevent race with main scan loop
                if not risk.mark_selling(symbol):
                    continue  # Main loop already claimed this sell

                try:
                    order_id = executor.place_sell(symbol, position["quantity"], price, reason)
                    if order_id:
                        pnl_pct = (price - position["entry_price"]) / position["entry_price"] * 100
                        risk.record_trade_pnl(position["entry_price"], price, position["quantity"])
                        log.info(
                            "REALTIME CLOSED %s | reason=%s | entry=%.4f | exit=%.4f | pnl=%.2f%% | daily_pnl=$%.2f",
                            symbol, reason, position["entry_price"], price, pnl_pct, risk.daily_pnl(),
                        )
                        risk.remove_position(symbol)
                        if reason == "stop_loss":
                            risk.record_stop_loss(symbol)
                finally:
                    risk.unmark_selling(symbol)

        except Exception as e:
            log.error("Monitor handler error: %s", e, exc_info=True)

        return RET_OK, data


class PositionMonitor:
    """
    Manages a persistent OpenQuoteContext with real-time QUOTE push subscriptions
    for all currently open positions.
    """

    def __init__(self):
        self._ctx = None
        self._handler = _QuoteHandler()
        self._subscribed: set[str] = set()
        self._lock = threading.Lock()

    def start(self):
        """Open the quote context and attach the handler."""
        try:
            self._ctx = OpenQuoteContext(host=config.OPEND_HOST, port=config.OPEND_PORT)
            self._ctx.set_handler(self._handler)
            log.info("Real-time position monitor started")
        except Exception as e:
            log.error("Failed to start position monitor: %s", e)
            self._ctx = None

    def stop(self):
        """Close the quote context and clean up."""
        if self._ctx:
            try:
                self._ctx.close()
            except Exception:
                pass
            self._ctx = None
        with self._lock:
            self._subscribed.clear()
        log.info("Real-time position monitor stopped")

    def on_position_opened(self, symbol: str):
        """Subscribe to real-time quotes when a new position is opened."""
        if not self._ctx:
            return
        with self._lock:
            if symbol in self._subscribed:
                return
        try:
            ret, msg = self._ctx.subscribe([symbol], [SubType.QUOTE], subscribe_push=True)
            if ret == RET_OK:
                with self._lock:
                    self._subscribed.add(symbol)
                log.info("Monitor: subscribed real-time quotes for %s", symbol)
            else:
                log.warning("Monitor: subscribe failed for %s: %s", symbol, msg)
        except Exception as e:
            log.warning("Monitor: subscribe error for %s: %s", symbol, e)

    def on_position_closed(self, symbol: str):
        """Unsubscribe from real-time quotes when a position is closed."""
        if not self._ctx:
            return
        with self._lock:
            if symbol not in self._subscribed:
                return
        try:
            ret, msg = self._ctx.unsubscribe([symbol], [SubType.QUOTE])
            if ret == RET_OK:
                with self._lock:
                    self._subscribed.discard(symbol)
                log.info("Monitor: unsubscribed from %s", symbol)
        except Exception as e:
            log.warning("Monitor: unsubscribe error for %s: %s", symbol, e)

    def sync(self, open_symbols: set[str]):
        """
        Sync subscriptions to match the current set of open positions.
        Called at startup to re-subscribe positions that survived a restart.
        """
        with self._lock:
            current = set(self._subscribed)
        for s in open_symbols - current:
            self.on_position_opened(s)
        for s in current - open_symbols:
            self.on_position_closed(s)


# Module-level singleton — imported and used by main.py
_monitor = PositionMonitor()


def start():
    _monitor.start()


def stop():
    _monitor.stop()


def on_position_opened(symbol: str):
    _monitor.on_position_opened(symbol)


def on_position_closed(symbol: str):
    _monitor.on_position_closed(symbol)


def sync(open_symbols: set[str]):
    _monitor.sync(open_symbols)
