#!/usr/bin/env python

import logging
import time
from decimal import Decimal
from typing import Dict, List, Tuple, Optional, Any, Union

import pandas as pd

from hummingbot.client.settings import AllConnectorSettings
from hummingbot.connector.exchange.zbit.zbit_exchange import ZbitExchange
from hummingbot.connector.derivative.position import Position
from hummingbot.core.clock import Clock
from hummingbot.core.data_type.common import OrderType, PositionAction, PositionMode, PositionSide, TradeType
from hummingbot.core.data_type.limit_order import LimitOrder
from hummingbot.core.data_type.order_candidate import OrderCandidate, PerpetualOrderCandidate
from hummingbot.core.network_iterator import NetworkStatus
from hummingbot.strategy.hedge.hedge import HedgeStrategy
from hummingbot.strategy.hedge.hedge_config_map_pydantic import HedgeConfigMap
from hummingbot.strategy.market_trading_pair_tuple import MarketTradingPairTuple


class ZbitHedgeStrategy(HedgeStrategy):
    """
    ZBit对冲策略

    该策略继承自Hummingbot的HedgeStrategy类，用于在ZBit交易所
    实现基于价值或基于数量的资产对冲。策略可以监控多个交易所
    的资产头寸，并在ZBit上执行相应的对冲操作。
    """

    # 策略日志记录器
    _logger = None

    @classmethod
    def logger(cls):
        if cls._logger is None:
            cls._logger = logging.getLogger(__name__)
        return cls._logger

    def __init__(
        self,
        config_map: HedgeConfigMap,
        hedge_market_pairs: List[MarketTradingPairTuple],
        market_pairs: List[MarketTradingPairTuple],
        offsets: Dict[MarketTradingPairTuple, Decimal],
        status_report_interval: float = 900,
        max_order_age: float = 5,
        enable_auto_set_position_mode: bool = True,
        hedge_ratio_adjustment: Decimal = Decimal("0.0"),  # ZBit特有参数：对冲比率调整
        zbit_specific_slippage: Optional[Dict[str, Decimal]] = None,  # ZBit特有参数：特定交易对的滑点设置
    ):
        """
        初始化ZBit对冲策略
        
        :param config_map: 策略配置映射
        :param hedge_market_pairs: 要对冲的市场交易对列表
        :param market_pairs: 要监控的市场交易对列表
        :param offsets: 市场交易对偏移量字典
        :param status_report_interval: 状态报告间隔（秒）
        :param max_order_age: 订单最大有效时间（秒）
        :param enable_auto_set_position_mode: 是否自动设置持仓模式
        :param hedge_ratio_adjustment: ZBit特有的对冲比率调整值
        :param zbit_specific_slippage: ZBit特有的滑点设置，按交易对区分
        """
        super().__init__(
            config_map=config_map,
            hedge_market_pairs=hedge_market_pairs,
            market_pairs=market_pairs,
            offsets=offsets,
            status_report_interval=status_report_interval,
            max_order_age=max_order_age,
            enable_auto_set_position_mode=enable_auto_set_position_mode,
        )
        
        # ZBit特有的参数
        self._hedge_ratio_adjustment = hedge_ratio_adjustment
        self._zbit_specific_slippage = zbit_specific_slippage or {}
        self._zbit_market = None
        self._last_zbit_sync_timestamp = 0
        self._zbit_sync_interval = 60  # 每60秒与ZBit同步一次
        
        # 设置ZBit市场
        for market_pair in hedge_market_pairs:
            if isinstance(market_pair.market, ZbitExchange):
                self._zbit_market = market_pair.market
                break
        
        # 如果没有找到ZBit市场，记录警告
        if self._zbit_market is None:
            self.logger().warning("没有找到ZBit市场！请确保hedge_connector设置为'zbit'")

    def tick(self, timestamp: float) -> None:
        """
        策略的主要循环函数，每个时钟周期执行一次
        
        :param timestamp: 当前时间戳
        """
        # 首先执行父类的tick方法
        super().tick(timestamp)
        
        # ZBit特有的逻辑：周期性与ZBit同步
        if (timestamp - self._last_zbit_sync_timestamp) > self._zbit_sync_interval:
            self._last_zbit_sync_timestamp = timestamp
            self._sync_with_zbit()

    def _sync_with_zbit(self) -> None:
        """
        与ZBit交易所同步，执行特定于ZBit的操作
        """
        if self._zbit_market is None:
            return
        
        try:
            # 检查ZBit市场的连接状态
            if self._zbit_market.network_status is not NetworkStatus.CONNECTED:
                self.logger().warning("ZBit市场未连接，无法同步")
                return
            
            # 这里可以添加ZBit特有的同步逻辑
            # 例如：更新对冲比率、检查特定条件等
            self.logger().info("与ZBit同步完成")
            
        except Exception as e:
            self.logger().error(f"与ZBit同步时出错: {str(e)}", exc_info=True)

    def get_hedge_direction_and_value(self) -> Tuple[bool, Decimal]:
        """
        重写计算对冲方向和对冲值的方法，添加ZBit特有的调整逻辑
        
        :return: 元组(is_buy, value_to_hedge)，其中is_buy是布尔值表示是否买入，
                value_to_hedge是要对冲的数量
        """
        # 先调用父类的方法获取基本的对冲方向和数量
        is_buy, value_to_hedge = super().get_hedge_direction_and_value()
        
        # 应用ZBit特有的对冲比率调整
        adjusted_value = value_to_hedge * (Decimal("1.0") + self._hedge_ratio_adjustment)
        
        # 记录调整信息
        if self._hedge_ratio_adjustment != Decimal("0.0"):
            self.logger().info(
                f"应用ZBit对冲比率调整: {self._hedge_ratio_adjustment}. "
                f"原始对冲值: {value_to_hedge}, 调整后: {adjusted_value}"
            )
        
        return is_buy, adjusted_value

    def get_slippage_ratio(self, is_buy: bool) -> Decimal:
        """
        重写获取滑点比率的方法，为ZBit添加特定交易对的滑点设置
        
        :param is_buy: 是否为买入操作
        :return: 滑点比率
        """
        # 为特定交易对设置特殊滑点
        if self._hedge_market_pairs and len(self._hedge_market_pairs) > 0:
            trading_pair = self._hedge_market_pairs[0].trading_pair
            if trading_pair in self._zbit_specific_slippage:
                specific_slippage = self._zbit_specific_slippage[trading_pair]
                self.logger().info(f"使用ZBit {trading_pair}特定滑点设置: {specific_slippage}")
                return specific_slippage
        
        # 如果没有特定设置，则使用父类的滑点设置
        return super().get_slippage_ratio(is_buy)

    def place_orders(
        self, market_pair: MarketTradingPairTuple, 
        orders: Union[List[OrderCandidate], List[PerpetualOrderCandidate]]
    ) -> None:
        """
        重写下单方法，为ZBit添加特殊处理
        
        :param market_pair: 市场交易对
        :param orders: 订单候选列表
        """
        # 检查是否为ZBit市场
        is_zbit_market = isinstance(market_pair.market, ZbitExchange)
        
        # 如果是ZBit市场，执行特定的订单处理逻辑
        if is_zbit_market:
            self.logger().info(f"在ZBit执行下单: {len(orders)}个订单")
            
            # 处理订单前检查市场状态
            if market_pair.market.network_status is not NetworkStatus.CONNECTED:
                self.logger().warning("ZBit市场未连接，无法下单")
                return
            
            # ZBit特有的订单处理逻辑可以添加在这里
            # 例如：特定的订单类型、参数等调整
        
        # 调用父类的下单方法
        super().place_orders(market_pair, orders)

    def format_status(self) -> str:
        """
        重写格式化状态方法，添加ZBit特有的状态信息
        
        :return: 格式化的状态字符串
        """
        # 先获取父类的状态字符串
        status = super().format_status()
        
        # 添加ZBit特有的状态信息
        try:
            if self._zbit_market is not None:
                zbit_lines = [
                    "",
                    "  ZBit特有状态信息:",
                    f"  对冲比率调整: {self._hedge_ratio_adjustment}",
                    f"  上次与ZBit同步: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self._last_zbit_sync_timestamp))}"
                ]
                
                # 添加特定交易对的滑点信息
                if self._zbit_specific_slippage:
                    zbit_lines.append("  特定交易对滑点设置:")
                    for pair, slippage in self._zbit_specific_slippage.items():
                        zbit_lines.append(f"    {pair}: {slippage}")
                
                # 将ZBit特有信息添加到状态字符串中
                status += "\n" + "\n".join(zbit_lines)
        except Exception as e:
            self.logger().error(f"格式化ZBit状态信息时出错: {str(e)}", exc_info=True)
        
        return status


def create_zbit_hedge_strategy(
    config_map: Dict,
    zbit_market_pairs: List[MarketTradingPairTuple],
    monitor_market_pairs: List[MarketTradingPairTuple],
    offsets: Dict[MarketTradingPairTuple, Decimal],
    status_report_interval: float = 900,
    max_order_age: float = 5
) -> ZbitHedgeStrategy:
    """
    创建ZBit对冲策略实例的工厂函数
    
    :param config_map: 策略配置字典
    :param zbit_market_pairs: ZBit市场交易对列表
    :param monitor_market_pairs: 监控市场交易对列表
    :param offsets: 市场交易对偏移量字典
    :param status_report_interval: 状态报告间隔(秒)
    :param max_order_age: 订单最大有效时间(秒)
    :return: ZbitHedgeStrategy实例
    """
    # 将配置字典转换为HedgeConfigMap对象
    from hummingbot.client.config.config_helpers import ClientConfigAdapter
    config_map_adapter = ClientConfigAdapter(config_map)
    hedge_config_map = HedgeConfigMap(**config_map_adapter.hb_config)
    
    # 创建额外的ZBit特有参数
    hedge_ratio_adjustment = Decimal(str(config_map.get("hedge_ratio_adjustment", "0.0")))
    
    # 创建特定交易对的滑点设置
    zbit_specific_slippage = {}
    specific_slippage_config = config_map.get("zbit_specific_slippage", {})
    for pair, slippage in specific_slippage_config.items():
        zbit_specific_slippage[pair] = Decimal(str(slippage))
    
    # 创建并返回ZbitHedgeStrategy实例
    return ZbitHedgeStrategy(
        config_map=hedge_config_map,
        hedge_market_pairs=zbit_market_pairs,
        market_pairs=monitor_market_pairs,
        offsets=offsets,
        status_report_interval=status_report_interval,
        max_order_age=max_order_age,
        enable_auto_set_position_mode=config_map.get("enable_auto_set_position_mode", True),
        hedge_ratio_adjustment=hedge_ratio_adjustment,
        zbit_specific_slippage=zbit_specific_slippage,
    ) 