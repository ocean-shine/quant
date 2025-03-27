import asyncio
import logging
import os
from decimal import Decimal
from typing import List

from hummingbot.client.config.client_config_map import ClientConfigMap
from hummingbot.client.config.config_helpers import ClientConfigAdapter
from hummingbot.connector.exchange.paper_trade.paper_trade_exchange import QuantizationParams
from hummingbot.connector.test_support.mock_paper_exchange import MockPaperExchange
from hummingbot.core.clock import Clock, ClockMode
from hummingbot.core.data_type.common import OrderType, TradeType
from hummingbot.core.data_type.limit_order import LimitOrder
from hummingbot.core.data_type.trade_fee import AddedToCostTradeFee
from hummingbot.core.event.event_logger import EventLogger
from hummingbot.core.event.events import (
    BuyOrderCompletedEvent,
    MarketEvent,
    MarketOrderFailureEvent,
    OrderCancelledEvent,
    OrderExpiredEvent,
    OrderFilledEvent,
    SellOrderCompletedEvent,
)
from hummingbot.strategy.market_trading_pair_tuple import MarketTradingPairTuple
from hummingbot.strategy.pure_market_making import PureMarketMakingStrategy

# 设置日志格式，输出到文件
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "test_zbit_pure_market_making.log")

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, mode='w'),  # 输出到文件
        logging.StreamHandler()  # 同时输出到控制台
    ],
    force=True
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# 设置其他模块的日志级别
logging.getLogger("hummingbot").setLevel(logging.DEBUG)
logging.getLogger("hummingbot.strategy.pure_market_making").setLevel(logging.DEBUG)
logging.getLogger("hummingbot.core.clock").setLevel(logging.DEBUG)
logging.getLogger("hummingbot.connector.test_support.mock_paper_exchange").setLevel(logging.DEBUG)

logger.info(f"日志将保存到: {log_file}")

class TestZbitPureMarketMaking:
    def __init__(self):
        self.clock: Clock = Clock(ClockMode.BACKTEST, 1, 0, 0)
        self.market: MockPaperExchange = MockPaperExchange(
            client_config_map=ClientConfigAdapter(ClientConfigMap())
        )
        self.mid_price = 100
        self.bid_spread = Decimal("0.01")  # 1%
        self.ask_spread = Decimal("0.01")  # 1%
        self.order_amount = Decimal("1.0")
        self.order_refresh_time = 15
        self.cancel_order_wait_time = 45
        
        logger.info(f"Setting up market with mid price: {self.mid_price}")
        self.market.set_balanced_order_book(
            trading_pair="BTC-USDT",
            mid_price=self.mid_price,
            min_price=1,
            max_price=200,
            price_step_size=1,
            volume_step_size=10
        )
        
        self.market.set_balance("BTC", 500)
        self.market.set_balance("USDT", 50000)
        logger.info("Market balances set: BTC=500, USDT=50000")
        
        self.market.set_quantization_param(
            QuantizationParams(
                "BTC-USDT", 6, 6, 6, 6
            )
        )

        self.market_info: MarketTradingPairTuple = MarketTradingPairTuple(
            self.market, "BTC-USDT", "BTC", "USDT"
        )
        
        self.event_logger = EventLogger()
        self.market.add_listener(MarketEvent.OrderFilled, self.event_logger)
        self.market.add_listener(MarketEvent.BuyOrderCompleted, self.event_logger)
        self.market.add_listener(MarketEvent.SellOrderCompleted, self.event_logger)
        
        # 创建策略实例
        logger.info("Creating PureMarketMakingStrategy instance...")
        self.strategy: PureMarketMakingStrategy = PureMarketMakingStrategy()
        self.strategy.init_params(
            market_info=self.market_info,
            bid_spread=self.bid_spread,
            ask_spread=self.ask_spread,
            order_amount=self.order_amount,
            order_refresh_time=self.order_refresh_time,
            max_order_age=self.cancel_order_wait_time,
            order_levels=1,
            hb_app_notification=False,
            order_optimization_enabled=False
        )
        logger.info("Strategy instance created successfully")

    async def run_test(self):
        try:
            # 添加策略到时钟
            logger.info("Adding strategy to clock...")
            self.clock.add_iterator(self.strategy)
            
            # 启动策略
            logger.info("Starting strategy...")
            self.strategy.start(self.clock)
            
            # 运行时钟，让策略下单
            logger.info("Running clock to place orders...")
            # 只运行1秒，让策略有机会下单但不会刷新订单
            self.clock.backtest_til(1)
            
            # 在刷新前检查是否创建了订单
            active_buys = self.strategy.active_buys
            active_sells = self.strategy.active_sells
            logger.info(f"Active buys after initial placement: {active_buys}")
            logger.info(f"Active sells after initial placement: {active_sells}")
            
            if len(active_buys) > 0 and len(active_sells) > 0:
                # 模拟买单成交
                buy_order = active_buys[0]
                logger.info(f"Simulating buy order fill: {buy_order}")
                self.simulate_limit_order_fill(self.market, buy_order)
                
                # 继续运行时钟一小段时间，让策略响应订单成交
                logger.info("Running clock after buy order filled...")
                self.clock.backtest_til(5)
                
                # 模拟卖单成交
                active_sells = self.strategy.active_sells
                if len(active_sells) > 0:
                    sell_order = active_sells[0]
                    logger.info(f"Simulating sell order fill: {sell_order}")
                    self.simulate_limit_order_fill(self.market, sell_order)
                    
                    # 继续运行时钟一小段时间，让策略响应订单成交
                    logger.info("Running clock after sell order filled...")
                    self.clock.backtest_til(10)
                
                # 检查是否创建了新的订单
                active_buys = self.strategy.active_buys
                active_sells = self.strategy.active_sells
                logger.info(f"Active buys after orders filled: {active_buys}")
                logger.info(f"Active sells after orders filled: {active_sells}")
            else:
                logger.error("No orders were created")
                
            # 检查事件
            buy_events = list(filter(
                lambda e: isinstance(e, OrderFilledEvent) and e.trading_pair == "BTC-USDT" or 
                          isinstance(e, BuyOrderCompletedEvent) and e.base_asset == "BTC" and e.quote_asset == "USDT",
                self.event_logger.event_log
            ))
            sell_events = list(filter(
                lambda e: isinstance(e, OrderFilledEvent) and e.trading_pair == "BTC-USDT" or 
                          isinstance(e, SellOrderCompletedEvent) and e.base_asset == "BTC" and e.quote_asset == "USDT",
                self.event_logger.event_log
            ))
            
            logger.info(f"Buy events: {len(buy_events)}")
            logger.info(f"Sell events: {len(sell_events)}")
            
            # 验证测试结果
            has_buy_filled = any(isinstance(e, BuyOrderCompletedEvent) for e in buy_events)
            has_sell_filled = any(isinstance(e, SellOrderCompletedEvent) for e in sell_events)
            
            if has_buy_filled:
                logger.info("Buy order was successfully filled.")
            else:
                logger.error("Buy order was not filled.")
                
            if has_sell_filled:
                logger.info("Sell order was successfully filled.")
            else:
                logger.error("Sell order was not filled.")
                
        except Exception as e:
            logger.error(f"Error during test execution: {str(e)}", exc_info=True)

    @staticmethod
    def simulate_limit_order_fill(market: MockPaperExchange, limit_order: LimitOrder):
        quote_currency_traded: Decimal = limit_order.price * limit_order.quantity
        base_currency_traded: Decimal = limit_order.quantity
        quote_currency: str = limit_order.quote_currency
        base_currency: str = limit_order.base_currency

        if limit_order.is_buy:
            market.set_balance(quote_currency, market.get_balance(quote_currency) - quote_currency_traded)
            market.set_balance(base_currency, market.get_balance(base_currency) + base_currency_traded)
            logger.info(f"Updated balances after buy: {base_currency}={market.get_balance(base_currency)}, {quote_currency}={market.get_balance(quote_currency)}")
            market.trigger_event(MarketEvent.OrderFilled, OrderFilledEvent(
                market.current_timestamp,
                limit_order.client_order_id,
                limit_order.trading_pair,
                TradeType.BUY,
                OrderType.LIMIT,
                limit_order.price,
                limit_order.quantity,
                AddedToCostTradeFee(Decimal("0"))
            ))
            market.trigger_event(MarketEvent.BuyOrderCompleted, BuyOrderCompletedEvent(
                market.current_timestamp,
                limit_order.client_order_id,
                base_currency,
                quote_currency,
                base_currency_traded,
                quote_currency_traded,
                OrderType.LIMIT
            ))
        else:
            market.set_balance(quote_currency, market.get_balance(quote_currency) + quote_currency_traded)
            market.set_balance(base_currency, market.get_balance(base_currency) - base_currency_traded)
            logger.info(f"Updated balances after sell: {base_currency}={market.get_balance(base_currency)}, {quote_currency}={market.get_balance(quote_currency)}")
            market.trigger_event(MarketEvent.OrderFilled, OrderFilledEvent(
                market.current_timestamp,
                limit_order.client_order_id,
                limit_order.trading_pair,
                TradeType.SELL,
                OrderType.LIMIT,
                limit_order.price,
                limit_order.quantity,
                AddedToCostTradeFee(Decimal("0"))
            ))
            market.trigger_event(MarketEvent.SellOrderCompleted, SellOrderCompletedEvent(
                market.current_timestamp,
                limit_order.client_order_id,
                base_currency,
                quote_currency,
                base_currency_traded,
                quote_currency_traded,
                OrderType.LIMIT
            ))

async def main():
    try:
        logger.info("Starting test...")
        test = TestZbitPureMarketMaking()
        await test.run_test()
        logger.info("Test completed successfully")
    except Exception as e:
        logger.error(f"Test failed: {str(e)}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main()) 