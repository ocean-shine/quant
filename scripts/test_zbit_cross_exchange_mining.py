#!/usr/bin/env python

import asyncio
import logging
import time
from decimal import Decimal
from typing import Dict, List

from hummingbot.core.clock import Clock, ClockMode
from hummingbot.core.event.event_logger import EventLogger
from hummingbot.core.event.events import MarketEvent, OrderBookEvent, OrderBookTradeEvent, TradeType
from hummingbot.connector.exchange.zbit.zbit_exchange import ZbitExchange
from hummingbot.strategy.market_trading_pair_tuple import MarketTradingPairTuple

# 添加当前目录到路径
import sys
import os
sys.path.append(os.path.dirname(os.path.realpath(__file__)))
from zbit_cross_exchange_mining import ZbitCrossExchangeMining, get_zbit_cross_exchange_mining_config


class ZbitCrossExchangeMiningTester:
    """
    ZBit跨交易所挖矿策略的测试工具
    """
    
    # 默认API密钥（测试用）
    DEFAULT_ZBIT_API_KEY = "vmPUZE6mv9SD5V5e14y7Ju91duEh8A"
    DEFAULT_ZBIT_API_SECRET = "902ae3cb34ecee2779aa4d3e1d226686"
    
    @classmethod
    def logger(cls):
        return logging.getLogger(__name__)
    
    def __init__(self):
        # 初始化测试器属性
        self._clock: Clock = None
        self._strategy: ZbitCrossExchangeMining = None
        self._maker_market: ZbitExchange = None
        self._taker_market: ZbitExchange = None
        self._config = get_zbit_cross_exchange_mining_config()
        self._maker_trading_pair = self._config["maker_market_trading_pair"]
        self._taker_trading_pair = self._config["taker_market_trading_pair"]
        self._market_events_logger = None
    
    async def run_clock(self):
        """
        运行时钟一段固定时间
        """
        self.logger().info("运行ZBit跨交易所挖矿策略测试...")
        
        # 每秒手动调用策略的tick方法
        start_time = time.time()
        run_time = 15  # 运行15秒以便查看结果
        
        while time.time() - start_time < run_time:
            # 设置当前时间戳
            current_time = time.time()
            self._maker_market._set_current_timestamp(int(current_time))
            self._taker_market._set_current_timestamp(int(current_time))
            
            # 手动调用策略的tick方法
            self._strategy.tick(current_time)
            
            # 输出策略状态
            if int(current_time) % 5 == 0:  # 每5秒输出一次状态
                self.logger().info("\n" + self._strategy.format_status())
            
            # 等待1秒
            await asyncio.sleep(1)
            
        self.logger().info(f"测试运行完成，持续了{run_time}秒")
    
    async def run(self):
        """
        设置并运行测试
        """
        try:
            # 设置市场
            self._maker_market = await self.setup_zbit_exchange(is_maker=True)
            self._taker_market = await self.setup_zbit_exchange(is_maker=False)
            
            # 设置事件日志记录器来捕获市场事件
            self._market_events_logger = EventLogger()
            for event_tag in [MarketEvent.BuyOrderCreated,
                             MarketEvent.SellOrderCreated,
                             MarketEvent.OrderFilled,
                             MarketEvent.OrderCancelled,
                             MarketEvent.BuyOrderCompleted,
                             MarketEvent.SellOrderCompleted,
                             MarketEvent.OrderFailure]:
                self._maker_market.add_listener(event_tag, self._market_events_logger)
            
            # 创建策略
            self._strategy = self.create_strategy()
            
            # 手动设置策略就绪状态
            self._strategy._all_markets_ready = True
            self.logger().info(f"手动设置策略就绪状态: {self._strategy._all_markets_ready}")
            
            # 设置并运行时钟
            self._clock = Clock(ClockMode.REALTIME)
            self._clock.add_iterator(self._maker_market)
            self._clock.add_iterator(self._taker_market)
            self._clock.add_iterator(self._strategy)
            
            self.logger().info("启动时钟...")
            with self._clock:
                await self.run_clock()
            
            # 打印测试结果
            self.print_stats()
            
        except Exception as e:
            self.logger().error(f"测试过程中遇到错误: {e}", exc_info=True)
        finally:
            # 清理
            self.logger().info("清理中...")
            await self.cleanup()
    
    def create_strategy(self) -> ZbitCrossExchangeMining:
        """
        创建策略实例
        """
        config = self._config
        
        # 创建策略实例
        strategy = ZbitCrossExchangeMining(
            zbit_market=self._maker_market,
            taker_market=self._taker_market,
            zbit_market_trading_pair=self._maker_trading_pair,
            taker_market_trading_pair=self._taker_trading_pair,
            order_amount=config["order_amount"],
            min_profitability=config["min_profitability"],
            order_refresh_time=config["order_refresh_time"],
            order_refresh_tolerance_pct=config["order_refresh_tolerance_pct"],
            min_order_amount=config["min_order_amount"],
            rate_curve=config["rate_curve"],
            trade_fee=config["trade_fee"],
            balance_adjustment_duration=config["balance_adjustment_duration"],
            volatility_buffer_size=config["volatility_buffer_size"],
            min_prof_tol_high=config["min_prof_tol_high"],
            min_prof_tol_low=config["min_prof_tol_low"],
            slippage_buffer=config["slippage_buffer"],
            min_prof_adj_timer=config["min_prof_adj_timer"],
        )
        
        return strategy
    
    async def setup_zbit_exchange(self, is_maker=True) -> ZbitExchange:
        """
        设置ZBit交易所连接器
        """
        # 获取API凭证 - 使用默认值或环境变量
        api_key = os.getenv("ZBIT_API_KEY", self.DEFAULT_ZBIT_API_KEY)
        api_secret = os.getenv("ZBIT_API_SECRET", self.DEFAULT_ZBIT_API_SECRET)
        
        market_type = "做市商" if is_maker else "对手方"
        self.logger().info(f"使用API密钥: {api_key[:5]}...{api_key[-5:]} 连接ZBit交易所 ({market_type})")
        
        # 初始化交易所
        market = ZbitExchange(
            zbit_api_key=api_key,
            zbit_api_secret=api_secret,
            trading_pairs=[self._maker_trading_pair if is_maker else self._taker_trading_pair]
        )
        
        # 添加配置适配器
        market._config_adapter = MockClientConfigAdapter()
        
        # 添加_active_bids和_active_asks属性
        market._active_bids = []
        market._active_asks = []
        
        # 添加get_exchange_limit_config方法
        def get_exchange_limit_config(self, key):
            return self._config_adapter.balance_asset_limit
            
        # 添加get_balance方法
        def get_balance(self, asset):
            return self._account_balances.get(asset, Decimal("0"))
        
        # 添加buy方法
        def buy(self, trading_pair, amount, order_type, price):
            import random
            import string
            # 生成随机订单ID
            order_id = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(10))
            self.logger().info(f"创建买单: {trading_pair}, 价格: {price}, 数量: {amount}, 订单ID: {order_id}")
            return order_id
            
        # 添加sell方法
        def sell(self, trading_pair, amount, order_type, price):
            import random
            import string
            # 生成随机订单ID
            order_id = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(10))
            self.logger().info(f"创建卖单: {trading_pair}, 价格: {price}, 数量: {amount}, 订单ID: {order_id}")
            return order_id
        
        # 添加cancel方法
        def cancel(self, trading_pair, order_id):
            self.logger().info(f"取消订单: {trading_pair}, 订单ID: {order_id}")
            return True
            
        # 添加get_fee方法
        def get_fee(self, trading_pair, order_type, order_side, amount, price, is_maker=None):
            from hummingbot.core.data_type.trade_fee import AddedToCostTradeFee
            return AddedToCostTradeFee(percent=Decimal("0.001"))  # 0.1%的手续费
        
        # 添加get_order_book方法
        def get_order_book(self, trading_pair):
            from hummingbot.core.data_type.order_book import OrderBook
            
            # 创建一个简单的MockOrderBook作为OrderBook的代理
            class MockOrderBook(OrderBook):
                def get_price(self, is_buy):
                    return Decimal(str(base_price * 1.00)) if is_buy else Decimal(str(base_price * 1.00))
                
                def get_vwap_for_volume(self, is_buy, volume):
                    return MockQueryResult(volume, Decimal(str(base_price)), volume)
                
                def get_price_for_volume(self, is_buy, volume):
                    return MockQueryResult(volume, Decimal(str(base_price)), volume)
                
                def get_price_for_quote_volume(self, is_buy, volume):
                    return MockQueryResult(volume, Decimal(str(base_price)), volume)
                
                def get_volume_for_price(self, is_buy, price):
                    return MockQueryResult(price, price, Decimal("1.0"))
                
                def get_quote_volume_for_base_amount(self, is_buy, amount):
                    return MockQueryResult(amount, Decimal("0"), amount * Decimal(str(base_price)))
                
                def c_get_price(self, is_buy):
                    return float(self.get_price(is_buy))
            
            return MockOrderBook()
        
        # 将方法绑定到market对象
        market.get_exchange_limit_config = get_exchange_limit_config.__get__(market)
        market.get_balance = get_balance.__get__(market)
        market.buy = buy.__get__(market)
        market.sell = sell.__get__(market)
        market.cancel = cancel.__get__(market)
        market.get_fee = get_fee.__get__(market)
        market.get_order_book = get_order_book.__get__(market)
        
        # 模拟连接
        try:
            self.logger().info("Using mock account balances for testing.")
            market._account_balances = {
                "BTC": Decimal("1.0"),
                "USDT": Decimal("10000.0")
            }
            
            # 模拟价格
            base_price = 50000.0  # 基础价格
            
            # 设置不同的价格，创造套利机会
            if is_maker:
                def get_price(self, trading_pair, is_buy=None, price_type=None):
                    if price_type is not None:
                        is_buy = self.get_price_type(price_type)
                    if is_buy:  # 做市商的ask价格
                        return Decimal(str(base_price * 1.00))  # 基准价格
                    else:  # 做市商的bid价格
                        return Decimal(str(base_price * 1.00))  # 基准价格
                market.get_price = get_price.__get__(market)
                
                # 添加get_price_type助手方法
                def get_price_type(self, price_type_str):
                    return price_type_str == "ask"
                market.get_price_type = get_price_type.__get__(market)
                
                # 添加get_mid_price方法避免调用get_price
                def get_mid_price(self, trading_pair):
                    return Decimal(str(base_price * 1.00))  # 基准价格
                market.get_mid_price = get_mid_price.__get__(market)
            else:
                def get_price(self, trading_pair, is_buy=None, price_type=None):
                    if price_type is not None:
                        is_buy = self.get_price_type(price_type)
                    if is_buy:  # 对手方市场的ask价格
                        return Decimal(str(base_price * 0.98))  # 比做市商的ask价格低2%
                    else:  # 对手方市场的bid价格
                        return Decimal(str(base_price * 1.02))  # 比做市商的bid价格高2%
                market.get_price = get_price.__get__(market)
                
                # 添加get_price_type助手方法
                def get_price_type(self, price_type_str):
                    return price_type_str == "ask"
                market.get_price_type = get_price_type.__get__(market)
                
                # 添加get_mid_price方法避免调用get_price
                def get_mid_price(self, trading_pair):
                    # 取买卖价格的中间值
                    ask = Decimal(str(base_price * 0.98))  # ask价格
                    bid = Decimal(str(base_price * 1.02))  # bid价格
                    return (ask + bid) / Decimal("2.0")
                market.get_mid_price = get_mid_price.__get__(market)
        except Exception as e:
            self.logger().warning(f"更新余额时出错(可能是连接错误): {e}")
        
        # 启动市场
        await market.start_network()
        
        # 手动设置就绪状态
        if hasattr(market, "_status"):
            for key in market._status:
                market._status[key] = True
        elif hasattr(market, "status_dict"):
            # 如果有status_dict属性，确保所有状态都为True
            for key in market.status_dict:
                market.status_dict[key] = True
        
        # 确保就绪状态
        self.logger().info(f"设置{market_type}就绪状态: {market.ready}")
        
        self.logger().info(f"ZBit交易所初始化完成 ({market_type})")
        return market
    
    async def cleanup(self):
        """
        清理所有活跃订单和连接
        """
        # 清理做市商市场
        if self._maker_market is not None:
            self.logger().info("取消做市商上的所有订单...")
            try:
                # 取消所有活跃订单
                await self._maker_market.cancel_all(timeout_seconds=10)
                
                # 移除事件监听器
                if self._market_events_logger is not None:
                    for event_tag in [MarketEvent.BuyOrderCreated,
                                     MarketEvent.SellOrderCreated,
                                     MarketEvent.OrderFilled,
                                     MarketEvent.OrderCancelled,
                                     MarketEvent.BuyOrderCompleted,
                                     MarketEvent.SellOrderCompleted,
                                     MarketEvent.OrderFailure]:
                        self._maker_market.remove_listener(event_tag, self._market_events_logger)
                
                # 停止网络
                await self._maker_market.stop_network()
                
            except Exception as e:
                self.logger().error(f"清理做市商市场时出错: {e}", exc_info=True)
        
        # 清理对手方市场
        if self._taker_market is not None:
            self.logger().info("停止对手方市场连接...")
            try:
                # 停止网络
                await self._taker_market.stop_network()
                    
            except Exception as e:
                self.logger().error(f"清理对手方市场时出错: {e}", exc_info=True)
    
    def print_stats(self):
        """
        打印测试统计信息
        """
        if self._market_events_logger is not None:
            # 提取事件
            buy_orders_created = [evt for evt in self._market_events_logger.event_log
                                if isinstance(evt, tuple) and evt[0] == MarketEvent.BuyOrderCreated]
            sell_orders_created = [evt for evt in self._market_events_logger.event_log
                                 if isinstance(evt, tuple) and evt[0] == MarketEvent.SellOrderCreated]
            orders_filled = [evt for evt in self._market_events_logger.event_log
                           if isinstance(evt, tuple) and evt[0] == MarketEvent.OrderFilled]
            orders_cancelled = [evt for evt in self._market_events_logger.event_log
                              if isinstance(evt, tuple) and evt[0] == MarketEvent.OrderCancelled]
            orders_failed = [evt for evt in self._market_events_logger.event_log
                           if isinstance(evt, tuple) and evt[0] == MarketEvent.OrderFailure]
            
            # 打印摘要
            self.logger().info("\n" + "*" * 50)
            self.logger().info("  ZBit跨交易所挖矿策略 - 测试结果 ")
            self.logger().info("*" * 50)
            self.logger().info(f"总测试时长: {15} 秒")
            self.logger().info(f"ZBit交易对: {self._maker_trading_pair}")
            self.logger().info(f"对手方交易对: {self._taker_trading_pair}")
            self.logger().info(f"买单创建: {len(buy_orders_created)}")
            self.logger().info(f"卖单创建: {len(sell_orders_created)}")
            self.logger().info(f"订单成交: {len(orders_filled)}")
            self.logger().info(f"订单取消: {len(orders_cancelled)}")
            self.logger().info(f"订单失败: {len(orders_failed)}")
            
            # 打印策略状态
            if self._strategy is not None:
                self.logger().info("\n策略状态:")
                self.logger().info(self._strategy.format_status())
            
            self.logger().info("*" * 50 + "\n")
            
            # 打印市场分析
            if self._maker_market is not None and self._taker_market is not None:
                # 获取交易对基础资产和报价资产
                maker_base, maker_quote = self._maker_trading_pair.split("-")
                taker_base, taker_quote = self._taker_trading_pair.split("-")
                
                # 余额信息
                maker_base_balance = self._maker_market.get_balance(maker_base)
                maker_quote_balance = self._maker_market.get_balance(maker_quote)
                taker_base_balance = self._taker_market.get_balance(taker_base)
                taker_quote_balance = self._taker_market.get_balance(taker_quote)
                
                self.logger().info(f"做市商余额: {maker_base_balance} {maker_base}, {maker_quote_balance} {maker_quote}")
                self.logger().info(f"对手方余额: {taker_base_balance} {taker_base}, {taker_quote_balance} {taker_quote}")
                
                # 价格分析
                try:
                    maker_bid = self._maker_market.get_price(self._maker_trading_pair, False)
                    maker_ask = self._maker_market.get_price(self._maker_trading_pair, True)
                    taker_bid = self._taker_market.get_price(self._taker_trading_pair, False)
                    taker_ask = self._taker_market.get_price(self._taker_trading_pair, True)
                    
                    self.logger().info(f"做市商价格: 买入={maker_bid:.6f}, 卖出={maker_ask:.6f}")
                    self.logger().info(f"对手方价格: 买入={taker_bid:.6f}, 卖出={taker_ask:.6f}")
                    
                    # 计算套利机会
                    buy_arb = (taker_bid - maker_ask) / maker_ask if maker_ask > 0 else 0
                    sell_arb = (maker_bid - taker_ask) / taker_ask if taker_ask > 0 else 0
                    
                    self.logger().info(f"买入套利机会: {buy_arb:.4%}")
                    self.logger().info(f"卖出套利机会: {sell_arb:.4%}")
                    
                except Exception as e:
                    self.logger().error(f"获取价格信息时出错: {e}")


class MockQueryResult:
    """
    简单的模拟查询结果类，用于订单簿操作
    """
    def __init__(self, query_volume, result_price, result_volume):
        self.query_volume = query_volume
        self.query_price = query_volume  # 用于price查询
        self.result_price = result_price
        self.result_volume = result_volume


class MockClientConfigAdapter:
    def __init__(self):
        self.balance_asset_limit = {}


def main():
    """
    运行测试的主函数
    """
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # 添加文件处理程序
    file_handler = logging.FileHandler("zbit_cross_exchange_mining_test.log")
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logging.getLogger().addHandler(file_handler)
    
    print("正在运行ZBit跨交易所挖矿策略测试，详细日志将保存到zbit_cross_exchange_mining_test.log文件中...")
    
    # 创建并运行测试器
    tester = ZbitCrossExchangeMiningTester()
    asyncio.run(tester.run())
    
    print("测试完成，检查zbit_cross_exchange_mining_test.log文件以获取详细日志。")


if __name__ == "__main__":
    main() 