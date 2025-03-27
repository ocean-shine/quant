#!/usr/bin/env python
import asyncio
import logging
from decimal import Decimal
from typing import Dict, List, Optional

from hummingbot.connector.exchange.zbit.zbit_exchange import ZbitExchange
from hummingbot.core.clock import Clock
from hummingbot.core.data_type.common import OrderType, TradeType
from hummingbot.core.utils.async_utils import safe_ensure_future
from hummingbot.logger import HummingbotLogger
from hummingbot.strategy.liquidity_mining.liquidity_mining import LiquidityMiningStrategy
from hummingbot.strategy.market_trading_pair_tuple import MarketTradingPairTuple

class ZbitLiquidityMining:
    """
    ZBit流动性挖矿策略封装类
    此类为用户提供了一种简化的方法来使用Hummingbot的流动性挖矿策略与ZBit交易所
    """
    
    _logger = None
    
    @classmethod
    def logger(cls) -> HummingbotLogger:
        """
        获取类的日志记录器
        """
        if cls._logger is None:
            cls._logger = logging.getLogger(__name__)
        return cls._logger
    
    def __init__(
        self,
        zbit_api_key: str,
        zbit_api_secret: str,
        token: str,
        markets: List[str],
        order_amount: Decimal,
        spread: Decimal,
        inventory_skew_enabled: bool = True,
        target_base_pct: Decimal = Decimal("0.5"),
        order_refresh_time: float = 60.0,
        order_refresh_tolerance_pct: Decimal = Decimal("0.2"),
        inventory_range_multiplier: Decimal = Decimal("1"),
        volatility_interval: int = 300,
        avg_volatility_period: int = 10,
        volatility_to_spread_multiplier: Decimal = Decimal("1"),
        max_spread: Decimal = Decimal("-1"),
        max_order_age: float = 3600.0,
        status_report_interval: float = 900,
        hb_app_notification: bool = False,
    ):
        """
        初始化ZBit流动性挖矿策略
        
        :param zbit_api_key: ZBit API密钥
        :param zbit_api_secret: ZBit API密钥的密码
        :param token: 要挖矿的代币符号（必须是交易对中的基础或报价代币）
        :param markets: 要参与的交易对列表
        :param order_amount: 每个订单的数量（以token为单位）
        :param spread: 买卖订单与中间价格的差距百分比
        :param inventory_skew_enabled: 是否启用库存偏斜
        :param target_base_pct: 目标基础资产百分比
        :param order_refresh_time: 刷新订单的时间间隔（秒）
        :param order_refresh_tolerance_pct: 刷新订单时的价格容忍度百分比
        :param inventory_range_multiplier: 库存范围乘数
        :param volatility_interval: 计算波动率的时间间隔（秒）
        :param avg_volatility_period: 计算平均波动率的周期数
        :param volatility_to_spread_multiplier: 波动率到价差的乘数
        :param max_spread: 最大价差百分比（-1表示忽略）
        :param max_order_age: 订单最大生命周期（秒）
        :param status_report_interval: 状态报告间隔（秒）
        :param hb_app_notification: 是否启用Hummingbot应用通知
        """
        # 保存参数
        self._zbit_api_key = zbit_api_key
        self._zbit_api_secret = zbit_api_secret
        self._token = token
        self._markets = markets
        self._order_amount = order_amount
        self._spread = spread
        self._inventory_skew_enabled = inventory_skew_enabled
        self._target_base_pct = target_base_pct
        self._order_refresh_time = order_refresh_time
        self._order_refresh_tolerance_pct = order_refresh_tolerance_pct
        self._inventory_range_multiplier = inventory_range_multiplier
        self._volatility_interval = volatility_interval
        self._avg_volatility_period = avg_volatility_period
        self._volatility_to_spread_multiplier = volatility_to_spread_multiplier
        self._max_spread = max_spread
        self._max_order_age = max_order_age
        self._status_report_interval = status_report_interval
        self._hb_app_notification = hb_app_notification
        
        # 初始化变量
        self._strategy = None
        self._zbit_exchange = None
        self._clock = None
        self._markets_trading_pair_tuples = {}
        self._last_status_report_timestamp = 0
    
    def start(self):
        """
        启动ZBit流动性挖矿策略
        """
        try:
            # 创建事件循环
            self._ev_loop = asyncio.get_event_loop()
            self._ev_loop.run_until_complete(self._start_strategy())
        except Exception as e:
            self.logger().error(f"策略启动时发生错误: {str(e)}", exc_info=True)
    
    async def _start_strategy(self):
        """
        异步启动策略
        """
        try:
            # 创建ZBit交易所实例
            self._zbit_exchange = ZbitExchange(
                zbit_api_key=self._zbit_api_key,
                zbit_api_secret=self._zbit_api_secret,
                trading_pairs=self._markets,
                trading_required=True
            )
            
            # 启动网络
            await self._zbit_exchange.start_network()
            self.logger().info("ZBit交易所连接已启动")
            
            # 创建市场交易对元组
            market_infos = {}
            for trading_pair in self._markets:
                market_infos[trading_pair] = MarketTradingPairTuple(
                    self._zbit_exchange,
                    trading_pair,
                    *trading_pair.split("-")
                )
            
            # 创建时钟
            self._clock = Clock(
                clock_mode="realtime",
                tick_size=1.0
            )
            self._clock.add_iterator(self._zbit_exchange)
            
            # 创建流动性挖矿策略
            self._strategy = LiquidityMiningStrategy()
            self._strategy.init_params(
                client_config_map=self._zbit_exchange._client_config_map,
                exchange=self._zbit_exchange,
                market_infos=market_infos,
                token=self._token,
                order_amount=self._order_amount,
                spread=self._spread,
                inventory_skew_enabled=self._inventory_skew_enabled,
                target_base_pct=self._target_base_pct,
                order_refresh_time=self._order_refresh_time,
                order_refresh_tolerance_pct=self._order_refresh_tolerance_pct,
                inventory_range_multiplier=self._inventory_range_multiplier,
                volatility_interval=self._volatility_interval,
                avg_volatility_period=self._avg_volatility_period,
                volatility_to_spread_multiplier=self._volatility_to_spread_multiplier,
                max_spread=self._max_spread,
                max_order_age=self._max_order_age,
                status_report_interval=self._status_report_interval,
                hb_app_notification=self._hb_app_notification
            )
            
            # 添加策略到时钟
            self._clock.add_iterator(self._strategy)
            
            # 启动策略
            self._strategy.start(self._clock, 0)
            
            # 启动时钟运行
            with self._clock:
                await self._run()
        except Exception as e:
            self.logger().error(f"策略执行期间发生错误: {str(e)}", exc_info=True)
            await self.stop()
    
    async def _run(self):
        """
        运行策略主循环
        """
        # 持续运行，直到用户中断
        while True:
            try:
                # 检查策略是否就绪
                if self._strategy and self._strategy._ready_to_trade:
                    # 打印状态
                    current_time = self._clock.current_timestamp
                    if current_time - self._last_status_report_timestamp > self._status_report_interval:
                        self._last_status_report_timestamp = current_time
                        status = await self._strategy.format_status()
                        self.logger().info(status)
                
                # 每秒休眠一次
                await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                self.logger().info("策略运行被取消")
                break
            except Exception as e:
                self.logger().error(f"策略运行时发生错误: {str(e)}", exc_info=True)
    
    async def stop(self):
        """
        停止策略和所有相关组件
        """
        self.logger().info("正在停止ZBit流动性挖矿策略...")
        
        # 停止策略
        if self._strategy:
            self._strategy.stop(self._clock)
        
        # 停止交易所网络
        if self._zbit_exchange:
            await self._zbit_exchange.stop_network()
        
        # 停止时钟
        if self._clock:
            self._clock.stop()
        
        self.logger().info("ZBit流动性挖矿策略已停止")


def create_zbit_liquidity_mining_strategy(
    zbit_api_key: str,
    zbit_api_secret: str,
    token: str,
    markets: List[str],
    order_amount: Decimal,
    spread: Decimal,
    **kwargs
) -> ZbitLiquidityMining:
    """
    创建一个ZBit流动性挖矿策略实例
    
    :param zbit_api_key: ZBit API密钥
    :param zbit_api_secret: ZBit API密钥的密码
    :param token: 要挖矿的代币符号
    :param markets: 要参与的交易对列表
    :param order_amount: 每个订单的数量
    :param spread: 买卖订单与中间价格的差距百分比
    :return: 策略实例
    """
    return ZbitLiquidityMining(
        zbit_api_key=zbit_api_key,
        zbit_api_secret=zbit_api_secret,
        token=token,
        markets=markets,
        order_amount=order_amount,
        spread=spread,
        **kwargs
    ) 