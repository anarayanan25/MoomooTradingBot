"""
Market data helpers — quotes and market state via Moomoo SDK.
"""
import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from moomoo import OpenQuoteContext, SubType, KLType, RET_OK
import config

_ET = ZoneInfo("America/New_York")

log = logging.getLogger(__name__)

# US market states that represent regular trading hours
_OPEN_STATES = {"OPEN", "MARKET_OPEN", "MORNING", "AFTERNOON"}

# US market states that are definitely closed (no need to scan)
_CLOSED_STATES = {"AFTER_HOURS_END", "CLOSED", "NONE"}


def get_quotes(symbols: list[str]) -> tuple[dict[str, float], dict[str, float]]:
    """
    Fetch real-time last price and cumulative day volume for each symbol.
    Returns (prices, volumes) — each is {symbol: value}. Symbols that fail are omitted.
    """
    ctx = OpenQuoteContext(host=config.OPEND_HOST, port=config.OPEND_PORT)
    try:
        ret, msg = ctx.subscribe(symbols, [SubType.QUOTE])
        if ret != RET_OK:
            log.error("Subscribe failed: %s", msg)
            return {}, {}

        time.sleep(1)  # Allow subscription to settle before querying
        ret, data = ctx.get_stock_quote(symbols)
        if ret != RET_OK or data is None or len(data) == 0:
            log.error("get_stock_quote failed: %s", data)
            return {}, {}

        prices, volumes = {}, {}
        for _, row in data.iterrows():
            code = row["code"]
            if row["last_price"] not in (None, "", "N/A"):
                prices[code] = float(row["last_price"])
            vol = row.get("volume")
            if vol not in (None, "", "N/A"):
                volumes[code] = float(vol)
        return prices, volumes
    except Exception as e:
        log.error("get_quotes error: %s", e)
        return {}, {}
    finally:
        ctx.close()


def preload_price_history(symbols: list[str]) -> dict[str, dict]:
    """
    Fetch the last LOOKBACK_BARS x 5-min candles for each symbol at startup.
    Returns {symbol: {"prices": [...], "volumes": [...]}} so strategy.py can
    pre-populate rolling histories with real data instead of waiting 2 hours.
    """
    ctx = OpenQuoteContext(host=config.OPEND_HOST, port=config.OPEND_PORT)
    result = {}
    try:
        ret, msg = ctx.subscribe(symbols, [SubType.K_5M])
        if ret != RET_OK:
            log.warning("K_5M subscribe failed: %s — bot will build history live", msg)
            return {}
        time.sleep(1)
        for symbol in symbols:
            ret, data = ctx.get_cur_kline(symbol, config.LOOKBACK_BARS, KLType.K_5M)
            if ret != RET_OK or data is None or len(data) == 0:
                log.warning("Could not preload klines for %s", symbol)
                continue
            closes, bar_volumes = [], []
            for _, row in data.iterrows():
                if row["close"] not in (None, "", "N/A"):
                    closes.append(float(row["close"]))
                vol = row.get("volume")
                if vol not in (None, "", "N/A"):
                    bar_volumes.append(float(vol))
            if closes:
                result[symbol] = {"prices": closes, "volumes": bar_volumes}
        log.info("Preloaded price history for %d/%d symbols (%d bars each)",
                 len(result), len(symbols), config.LOOKBACK_BARS)
    except Exception as e:
        log.warning("preload_price_history error: %s — bot will build history live", e)
    finally:
        ctx.close()
    return result


def is_capital_flowing_in(symbol: str) -> bool:
    """
    Returns True if intraday net capital is flowing INTO the stock (bullish).
    Also checks big money (super+large orders) net inflow if BIG_MONEY_FILTER is enabled.
    Fails open: returns True if any API call fails so it never blocks a trade.
    """
    ctx = OpenQuoteContext(host=config.OPEND_HOST, port=config.OPEND_PORT)
    try:
        # --- Total net inflow check ---
        ret, flow_data = ctx.get_capital_flow(symbol)
        if ret != RET_OK or flow_data is None or len(flow_data) == 0:
            log.warning("get_capital_flow failed for %s — skipping filter", symbol)
            return True
        total_inflow = float(flow_data["in_flow"].sum())
        if total_inflow <= 0:
            log.info("Capital flow %s | net_inflow=%.2f | flowing_in=False", symbol, total_inflow)
            return False

        # --- Big money check (super + large orders) ---
        if config.BIG_MONEY_FILTER:
            ret2, dist_data = ctx.get_capital_distribution(symbol)
            if ret2 == RET_OK and dist_data is not None and len(dist_data) > 0:
                row = dist_data.iloc[0]
                big_in = float(row.get("capital_in_super", 0) or 0) + float(row.get("capital_in_big", 0) or 0)
                big_out = float(row.get("capital_out_super", 0) or 0) + float(row.get("capital_out_big", 0) or 0)
                big_net = big_in - big_out
                if big_net <= 0:
                    log.info(
                        "BIG MONEY FILTER %s | big_net=%.2f — institutional outflow, skipping",
                        symbol, big_net,
                    )
                    return False
                log.info(
                    "Capital signals %s | total_inflow=%.2f | big_net=%.2f | OK",
                    symbol, total_inflow, big_net,
                )
            else:
                log.warning("get_capital_distribution failed for %s — skipping big money check", symbol)

        log.info("Capital flow %s | net_inflow=%.2f | flowing_in=True", symbol, total_inflow)
        return True
    except Exception as e:
        log.warning("is_capital_flowing_in error for %s: %s — skipping filter", symbol, e)
        return True  # Fail open
    finally:
        ctx.close()


def get_active_watchlist(symbols: list[str]) -> list[str]:
    """
    Returns the subset of watchlist symbols that are 'active' today based on
    turnover rate. Called once at market open — dormant stocks are excluded
    from buy signal scanning for the rest of the day.
    Falls back to the full watchlist if the API fails or too few symbols pass.
    """
    ctx = OpenQuoteContext(host=config.OPEND_HOST, port=config.OPEND_PORT)
    try:
        ret, data = ctx.get_market_snapshot(symbols)
        if ret != RET_OK or data is None or len(data) == 0:
            log.warning("get_active_watchlist: snapshot failed — using full watchlist")
            return symbols

        active = []
        for _, row in data.iterrows():
            code = row.get("code")
            turnover_rate = float(row.get("turnover_rate") or 0)
            if code and turnover_rate >= config.MIN_TURNOVER_RATE:
                active.append(code)

        if len(active) < 3:
            log.info("Stock filter: only %d active — falling back to full watchlist", len(active))
            return symbols

        log.info("Stock filter: %d/%d symbols active (turnover >= %.1f%%)",
                 len(active), len(symbols), config.MIN_TURNOVER_RATE)
        return active
    except Exception as e:
        log.warning("get_active_watchlist error: %s — using full watchlist", e)
        return symbols
    finally:
        ctx.close()


def get_day_changes(symbols: list[str]) -> dict[str, float]:
    """
    Fetch today's % change vs previous close for each symbol via market snapshot.
    Used for:
      - Gap filter: skip stocks already up >3% or down >2% (momentum exhausted / stock weak)
      - Earnings proxy: large day changes often indicate earnings/news events
    Fails open — returns {} on any API error so it never blocks trades.
    """
    ctx = OpenQuoteContext(host=config.OPEND_HOST, port=config.OPEND_PORT)
    try:
        ret, data = ctx.get_market_snapshot(symbols)
        if ret != RET_OK or data is None or len(data) == 0:
            log.warning("get_day_changes: snapshot failed — skipping gap filter")
            return {}
        changes = {}
        for _, row in data.iterrows():
            code = row.get("code")
            change_rate = row.get("change_rate")
            if code and change_rate not in (None, "", "N/A"):
                changes[code] = float(change_rate)
        log.info("Day changes fetched for %d symbols", len(changes))
        return changes
    except Exception as e:
        log.warning("get_day_changes error: %s — skipping gap filter", e)
        return {}
    finally:
        ctx.close()


def is_trading_hours() -> bool:
    """
    Returns True if current ET time is within the allowed trading window.
    Avoids the noisy first 30min (9:30–10:00) and last 15min (3:45–4:00).
    """
    now_et = datetime.now(_ET).strftime("%H:%M")
    result = config.TRADING_START_TIME <= now_et <= config.TRADING_END_TIME
    if not result:
        log.info("Outside trading hours (ET: %s) — window is %s to %s",
                 now_et, config.TRADING_START_TIME, config.TRADING_END_TIME)
    return result


def is_market_open() -> bool:
    """
    Returns True if the US market is currently in regular trading hours.
    Uses Moomoo's global state — no manual timezone math needed.
    """
    ctx = OpenQuoteContext(host=config.OPEND_HOST, port=config.OPEND_PORT)
    try:
        ret, state = ctx.get_global_state()
        if ret != RET_OK:
            log.warning("get_global_state failed: %s — assuming market open", state)
            return True
        market_us = str(state.get("market_us", "")).upper()
        is_open = market_us in _OPEN_STATES
        if not is_open:
            log.info("Market state: %s — not in open states %s", market_us, _OPEN_STATES)
        return is_open
    except Exception as e:
        log.warning("is_market_open error: %s — assuming market open", e)
        return True
    finally:
        ctx.close()
