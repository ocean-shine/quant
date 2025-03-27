#!/usr/bin/env python

import logging
import time
from decimal import Decimal
from typing import Dict, List

import pandas as pd

from hummingbot.connector.exchange.zbit.zbit_exchange import ZbitExchange
from hummingbot.core.clock import Clock
from hummingbot.core.data_type.limit_order import LimitOrder
from hummingbot.core.data_type.order_book import OrderBook
from hummingbot.core.event.events import MarketEvent, OrderType, TradeType
from hummingbot.strategy.cross_exchange_mining.cross_exchange_mining import CrossExchangeMiningStrategy
from hummingbot.strategy.cross_exchange_mining.cross_exchange_mining_pair import CrossExchangeMiningPair
from hummingbot.strategy.market_trading_pair_tuple import MarketTradingPairTuple


class ZbitCrossExchangeMining(CrossExchangeMiningStrategy):
    """
    ZBit跨交易所挖矿策略

    这个策略继承自Hummingbot的CrossExchangeMiningStrategy，为ZBit交易所提供跨交易所挖矿支持。
    跨交易所挖矿策略通过在做市商市场(ZBit)和对手方市场之间进行套利交易，
    同时通过维持做市深度获取ZBit交易所的挖矿收益。
    """

    # 日志记录器
    _logger = None

    @classmethod
    def logger(cls):
        if cls._logger is None:
            cls._logger = logging.getLogger(__name__)
        return cls._logger

    def __init__(self,
                 zbit_market: ZbitExchange,
                 taker_market: ZbitExchange,
                 zbit_market_trading_pair: str,
                 taker_market_trading_pair: str,
                 order_amount: Decimal,
                 min_profitability: Decimal,
                 order_refresh_time: float = 30.0,
                 order_refresh_tolerance_pct: Decimal = Decimal("0.02"),
                 min_order_amount: Decimal = Decimal("0.0"),
                 rate_curve: Decimal = Decimal("0.001"),
                 trade_fee: Decimal = Decimal("0.001"),
                 balance_adjustment_duration: int = 0,
                 volatility_buffer_size: int = 0,
                 min_prof_tol_high: Decimal = Decimal("2.0"),
                 min_prof_tol_low: Decimal = Decimal("0.1"),
                 slippage_buffer: Decimal = Decimal("5.0"),
                 min_prof_adj_timer: float = 60.0,
                 logging_options: int = (CrossExchangeMiningStrategy.OPTION_LOG_CREATE_ORDER |
                                        CrossExchangeMiningStrategy.OPTION_LOG_ADJUST_ORDER |
                                        CrossExchangeMiningStrategy.OPTION_LOG_MAKER_ORDER_FILLED |
                                        CrossExchangeMiningStrategy.OPTION_LOG_REMOVING_ORDER |
                                        CrossExchangeMiningStrategy.OPTION_LOG_STATUS_REPORT |
                                        CrossExchangeMiningStrategy.OPTION_LOG_MAKER_ORDER_HEDGED),
                 status_report_interval: float = 900,
                 hb_app_notification: bool = False):
        """
        初始化ZBit跨交易所挖矿策略

        :param zbit_market: ZBit交易所市场
        :param taker_market: 对手方交易所市场
        :param zbit_market_trading_pair: ZBit交易对，如"BTC-USDT"
        :param taker_market_trading_pair: 对手方交易对，如"BTC-USDT"
        :param order_amount: 订单数量
        :param min_profitability: 最低盈利要求，以百分比表示
        :param order_refresh_time: 订单刷新时间(秒)
        :param order_refresh_tolerance_pct: 订单刷新容忍度百分比
        :param min_order_amount: 最小订单数量
        :param rate_curve: 费率曲线
        :param trade_fee: 交易费用
        :param balance_adjustment_duration: 余额调整持续时间
        :param volatility_buffer_size: 波动性缓冲区大小
        :param min_prof_tol_high: 最低盈利容忍度上限
        :param min_prof_tol_low: 最低盈利容忍度下限
        :param slippage_buffer: 滑点缓冲
        :param min_prof_adj_timer: 最低盈利调整计时器
        :param logging_options: 日志选项
        :param status_report_interval: 状态报告间隔(秒)
        :param hb_app_notification: 是否启用Hummingbot应用通知
        """
        # 调用父类的__init__
        super().__init__()
        
        # 解析交易对的基础资产和报价资产
        zbit_base, zbit_quote = zbit_market_trading_pair.split("-")
        taker_base, taker_quote = taker_market_trading_pair.split("-")

        # 创建市场交易对元组
        zbit_market_tuple = MarketTradingPairTuple(zbit_market, zbit_market_trading_pair, zbit_base, zbit_quote)
        taker_market_tuple = MarketTradingPairTuple(taker_market, taker_market_trading_pair, taker_base, taker_quote)

        # 创建跨交易所挖矿对
        self._market_pairs = [CrossExchangeMiningPair(
            maker=zbit_market_tuple,
            taker=taker_market_tuple
        )]

        # 创建配置映射
        from hummingbot.strategy.cross_exchange_mining.cross_exchange_mining_config_map_pydantic import (
            CrossExchangeMiningConfigMap
        )
        
        config_map = CrossExchangeMiningConfigMap(
            strategy="cross_exchange_mining",
            maker_market=zbit_market.name,
            taker_market=taker_market.name,
            maker_market_trading_pair=zbit_market_trading_pair,
            taker_market_trading_pair=taker_market_trading_pair,
            order_amount=order_amount,
            min_profitability=min_profitability,
            min_order_amount=min_order_amount,
            rate_curve=rate_curve,
            trade_fee=trade_fee,
            balance_adjustment_duration=balance_adjustment_duration,
            volatility_buffer_size=volatility_buffer_size,
            min_prof_tol_high=min_prof_tol_high,
            min_prof_tol_low=min_prof_tol_low,
            slippage_buffer=slippage_buffer,
            min_prof_adj_timer=min_prof_adj_timer,
        )

        # 调用父类的init_params方法
        self.init_params(
            config_map=config_map,
            market_pairs=self._market_pairs,
            logging_options=logging_options,
            status_report_interval=status_report_interval,
        )
        
        # 添加自定义属性
        self._zbit_market = zbit_market
        self._taker_market = taker_market
        self._last_status_report_ts = 0
        self._last_timestamp = 0
        self._zbit_market_info = zbit_market_tuple
        self._taker_market_info = taker_market_tuple
        self._order_refresh_tolerance_pct = order_refresh_tolerance_pct
        self._order_refresh_time = order_refresh_time
        self._order_amount = order_amount

    def tick(self, timestamp: float):
        """
        策略的主要循环，每个时钟周期调用一次
        :param timestamp: 当前时间戳
        """
        # 记录当前时间戳
        self._last_timestamp = timestamp
        
        # 检查所有市场是否就绪
        if not self._all_markets_ready:
            self._all_markets_ready = all(market.ready for market in self.active_markets)
            if not self._all_markets_ready:
                # 添加调试日志
                self.logger().debug("等待市场就绪...")
                for market in self.active_markets:
                    self.logger().debug(f"  {market.name}: {market.ready}")
                return
            else:
                self.logger().info("所有市场已就绪。开始策略执行。")

        # 调用父类的tick方法继续执行通用逻辑
        super().tick(timestamp)

        # 定期生成状态报告
        self._generate_status_report(timestamp)

    def _generate_status_report(self, timestamp: float) -> None:
        """
        生成策略状态报告
        :param timestamp: 当前时间戳
        """
        if self.status_report_interval > 0 and timestamp - self._last_status_report_ts > self.status_report_interval:
            self.logger().info(self.format_status())
            self._last_status_report_ts = timestamp

    def get_price_type(self, price_type_str: str) -> bool:
        """
        转换价格类型字符串到布尔值
        :param price_type_str: "bid"或"ask"
        :return: True表示ask(卖出价), False表示bid(买入价)
        """
        if price_type_str == "ask":
            return True
        elif price_type_str == "bid":
            return False
        else:
            raise ValueError(f"Invalid price type string: {price_type_str}")

    def _update_order_prices(self, timestamp: float):
        """
        更新订单价格
        :param timestamp: 当前时间戳
        """
        # 在这里可以实现ZBit交易所特有的订单价格更新逻辑
        # 目前简单调用父类的_update_order_prices方法
        super()._update_order_prices(timestamp)

    def format_status(self) -> str:
        """
        生成策略状态字符串
        :return: 格式化的状态字符串
        """
        # 可以自定义状态报告的格式
        # 先调用父类的format_status获取基本信息
        status = super().format_status()
        
        # 添加ZBit特有的状态信息
        zbit_lines = [
            "\n  ZBit跨交易所挖矿策略状态:",
            f"  订单数量: {self._order_amount}",
            f"  刷新时间: {self._order_refresh_time}秒",
            f"  刷新容忍度: {self._order_refresh_tolerance_pct}%"
        ]
        
        # 合并状态信息
        return status + "\n" + "\n".join(zbit_lines)


def get_zbit_cross_exchange_mining_config() -> Dict:
    """
    获取ZBit跨交易所挖矿策略的默认配置
    :return: 配置字典
    """
    return {
        "order_amount": Decimal("0.1"),               # 订单量，这里设为0.1 BTC
        "min_profitability": Decimal("1.0"),          # 最低盈利要求，1%
        "order_refresh_time": 30.0,                   # 每30秒刷新订单
        "order_refresh_tolerance_pct": Decimal("0.2"), # 价格波动小于0.2%不更新订单
        "min_order_amount": Decimal("0.01"),           # 最小订单数量
        "rate_curve": Decimal("0.001"),                # 费率曲线
        "trade_fee": Decimal("0.001"),                 # 交易费用，0.1%
        "balance_adjustment_duration": 0,              # 余额调整持续时间
        "volatility_buffer_size": 10,                  # 波动性缓冲区大小
        "min_prof_tol_high": Decimal("2.0"),           # 最低盈利容忍度上限
        "min_prof_tol_low": Decimal("0.1"),            # 最低盈利容忍度下限
        "slippage_buffer": Decimal("5.0"),             # 滑点缓冲5%
        "min_prof_adj_timer": 60.0,                    # 最低盈利调整计时器，60秒
        "maker_market_trading_pair": "BTC-USDT",      # 做市商交易对
        "taker_market_trading_pair": "BTC-USDT",      # 对手方交易对
    } 