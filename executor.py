"""
Order executor — places buy/sell market orders via Moomoo SDK.
Always uses TRD_ENV from config (default: SIMULATE).
"""
import logging
from moomoo import OpenSecTradeContext, TrdEnv, TrdSide, OrderType, TrdMarket, RET_OK
import config

log = logging.getLogger(__name__)

# Hard-locked to paper trading — never touches real money
_TRD_ENV = TrdEnv.SIMULATE


def _get_trade_ctx():
    return OpenSecTradeContext(
        host=config.OPEND_HOST,
        port=config.OPEND_PORT,
        filter_trdmarket=TrdMarket.US,
    )


def place_buy(symbol: str, quantity: int, current_price: float) -> str | None:
    """
    Place a market buy order.
    Returns order_id on success, None on failure.
    """
    ctx = _get_trade_ctx()
    try:
        ret, data = ctx.place_order(
            price=0.0,
            qty=quantity,
            code=symbol,
            trd_side=TrdSide.BUY,
            order_type=OrderType.MARKET,
            trd_env=_TRD_ENV,
        )
        if ret != RET_OK:
            log.error("BUY order failed for %s: %s", symbol, data)
            return None

        order_id = str(data.iloc[0]["order_id"])
        log.info("BUY order placed: %s x%d @ ~%.4f | order_id=%s | env=%s",
                 symbol, quantity, current_price, order_id, config.TRD_ENV)
        return order_id
    except Exception as e:
        log.error("place_buy exception for %s: %s", symbol, e)
        return None
    finally:
        ctx.close()


def place_sell(symbol: str, quantity: int, current_price: float, reason: str = "") -> str | None:
    """
    Place a market sell order.
    Returns order_id on success, None on failure.
    """
    ctx = _get_trade_ctx()
    try:
        ret, data = ctx.place_order(
            price=0.0,
            qty=quantity,
            code=symbol,
            trd_side=TrdSide.SELL,
            order_type=OrderType.MARKET,
            trd_env=_TRD_ENV,
        )
        if ret != RET_OK:
            log.error("SELL order failed for %s: %s", symbol, data)
            return None

        order_id = str(data.iloc[0]["order_id"])
        log.info("SELL order placed: %s x%d @ ~%.4f | order_id=%s | reason=%s | env=%s",
                 symbol, quantity, current_price, order_id, reason, config.TRD_ENV)
        return order_id
    except Exception as e:
        log.error("place_sell exception for %s: %s", symbol, e)
        return None
    finally:
        ctx.close()
