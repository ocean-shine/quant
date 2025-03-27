#!/usr/bin/env python

import asyncio
import logging
import time
import os
from decimal import Decimal
from typing import Dict, List

# 添加当前目录到路径
import sys
# 确保父目录在路径中，这样可以导入hummingbot
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from hummingbot.core.clock import Clock, ClockMode
from hummingbot.logger import HummingbotLogger
from hummingbot.core.event.event_logger import EventLogger
from hummingbot.core.event.events import MarketEvent, OrderBookEvent, OrderBookTradeEvent, TradeType
from hummingbot.connector.exchange.zbit.zbit_exchange import ZbitExchange
from hummingbot.strategy.market_trading_pair_tuple import MarketTradingPairTuple

# 添加当前目录到路径
sys.path.append(os.path.dirname(os.path.realpath(__file__)))
from zbit_cross_exchange_market_making import ZbitCrossExchangeMarketMaking
from zbit_cross_exchange_market_making_config import get_zbit_cross_exchange_config


class MockClientConfigAdapter:
    def __init__(self):
        self.balance_asset_limit = {}


class ZbitCrossExchangeMarketMakingTester:
    """
    ZBit跨交易所做市策略的测试工具
    """
    
    # 默认API密钥（测试用）
    DEFAULT_ZBIT_API_KEY = "vmPUZE6mv9SD5V5e14y7Ju91duEh8A"
    DEFAULT_ZBIT_API_SECRET = "902ae3cb34ecee2779aa4d3e1d226686"
    
    @classmethod
    def logger(cls) -> HummingbotLogger:
        return logging.getLogger(__name__)
    
    def __init__(self):
        # 初始化测试器属性
        self._clock: Clock = None
        self._strategy: ZbitCrossExchangeMarketMaking = None
        self._maker_market: ZbitExchange = None
        self._taker_market: ZbitExchange = None  # 使用ZbitExchange作为对手方
        self._config = get_zbit_cross_exchange_config()
        self._maker_trading_pair = self._config["maker_market_trading_pair"]
        self._taker_trading_pair = self._config["taker_market_trading_pair"]
        self._maker_market_info = None
        self._taker_market_info = None
        self._market_events_logger = None
    
    async def run_clock(self):
        """
        运行时钟一段固定时间
        """
        self.logger().info("运行ZBit跨交易所做市策略测试...")
        
        # 直接输出策略初始状态
        if self._strategy is not None:
            self.logger().info("\n策略初始状态:")
            self.logger().info(self._strategy.format_status())
        
        # 每秒手动调用策略的tick方法
        start_time = time.time()
        run_time = 1  # 只运行1秒以便快速查看结果
        
        iteration = 0
        while time.time() - start_time < run_time:
            # 设置当前时间戳
            current_time = time.time()
            self._maker_market._set_current_timestamp(int(current_time))
            self._taker_market._set_current_timestamp(int(current_time))
            
            # 手动调用策略的tick方法
            self._strategy.tick(current_time)
            
            # 每次迭代后输出状态
            self.logger().info(f"\n迭代 {iteration} 后的状态:")
            self.logger().info(self._strategy.format_status())
            
            # 直接输出当前的活跃订单
            self.logger().info(f"活跃买单数量: {len(self._strategy._active_bids)}")
            self.logger().info(f"活跃卖单数量: {len(self._strategy._active_asks)}")
            
            if self._strategy._active_bids:
                self.logger().info(f"买单示例: {self._strategy._active_bids[0].client_order_id}, 价格: {self._strategy._active_bids[0].price}, 数量: {self._strategy._active_bids[0].quantity}")
                
            if self._strategy._active_asks:
                self.logger().info(f"卖单示例: {self._strategy._active_asks[0].client_order_id}, 价格: {self._strategy._active_asks[0].price}, 数量: {self._strategy._active_asks[0].quantity}")
            
            iteration += 1
            
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
            self._taker_market = await self.setup_zbit_exchange(is_maker=False)  # 使用ZBit作为对手方
            
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
            
            # 创建市场信息和策略
            maker_base, maker_quote = self._maker_trading_pair.split("-")
            taker_base, taker_quote = self._taker_trading_pair.split("-")
            
            self._maker_market_info = MarketTradingPairTuple(
                self._maker_market, 
                self._maker_trading_pair, 
                maker_base, 
                maker_quote
            )
            
            self._taker_market_info = MarketTradingPairTuple(
                self._taker_market, 
                self._taker_trading_pair, 
                taker_base, 
                taker_quote
            )

            # 设置模拟价格
            # 为做市商和对手方市场设置不同的价格，创造套利机会
            base_price = 50000.0  # 基础价格
            
            # 在Hummingbot中，get_price的is_buy参数指的是：
            # True代表获取ask价格（卖单最低价）
            # False代表获取bid价格（买单最高价）
            def get_taker_price(trading_pair, is_buy):
                if is_buy:  # 对手方市场的ask价格
                    return Decimal(str(base_price * 0.98))  # 比做市商的ask价格低2%，在对手方便宜买入
                else:  # 对手方市场的bid价格
                    return Decimal(str(base_price * 1.02))  # 比做市商的bid价格高2%，可以贵卖给对手方
                    
            def get_maker_price(trading_pair, is_buy):
                if is_buy:  # 做市商的ask价格
                    return Decimal(str(base_price * 1.00))  # 基准价格
                else:  # 做市商的bid价格
                    return Decimal(str(base_price * 1.00))  # 基准价格
            
            # 替换get_price方法
            self._taker_market.get_price = get_taker_price
            self._maker_market.get_price = get_maker_price
            
            # 模拟手续费计算方法
            from hummingbot.core.data_type.trade_fee import AddedToCostTradeFee
            def get_fee(self, trading_pair, order_type, order_side, amount, price, is_maker=None):
                return AddedToCostTradeFee(percent=Decimal("0.001"))  # 0.1%的手续费
                
            # 替换get_fee方法
            self._maker_market.get_fee = get_fee.__get__(self._maker_market)
            self._taker_market.get_fee = get_fee.__get__(self._taker_market)
            
            # 输出模拟价格，验证套利机会
            maker_bid = self._maker_market.get_price(self._maker_trading_pair, False)
            maker_ask = self._maker_market.get_price(self._maker_trading_pair, True)
            taker_bid = self._taker_market.get_price(self._taker_trading_pair, False)
            taker_ask = self._taker_market.get_price(self._taker_trading_pair, True)
            
            self.logger().info(f"初始价格配置:")
            self.logger().info(f"  做市商价格: 买入(bid)={maker_bid:.2f}, 卖出(ask)={maker_ask:.2f}")
            self.logger().info(f"  对手方价格: 买入(bid)={taker_bid:.2f}, 卖出(ask)={taker_ask:.2f}")
            self.logger().info(f"  买入套利机会: {((taker_bid - maker_ask) / maker_ask):.2%}")
            self.logger().info(f"  卖出套利机会: {((maker_bid - taker_ask) / taker_ask):.2%}")
            
            # 手动打印检查市场就绪状态
            self.logger().info("初始市场状态检查:")
            self.logger().info(f"  做市商就绪: {self._maker_market.ready}")
            self.logger().info(f"  对手方就绪: {self._taker_market.ready}")
            if hasattr(self._maker_market, "status_dict"):
                self.logger().info(f"  做市商状态字典: {self._maker_market.status_dict}")
            if hasattr(self._taker_market, "status_dict"):
                self.logger().info(f"  对手方状态字典: {self._taker_market.status_dict}")
            
            self.logger().info("等待策略启动...")
            
            # 初始化策略
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
    
    def create_strategy(self) -> ZbitCrossExchangeMarketMaking:
        """
        创建策略实例
        """
        config = self._config
        
        # 创建策略实例
        strategy = ZbitCrossExchangeMarketMaking(
            maker_market=self._maker_market,
            taker_market=self._taker_market,
            maker_market_trading_pair=self._maker_trading_pair,
            taker_market_trading_pair=self._taker_trading_pair,
            min_profitability=config["min_profitability"],
            order_amount=config["order_amount"],
            adjust_order_enabled=True,
            active_order_canceling=config["active_order_canceling"],
            min_order_amount=config["min_order_amount"],
            limit_order_min_expiration=130.0,
            cancel_order_threshold=config["cancel_order_threshold"],
            top_depth_tolerance=config["top_depth_tolerance"],
            anti_hysteresis_duration=config["anti_hysteresis_duration"],
            order_refresh_time=config["order_refresh_time"],
            order_refresh_tolerance_pct=config["order_refresh_tolerance_pct"],
            filled_order_delay=config["filled_order_delay"],
            order_optimization_enabled=config["order_optimization_enabled"],
            ask_order_optimization_depth=config["ask_order_optimization_depth"],
            bid_order_optimization_depth=config["bid_order_optimization_depth"],
            add_transaction_costs_to_orders=config["add_transaction_costs_to_orders"],
            logging_options=0xFF,
            status_report_interval=900,
            taker_to_maker_base_conversion_rate=config["taker_to_maker_base_conversion_rate"],
            taker_to_maker_quote_conversion_rate=config["taker_to_maker_quote_conversion_rate"],
            slippage_buffer=config["slippage_buffer"]
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
            
        # 将方法绑定到market对象
        market.get_exchange_limit_config = get_exchange_limit_config.__get__(market)
        market.get_balance = get_balance.__get__(market)
        market.buy = buy.__get__(market)
        market.sell = sell.__get__(market)
        market.cancel = cancel.__get__(market)
        
        # 模拟连接
        try:
            await market._update_balances()
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
            self.logger().info("  ZBit跨交易所做市策略 - 测试结果 ")
            self.logger().info("*" * 50)
            self.logger().info(f"总测试时长: {1} 秒")
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
    file_handler = logging.FileHandler("test_results.log")
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logging.getLogger().addHandler(file_handler)
    
    print("正在运行测试，详细日志将保存到test_results.log文件中...")
    
    # 创建并运行测试器
    tester = ZbitCrossExchangeMarketMakingTester()
    asyncio.run(tester.run())
    
    print("测试完成，检查test_results.log文件以获取详细日志。")


if __name__ == "__main__":
    main() 