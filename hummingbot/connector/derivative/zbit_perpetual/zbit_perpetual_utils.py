from typing import Any, Dict, List, Optional, Tuple

from bidict import bidict

from hummingbot.connector.trading_rule import TradingRule
from hummingbot.connector.utils import combine_to_hb_trading_pair
from hummingbot.core.data_type.in_flight_order import OrderState
from hummingbot.core.data_type.common import OrderType, PositionAction, TradeType

from hummingbot.connector.derivative.zbit_perpetual.zbit_perpetual_constants import ORDER_STATE


def is_exchange_information_valid(exchange_info: Dict[str, Any]) -> bool:
    """
    验证交易所信息是否有效
    :param exchange_info: 交易所信息字典
    :return: 如果信息有效则返回True，否则返回False
    """
    return all(key in exchange_info for key in ["symbol", "status", "baseAsset", "quoteAsset"])


def build_trading_rule(exchange_info: Dict[str, Any]) -> Optional[TradingRule]:
    """
    根据交易所信息构建交易规则
    :param exchange_info: 交易所信息字典
    :return: 构建的交易规则，如果无法构建则返回None
    """
    try:
        if not is_exchange_information_valid(exchange_info):
            return None

        # 提取交易对信息
        trading_pair = combine_to_hb_trading_pair(
            base=exchange_info["baseAsset"],
            quote=exchange_info["quoteAsset"],
        )

        # 提取规则参数
        min_price = float(exchange_info.get("priceFilter", {}).get("minPrice", "0"))
        min_quantity = float(exchange_info.get("lotSizeFilter", {}).get("minQty", "0"))
        step_size = float(exchange_info.get("lotSizeFilter", {}).get("stepSize", "0"))
        min_notional = float(exchange_info.get("minNotional", "0"))
        
        # 构建并返回交易规则
        return TradingRule(
            trading_pair=trading_pair,
            min_order_size=min_quantity,
            min_price_increment=min_price,
            min_base_amount_increment=step_size,
            min_notional_size=min_notional,
            buy_order_collateral_token=exchange_info["quoteAsset"],  # 抵押代币通常是报价货币
            sell_order_collateral_token=exchange_info["quoteAsset"],
        )
    except Exception:
        return None


def convert_to_order_state(status: str) -> OrderState:
    """
    将交易所订单状态转换为Hummingbot订单状态
    :param status: 交易所订单状态
    :return: Hummingbot订单状态
    """
    return ORDER_STATE.get(status, OrderState.OPEN)


def map_order_type(order_type: OrderType) -> str:
    """
    将Hummingbot订单类型映射到交易所订单类型
    :param order_type: Hummingbot订单类型
    :return: 交易所订单类型
    """
    order_type_map = {
        OrderType.LIMIT: "LIMIT",
        OrderType.MARKET: "MARKET",
        OrderType.LIMIT_MAKER: "LIMIT_MAKER",
    }
    return order_type_map.get(order_type, "LIMIT")


def map_order_side(trade_type: TradeType, position_action: PositionAction) -> str:
    """
    将Hummingbot交易类型和位置动作映射到交易所订单方向
    :param trade_type: 交易类型 (买/卖)
    :param position_action: 位置动作 (开仓/平仓)
    :return: 交易所订单方向
    """
    # 映射 (位置动作, 交易类型) 到交易所订单方向
    side_map = bidict({
        (PositionAction.OPEN, TradeType.BUY): "BUY_OPEN",    # 买入开多
        (PositionAction.CLOSE, TradeType.SELL): "SELL_CLOSE", # 卖出平多
        (PositionAction.OPEN, TradeType.SELL): "SELL_OPEN",   # 卖出开空
        (PositionAction.CLOSE, TradeType.BUY): "BUY_CLOSE",   # 买入平空
    })
    
    return side_map.get((position_action, trade_type), "BUY_OPEN")  # 默认买入开多


def get_pair_from_exchange_symbol(symbol: str) -> Tuple[str, str]:
    """
    从交易所交易对符号中获取基础和报价资产
    :param symbol: 交易所交易对符号 (例如 'BTCUSDT')
    :return: 基础和报价资产的元组 (例如 ('BTC', 'USDT'))
    """
    # 对于像BTCUSDT这样的交易对，我们需要确定分割点
    known_quote_assets = ['USDT', 'BUSD', 'USDC', 'BTC', 'ETH']
    for quote in known_quote_assets:
        if symbol.endswith(quote):
            base = symbol[:-len(quote)]
            return base, quote
    
    # 如果无法确定分割点，则返回原始符号作为基础资产，空字符串作为报价资产
    return symbol, "" 