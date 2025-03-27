#!/usr/bin/env python

import asyncio
import logging
import sys
import os
from decimal import Decimal
from typing import Dict, List, Optional, Set

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hummingbot.connector.exchange.zbit.zbit_exchange import ZbitExchange
from hummingbot.core.clock import Clock, ClockMode
from hummingbot.core.data_type.common import OrderType, PriceType, TradeType
from hummingbot.core.event.event_logger import EventLogger
from hummingbot.core.event.events import MarketEvent
from hummingbot.strategy.market_trading_pair_tuple import MarketTradingPairTuple
from hummingbot.core.network_iterator import NetworkStatus

# 导入本地脚本
from scripts.zbit_hedge import ZbitHedgeStrategy, create_zbit_hedge_strategy
from scripts.zbit_hedge_config import get_zbit_hedge_config


# 模拟客户端配置适配器类
class MockClientConfigAdapter:
    def __init__(self):
        self.hb_config = {}
        self.balance_asset_limit = {}
        
    def get_exchange_limit_config(self, key):
        return {}


# 模拟交易量指标收集器
class MockTradeVolumeMetricCollector:
    def __init__(self):
        self._tracked_order_fills = {}
        
    def process_tick(self, timestamp):
        # 空方法，仅用于避免错误
        pass
    
    def collect_trade_volume(self, connector_name, timestamp, order_id, base_asset, quote_asset, 
                             base_volume, quote_volume, market=None):
        # 空方法，仅用于避免错误
        pass
        
    def start(self):
        # 空方法，仅用于避免错误
        pass
        
    def stop(self):
        # 空方法，仅用于避免错误
        pass


# 配置日志格式
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("zbit_hedge_test.log")
    ]
)

class ZbitHedgeTester:
    """
    ZBit对冲策略测试类
    
    用于在模拟环境中测试ZBit对冲策略功能
    """
    def __init__(self):
        # 初始化日志记录器
        self._logger = logging.getLogger(__name__)
        self._logger.setLevel(logging.INFO)
        
        # 初始化市场和策略
        self._zbit_market = None
        self._monitor_market = None
        self._strategy = None
        self._clock = None
        self._market_logger = None
        
        # 测试配置
        self._zbit_trading_pair = "BTC-USDT"
        self._monitor_trading_pair = "BTC-USDT"
        self._test_duration = 15  # 测试持续时间（秒）

    def logger(self):
        return self._logger

    async def run(self):
        """
        运行测试
        """
        try:
            # 创建市场、策略和时钟
            await self.setup()
            
            # 设置策略就绪状态
            self._strategy._all_markets_ready = True
            self.logger().info(f"手动设置策略就绪状态: {self._strategy._all_markets_ready}")
            
            # 启动时钟
            self.logger().info("启动时钟...")
            await self.run_clock()
            
            # 输出测试结果
            self.print_stats()
            
        except Exception as e:
            self.logger().error(f"测试过程中遇到错误: {str(e)}", exc_info=True)
        finally:
            # 清理资源
            await self.cleanup()

    async def setup(self):
        """
        设置测试环境
        """
        self.logger().info("设置测试环境...")
        
        # 创建ZBit交易所实例
        self._zbit_market = await self.setup_zbit_exchange("maker")
        
        # 创建监控交易所实例（例如：Binance）
        self._monitor_market = await self.setup_zbit_exchange("taker", True)
        
        # 创建市场交易对元组
        zbit_market_tuple = MarketTradingPairTuple(
            self._zbit_market, self._zbit_trading_pair, 
            self._zbit_trading_pair.split("-")[0], self._zbit_trading_pair.split("-")[1]
        )
        
        monitor_market_tuple = MarketTradingPairTuple(
            self._monitor_market, self._monitor_trading_pair, 
            self._monitor_trading_pair.split("-")[0], self._monitor_trading_pair.split("-")[1]
        )
        
        # 设置偏移量
        offsets = {
            zbit_market_tuple: Decimal("0.0"),
            monitor_market_tuple: Decimal("0.0")
        }
        
        # 获取策略配置
        config_map = get_zbit_hedge_config()
        
        # 创建策略
        self._strategy = create_zbit_hedge_strategy(
            config_map=config_map,
            zbit_market_pairs=[zbit_market_tuple],
            monitor_market_pairs=[monitor_market_tuple],
            offsets=offsets,
            status_report_interval=900,  # 状态报告间隔（秒）
            max_order_age=5              # 订单最大有效时间（秒）
        )
        
        # 创建事件日志记录器
        self._market_logger = EventLogger()
        for event_tag in [
            MarketEvent.BuyOrderCreated,
            MarketEvent.SellOrderCreated,
            MarketEvent.OrderFilled,
            MarketEvent.OrderCancelled,
            MarketEvent.BuyOrderCompleted,
            MarketEvent.SellOrderCompleted,
            MarketEvent.OrderFailure
        ]:
            self._zbit_market.add_listener(event_tag, self._market_logger)
        
        # 创建时钟
        self._clock = Clock(ClockMode.BACKTEST)
        self._clock.add_iterator(self._zbit_market)
        self._clock.add_iterator(self._monitor_market)
        self._clock.add_iterator(self._strategy)
        
        self.logger().info("测试环境设置完成")

    async def run_clock(self):
        """
        运行时钟，执行策略
        """
        self.logger().info(f"运行ZBit对冲策略测试...")
        
        # 记录开始时间
        start_time = self._clock.current_timestamp
        
        # 运行时钟指定的时间
        while self._clock.current_timestamp - start_time < self._test_duration:
            # 更新当前时间
            current_time = self._clock.current_timestamp
            
            # 手动推进时钟
            self._clock.backtest_til(current_time + 1)
            await asyncio.sleep(0.01)  # 轻微延迟，避免CPU占用过高
            
            # 输出状态更新
            if (int(current_time) % 5) == 0:
                status = self._strategy.format_status()
                if status:
                    self.logger().info(f"\n{status}")
        
        self.logger().info(f"测试运行完成，持续了{self._test_duration}秒")

    async def setup_zbit_exchange(self, market_type: str, is_taker: bool = False) -> ZbitExchange:
        """
        设置ZBit交易所实例
        
        :param market_type: 市场类型，'maker'或'taker'
        :param is_taker: 是否为taker市场
        :return: ZbitExchange实例
        """
        self.logger().info(f"设置ZBit交易所 ({market_type})...")
        
        # 创建ZBit交易所实例
        market = ZbitExchange(
            zbit_api_key="vmPUZE6mv9SD5VNHk4HlWFsOr6aKE2zvsw0MuIgwCIPy6utIco14y7Ju91duEh8A",
            zbit_api_secret="NhqPtmdSJYdKjVHjA7PZj4Mge3R5YNiP1e3UZjInClVN65XAbvqqM6A7H5fATj0j",
            trading_pairs=[self._zbit_trading_pair if not is_taker else self._monitor_trading_pair]
        )
        
        # 添加交易量指标收集器
        market._trade_volume_metric_collector = MockTradeVolumeMetricCollector()
        
        # 为交易所添加模拟方法
        
        # 添加get_price方法
        def get_price(self, trading_pair, is_buy=None, price_type=None):
            if price_type is not None:
                is_buy = price_type == PriceType.BestAsk
            
            # 设置不同的价格，以创造对冲机会
            base_price = 50000.0  # 基准价格
            
            if is_taker:
                # 对于监控市场，价格有偏差
                if is_buy:  # taker的ask价格
                    return Decimal(str(base_price * 0.98))  # 低于做市商2%
                else:  # taker的bid价格
                    return Decimal(str(base_price * 1.02))  # 高于做市商2%
            else:
                # 对于ZBit市场，价格是基准
                return Decimal(str(base_price))
                
        market.get_price = get_price.__get__(market)
        
        # 添加get_balance方法
        def get_balance(self, asset):
            if asset == "BTC":
                return Decimal("1.0")
            elif asset == "USDT":
                return Decimal("50000.0")
            else:
                return Decimal("0.0")
                
        market.get_balance = get_balance.__get__(market)
        
        # 添加get_available_balance方法
        def get_available_balance(self, asset):
            return self.get_balance(asset)
            
        market.get_available_balance = get_available_balance.__get__(market)
        
        # 添加buy方法
        def buy(self, trading_pair, amount, order_type, price):
            self.logger().info(f"模拟买入: {trading_pair}, 数量: {amount}, 价格: {price}")
            return f"buy-{trading_pair}-{amount}-{price}"
            
        market.buy = buy.__get__(market)
        
        # 添加sell方法
        def sell(self, trading_pair, amount, order_type, price):
            self.logger().info(f"模拟卖出: {trading_pair}, 数量: {amount}, 价格: {price}")
            return f"sell-{trading_pair}-{amount}-{price}"
            
        market.sell = sell.__get__(market)
        
        # 添加cancel方法
        def cancel(self, trading_pair, order_id):
            self.logger().info(f"取消订单: {trading_pair}, 订单ID: {order_id}")
            return True
            
        market.cancel = cancel.__get__(market)
        
        # 添加get_fee方法
        def get_fee(self, base_currency, quote_currency, order_type, order_side, amount, price, is_maker=None):
            from hummingbot.core.data_type.trade_fee import AddedToCostTradeFee
            return AddedToCostTradeFee(percent=Decimal("0.001"))  # 0.1%的手续费
            
        market.get_fee = get_fee.__get__(market)
        
        # 设置网络状态为已连接
        market._network_status = NetworkStatus.CONNECTED
        
        # 设置ready状态
        market._trading_pairs_initialized = {self._zbit_trading_pair if not is_taker else self._monitor_trading_pair: True}
        market._account_available_balances_initialized = True
        market._account_balances_initialized = True
        market._trading_rules_initialized = True
        market._user_stream_initialized = True
        market._trading_required_initialized = True
        
        # 设置交易规则
        market._trading_rules = {}
        
        # 添加check_network方法
        async def check_network(self):
            return NetworkStatus.CONNECTED
        
        market.check_network = check_network.__get__(market)
        
        self.logger().info(f"ZBit交易所设置完成 ({market_type})")
        return market

    async def cleanup(self):
        """
        清理资源
        """
        self.logger().info("清理资源...")
        
        # 取消所有订单
        if self._zbit_market is not None:
            self.logger().info("取消所有订单...")
            await self._zbit_market.cancel_all(10)
        
        # 停止市场
        if self._zbit_market is not None:
            self.logger().info("停止ZBit市场...")
            await self._zbit_market.stop_network()
        
        if self._monitor_market is not None:
            self.logger().info("停止监控市场...")
            await self._monitor_market.stop_network()
        
        self.logger().info("资源清理完成")

    def print_stats(self):
        """
        打印测试统计信息
        """
        self.logger().info("\n" + "*" * 50)
        self.logger().info("  ZBit对冲策略 - 测试结果 ")
        self.logger().info("*" * 50)
        
        # 输出订单统计信息
        if self._market_logger:
            orders_created = len([e for e in self._market_logger.event_log if e[0] in [MarketEvent.BuyOrderCreated, MarketEvent.SellOrderCreated]])
            orders_filled = len([e for e in self._market_logger.event_log if e[0] == MarketEvent.OrderFilled])
            orders_cancelled = len([e for e in self._market_logger.event_log if e[0] == MarketEvent.OrderCancelled])
            orders_failed = len([e for e in self._market_logger.event_log if e[0] == MarketEvent.OrderFailure])
            
            self.logger().info(f"总测试时长: {self._test_duration} 秒")
            self.logger().info(f"订单创建: {orders_created}")
            self.logger().info(f"订单成交: {orders_filled}")
            self.logger().info(f"订单取消: {orders_cancelled}")
            self.logger().info(f"订单失败: {orders_failed}")
        
        # 输出市场统计
        if self._zbit_market and self._monitor_market:
            # 交易对和资产
            zbit_base, zbit_quote = self._zbit_trading_pair.split("-")
            monitor_base, monitor_quote = self._monitor_trading_pair.split("-")
            
            # 价格信息
            zbit_price = self._zbit_market.get_price(self._zbit_trading_pair, False)
            monitor_price = self._monitor_market.get_price(self._monitor_trading_pair, False)
            
            # 账户余额
            zbit_base_balance = self._zbit_market.get_balance(zbit_base)
            zbit_quote_balance = self._zbit_market.get_balance(zbit_quote)
            monitor_base_balance = self._monitor_market.get_balance(monitor_base)
            monitor_quote_balance = self._monitor_market.get_balance(monitor_quote)
            
            self.logger().info(f"ZBit价格 ({self._zbit_trading_pair}): {zbit_price}")
            self.logger().info(f"监控市场价格 ({self._monitor_trading_pair}): {monitor_price}")
            self.logger().info(f"理论对冲机会: {((monitor_price / zbit_price) - 1) * 100:.2f}%")
            self.logger().info(f"ZBit余额: {zbit_base_balance} {zbit_base}, {zbit_quote_balance} {zbit_quote}")
            self.logger().info(f"监控市场余额: {monitor_base_balance} {monitor_base}, {monitor_quote_balance} {monitor_quote}")
        
        # 输出策略状态
        if self._strategy:
            self.logger().info("\nZBit对冲策略状态:")
            status = self._strategy.format_status()
            self.logger().info(status)
        
        self.logger().info("*" * 50 + "\n")


async def main():
    """
    主函数
    """
    tester = ZbitHedgeTester()
    print("正在运行ZBit对冲策略测试...")
    await tester.run()
    print("测试完成，详细日志保存在zbit_hedge_test.log文件中")


if __name__ == "__main__":
    asyncio.run(main()) 