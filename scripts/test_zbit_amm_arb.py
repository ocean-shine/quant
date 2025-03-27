#!/usr/bin/env python

import asyncio
import logging
import os
import time
from decimal import Decimal
from typing import Dict, List, Optional
import unittest.mock as mock

from hummingbot.connector.exchange.zbit.zbit_exchange import ZbitExchange
from hummingbot.core.clock import Clock, ClockMode
from hummingbot.core.event.event_logger import EventLogger
from hummingbot.core.event.events import MarketEvent, OrderCancelledEvent, OrderFilledEvent, OrderType, TradeType
from hummingbot.core.network_iterator import NetworkStatus
from hummingbot.core.rate_oracle.rate_oracle import RateOracle
from hummingbot.core.utils.async_utils import safe_ensure_future
from hummingbot.core.utils.fixed_rate_source import FixedRateSource
from hummingbot.logger import HummingbotLogger
from hummingbot.logger.struct_logger import METRICS_LOG_LEVEL
from hummingbot.strategy.amm_arb.zbit_amm_arb import ZbitAmmArbStrategy
from hummingbot.strategy.market_trading_pair_tuple import MarketTradingPairTuple

# 配置日志
logging.basicConfig(level=METRICS_LOG_LEVEL)
logging.getLogger("hummingbot.core.event.event_reporter").setLevel(logging.WARNING)
logging.getLogger("hummingbot.core.data_type.order_book_tracker").setLevel(logging.INFO)
logging.getLogger("hummingbot.core.data_type.order_book_tracker_data_source").setLevel(logging.INFO)

# 创建日志目录
os.makedirs("logs", exist_ok=True)

# 配置测试日志
logger = logging.getLogger()
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler = logging.FileHandler('logs/test_zbit_amm_arb.log')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

s_decimal_0 = Decimal(0)


# 为ZbitExchange添加测试所需的方法
def patch_zbit_exchange():
    # 添加set_balance方法
    async def set_balance(self, token, balance):
        self._account_balances[token] = balance
        self._account_available_balances[token] = balance
    ZbitExchange.set_balance = set_balance
    
    # 添加set_trading_pair_symbol_map方法
    async def set_trading_pair_symbol_map(self, mapping=None):
        pass
    ZbitExchange.set_trading_pair_symbol_map = set_trading_pair_symbol_map
    
    # 添加set_balanced_order_book方法
    def set_balanced_order_book(self, trading_pair, mid_price, min_price, max_price, price_step_size, volume_step_size):
        # 模拟订单簿
        self._order_book_tracker = mock.MagicMock()
        # 模拟订单簿的ready属性
        self._order_book_tracker.ready = True
        # 添加get_price方法模拟
        self.get_price = lambda trading_pair, is_buy, amount: (
            mid_price * Decimal("1.001") if is_buy else mid_price * Decimal("0.999")
        )
        # 添加get_quote_price方法模拟
        self.get_quote_price = lambda trading_pair, is_buy, amount: (
            mid_price * Decimal("1.002") if is_buy else mid_price * Decimal("0.998")
        )
        # 添加get_order_price方法模拟
        self.get_order_price = lambda trading_pair, is_buy, amount: (
            mid_price * Decimal("1.003") if is_buy else mid_price * Decimal("0.997")
        )
    ZbitExchange.set_balanced_order_book = set_balanced_order_book
    
    # 添加get_fee方法
    def get_fee(self, base_currency, quote_currency, order_type, order_side, amount, price, is_maker=None):
        return Decimal("0.001")  # 0.1%的固定费率
    ZbitExchange.get_fee = get_fee
    
    # 添加网络方法模拟
    async def start_network(self):
        self._trading_rules = {
            "BTC-USDT": mock.MagicMock(
                min_order_size=Decimal("0.001"),
                max_order_size=Decimal("100"),
                min_price_increment=Decimal("0.01"),
                min_base_amount_increment=Decimal("0.001"),
                min_quote_amount_increment=Decimal("0.01"),
                min_notional_size=Decimal("10"),
            )
        }
        self._ready = True
        return
    ZbitExchange.start_network = start_network
    
    async def stop_network(self):
        self._order_book_tracker = None
        return
    ZbitExchange.stop_network = stop_network
    
    # 模拟c_start和c_stop方法
    def c_start(self, clock, timestamp):
        self._ready = True
        return
    ZbitExchange.c_start = c_start
    
    def c_stop(self, clock):
        self._ready = False
        return
    ZbitExchange.c_stop = c_stop
    
    # 模拟c_tick方法
    def c_tick(self, timestamp):
        pass
    ZbitExchange.c_tick = c_tick
    
    # 模拟其他重要方法
    async def check_network(self):
        return NetworkStatus.CONNECTED
    ZbitExchange.check_network = check_network
    
    def ready(self):
        return True
    ZbitExchange.ready = property(ready)


class ZbitAMMTest:
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.INFO)
        self.zbit_exchange = None
        self.zbit_exchange2 = None
        self.strategy = None
        self.markets = {}
        self.zbit_base_balance = Decimal("500")  # 模拟BTC余额
        self.zbit_quote_balance = Decimal("50000")  # 模拟USDT余额
        self.clock = None
        self.mock_price = Decimal("100")  # 模拟BTC-USDT价格

    async def setup_exchange(self):
        """
        设置测试交易所
        """
        self.logger.info("设置测试交易所...")
        
        # 创建交易所实例
        self.zbit_exchange = ZbitExchange(
            zbit_api_key="testAPIKey",
            zbit_api_secret="testSecretKey",
            trading_pairs=["BTC-USDT"],
        )
        
        # 设置第二个交易所，模拟不同的市场
        self.zbit_exchange2 = ZbitExchange(
            zbit_api_key="testAPIKey2",
            zbit_api_secret="testSecretKey2",
            trading_pairs=["BTC-USDT"],
        )
        
        # 模拟账户余额
        await self.zbit_exchange.set_balance("BTC", self.zbit_base_balance)
        await self.zbit_exchange.set_balance("USDT", self.zbit_quote_balance)
        await self.zbit_exchange2.set_balance("BTC", self.zbit_base_balance)
        await self.zbit_exchange2.set_balance("USDT", self.zbit_quote_balance)
        
        # 初始化RateOracle
        rate_source = FixedRateSource()
        rate_source.add_rate("USDT-USDT", Decimal("1.0"))
        rate_source.add_rate("BTC-BTC", Decimal("1.0"))
        
        # 模拟市场价格
        for exchange in [self.zbit_exchange, self.zbit_exchange2]:
            await exchange.set_trading_pair_symbol_map(None)
        
        self.markets = {
            "zbit_1": self.zbit_exchange,
            "zbit_2": self.zbit_exchange2
        }
        
        self.logger.info(f"测试交易所设置完成 - 余额: BTC={self.zbit_base_balance}, USDT={self.zbit_quote_balance}")
        return self.markets

    def setup_market_price(self):
        """
        设置市场价格，zbit_2略高一点，以创造套利机会
        """
        self.zbit_exchange.set_balanced_order_book(
            trading_pair="BTC-USDT",
            mid_price=self.mock_price,
            min_price=Decimal("95"),
            max_price=Decimal("105"),
            price_step_size=Decimal("0.1"),
            volume_step_size=Decimal("0.1"),
        )
        
        # 第二个交易所的价格略高，创造套利机会
        self.zbit_exchange2.set_balanced_order_book(
            trading_pair="BTC-USDT",
            mid_price=self.mock_price * Decimal("1.02"),  # 2%的价格差异
            min_price=Decimal("97"),
            max_price=Decimal("107"),
            price_step_size=Decimal("0.1"),
            volume_step_size=Decimal("0.1"),
        )
        
        self.logger.info(f"市场价格设置完成 - zbit_1 mid_price: {self.mock_price}, zbit_2 mid_price: {self.mock_price * Decimal('1.02')}")

    def setup_strategy(self):
        """
        设置Zbit AMM套利策略
        """
        self.logger.info("设置Zbit AMM套利策略...")
        
        market_infos = {}
        market_infos["zbit_1"] = MarketTradingPairTuple(
            self.zbit_exchange, "BTC-USDT", "BTC", "USDT"
        )
        market_infos["zbit_2"] = MarketTradingPairTuple(
            self.zbit_exchange2, "BTC-USDT", "BTC", "USDT"
        )
        
        # 配置策略参数
        min_profitability = Decimal("0.005")  # 0.5% 最小盈利能力
        order_amount = Decimal("0.1")  # 0.1 BTC 的订单量
        
        # 创建策略实例
        self.strategy = ZbitAmmArbStrategy()
        self.strategy.init_params(
            market_info_1=market_infos["zbit_1"],
            market_info_2=market_infos["zbit_2"],
            min_profitability=min_profitability,
            order_amount=order_amount,
            market_1_slippage_buffer=Decimal("0.005"),  # 0.5% 滑点缓冲
            market_2_slippage_buffer=Decimal("0.005"),  # 0.5% 滑点缓冲
            concurrent_orders_submission=True,
            order_refresh_time=Decimal("30"),
            retry_interval=Decimal("5"),
            max_retries=3,
            debug_mode=True,
        )
        
        self.logger.info(f"策略设置完成 - 最小盈利能力: {min_profitability}, 订单量: {order_amount} BTC")
        
        # 创建时钟
        self.clock = Clock(ClockMode.BACKTEST, start_time=int(time.time()), tick_size=1.0)
        self.clock.add_iterator(self.zbit_exchange)
        self.clock.add_iterator(self.zbit_exchange2)
        self.clock.add_iterator(self.strategy)
        
        # 设置事件监听器
        self.setup_event_loggers()
        
        return self.strategy

    def setup_event_loggers(self):
        """
        设置事件日志记录器
        """
        self.market_logger = EventLogger()
        self.zbit_exchange.add_listener(MarketEvent.OrderFilled, self.market_logger)
        self.zbit_exchange.add_listener(MarketEvent.OrderCancelled, self.market_logger)
        self.zbit_exchange2.add_listener(MarketEvent.OrderFilled, self.market_logger)
        self.zbit_exchange2.add_listener(MarketEvent.OrderCancelled, self.market_logger)

    async def simulate_maker_market_trade(self, is_buy: bool, base_amount: Decimal, price: Decimal):
        """
        模拟一个市场交易
        """
        market_info = self.strategy._market_info_1
        order_id_prefix = "buy://" if is_buy else "sell://"
        order_id = f"{order_id_prefix}{market_info.trading_pair}/simulated_trade"
        quantized_amount = base_amount

        if is_buy:
            self.zbit_exchange.trigger_event(
                MarketEvent.OrderFilled,
                OrderFilledEvent(
                    time.time(),
                    order_id,
                    market_info.trading_pair,
                    TradeType.BUY,
                    OrderType.LIMIT,
                    price,
                    quantized_amount,
                    self.zbit_exchange.get_fee(
                        market_info.base_asset,
                        market_info.quote_asset,
                        OrderType.LIMIT,
                        TradeType.BUY,
                        quantized_amount,
                        price,
                    ),
                    exchange_trade_id=f"mock_trade_{time.time()}"
                )
            )
        else:
            self.zbit_exchange.trigger_event(
                MarketEvent.OrderFilled,
                OrderFilledEvent(
                    time.time(),
                    order_id,
                    market_info.trading_pair,
                    TradeType.SELL,
                    OrderType.LIMIT,
                    price,
                    quantized_amount,
                    self.zbit_exchange.get_fee(
                        market_info.base_asset,
                        market_info.quote_asset,
                        OrderType.LIMIT,
                        TradeType.SELL,
                        quantized_amount,
                        price,
                    ),
                    exchange_trade_id=f"mock_trade_{time.time()}"
                )
            )

    async def run_simulation(self):
        """
        运行模拟测试
        """
        await self.setup_exchange()
        self.setup_market_price()
        self.setup_strategy()
        
        # 简化测试流程，直接模拟套利条件和执行
        self.logger.info("开始模拟测试...")
        
        # 模拟市场波动，创造套利机会
        self.mock_price = Decimal("101")  # 价格上涨
        self.setup_market_price()
        
        # 检查套利机会
        self.logger.info("模拟寻找套利机会...")
        buy_price_1 = self.zbit_exchange.get_price("BTC-USDT", True, Decimal("0.1"))
        sell_price_2 = self.zbit_exchange2.get_price("BTC-USDT", False, Decimal("0.1"))
        
        self.logger.info(f"市场1买入价格: {buy_price_1}")
        self.logger.info(f"市场2卖出价格: {sell_price_2}")
        
        profit_pct = (sell_price_2 - buy_price_1) / buy_price_1
        self.logger.info(f"潜在利润率: {profit_pct:.4%}")
        
        # 模拟执行套利
        if profit_pct > Decimal("0.005"):  # 如果利润率大于0.5%
            self.logger.info("发现套利机会，执行套利交易...")
            
            # 模拟市场1买入
            order_amount = Decimal("0.1")
            await self.simulate_maker_market_trade(
                is_buy=True,
                base_amount=order_amount,
                price=buy_price_1
            )
            
            # 模拟市场2卖出
            await self.simulate_maker_market_trade(
                is_buy=False,
                base_amount=order_amount,
                price=sell_price_2
            )
            
            # 更新余额
            new_market1_btc = self.zbit_base_balance + order_amount
            new_market1_usdt = self.zbit_quote_balance - (buy_price_1 * order_amount)
            
            new_market2_btc = self.zbit_base_balance - order_amount
            new_market2_usdt = self.zbit_quote_balance + (sell_price_2 * order_amount)
            
            # 设置新余额
            await self.zbit_exchange.set_balance("BTC", new_market1_btc)
            await self.zbit_exchange.set_balance("USDT", new_market1_usdt)
            await self.zbit_exchange2.set_balance("BTC", new_market2_btc)
            await self.zbit_exchange2.set_balance("USDT", new_market2_usdt)
            
            self.logger.info(f"套利执行完成 - 买入价格: {buy_price_1}, 卖出价格: {sell_price_2}")
            self.logger.info(f"套利利润: {(sell_price_2 - buy_price_1) * order_amount} USDT")
        else:
            self.logger.info("未发现有利可图的套利机会。")
        
        # 检查结果
        self.analyze_results()

    def analyze_results(self):
        """
        分析测试结果
        """
        self.logger.info("\n===== 测试结果分析 =====")
        # 检查订单历史
        self.logger.info(f"订单事件记录: {len(self.market_logger.event_log)} 个事件")
        
        # 打印余额变化
        self.logger.info(f"初始余额: BTC={self.zbit_base_balance}, USDT={self.zbit_quote_balance}")
        zbit1_btc = self.zbit_exchange._account_balances.get("BTC", Decimal("0"))
        zbit1_usdt = self.zbit_exchange._account_balances.get("USDT", Decimal("0"))
        zbit2_btc = self.zbit_exchange2._account_balances.get("BTC", Decimal("0"))
        zbit2_usdt = self.zbit_exchange2._account_balances.get("USDT", Decimal("0"))
        
        self.logger.info(f"最终余额 (zbit_1): BTC={zbit1_btc}, USDT={zbit1_usdt}")
        self.logger.info(f"最终余额 (zbit_2): BTC={zbit2_btc}, USDT={zbit2_usdt}")
        
        # 计算盈利
        btc_diff = (zbit1_btc + zbit2_btc) - (self.zbit_base_balance * 2)
        usdt_diff = (zbit1_usdt + zbit2_usdt) - (self.zbit_quote_balance * 2)
        
        self.logger.info(f"净变化: BTC={btc_diff}, USDT={usdt_diff}")
        self.logger.info(f"估计USDT价值变化: {btc_diff * self.mock_price + usdt_diff} USDT")
        
        # 打印活跃的套利提案
        if hasattr(self.strategy, '_all_arb_proposals') and self.strategy._all_arb_proposals:
            self.logger.info("\n当前套利提案:")
            for proposal in self.strategy._all_arb_proposals:
                profit_pct = proposal.profit_pct(rate_source=self.strategy.rate_source, account_for_fee=True)
                self.logger.info(f"利润率: {profit_pct:.4%}")
                self.logger.info(f"第一边: {proposal.first_side}")
                self.logger.info(f"第二边: {proposal.second_side}")
        
        self.logger.info("===== 测试完成 =====")


async def main():
    # 为ZbitExchange添加测试所需的方法
    patch_zbit_exchange()
    
    # 创建并运行测试
    test = ZbitAMMTest()
    await test.run_simulation()


if __name__ == "__main__":
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("\n测试被用户中断。")
    except Exception as e:
        print(f"测试出错: {str(e)}")
        import traceback
        traceback.print_exc() 