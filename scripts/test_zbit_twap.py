import asyncio
import logging
from decimal import Decimal
from typing import List
import os

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
from hummingbot.strategy.twap.zbit_twap import ZbitTwapTradeStrategy

# 设置日志格式，输出到文件
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "test_zbit_twap.log")

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

# 设置其他模块的日志级别
logging.getLogger("hummingbot").setLevel(logging.DEBUG)
logging.getLogger("hummingbot.strategy.twap.zbit_twap").setLevel(logging.DEBUG)
logging.getLogger("hummingbot.core.clock").setLevel(logging.DEBUG)
logging.getLogger("hummingbot.connector.test_support.mock_paper_exchange").setLevel(logging.DEBUG)

logger.info(f"日志将保存到: {log_file}")

class TestZbitTwapStrategy:
    def __init__(self):
        logger.info("Initializing test environment...")
        self.clock: Clock = Clock(ClockMode.BACKTEST, 1, 0, 0)
        self.market: MockPaperExchange = MockPaperExchange(
            client_config_map=ClientConfigAdapter(ClientConfigMap())
        )
        self.mid_price = 100
        self.order_delay_time = 15
        self.cancel_order_wait_time = 45
        logger.info(f"Setting up market with mid price: {self.mid_price}")
        self.market.set_balanced_order_book(trading_pair="BTC-USDT",
                                          mid_price=self.mid_price,
                                          min_price=1,
                                          max_price=200,
                                          price_step_size=1,
                                          volume_step_size=10)
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

        # 创建策略实例
        logger.info("Creating ZbitTwapTradeStrategy instance...")
        self.strategy: ZbitTwapTradeStrategy = ZbitTwapTradeStrategy(
            market_infos=[self.market_info],
            is_buy=True,
            target_asset_amount=Decimal("2.0"),
            order_step_size=Decimal("1.0"),
            order_price=Decimal("99"),
            order_delay_time=self.order_delay_time,
            cancel_order_wait_time=self.cancel_order_wait_time
        )
        logger.info("Strategy instance created successfully")

    async def run_test(self):
        try:
            # 添加策略到时钟
            logger.info("Adding strategy to clock...")
            self.clock.add_iterator(self.strategy)
            
            # 启动策略
            logger.info("Starting strategy...")
            self.strategy.start(self.clock, 0)
            
            # 运行时钟
            logger.info(f"Running clock for {self.order_delay_time + 1} seconds...")
            self.clock.backtest_til(self.order_delay_time + 1)
            
            # 检查是否创建了订单
            active_orders = self.strategy.active_bids
            logger.info(f"Active orders after first delay: {active_orders}")
            
            if len(active_orders) > 0:
                # 模拟订单成交
                order = active_orders[0][1]
                logger.info(f"Simulating order fill: {order}")
                self.simulate_limit_order_fill(self.market, order)
                
                # 继续运行时钟
                logger.info(f"Running clock for additional {self.order_delay_time} seconds...")
                self.clock.backtest_til(self.order_delay_time * 2 + 1)
                
                # 检查是否创建了新的订单
                active_orders = self.strategy.active_bids
                logger.info(f"Active orders after fill: {active_orders}")
            else:
                logger.error("No orders were created")
        except Exception as e:
            logger.error(f"Error during test execution: {str(e)}", exc_info=True)

    @staticmethod
    def simulate_limit_order_fill(market: MockPaperExchange, limit_order: LimitOrder):
        logger.info(f"Simulating fill for order: {limit_order}")
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
        test = TestZbitTwapStrategy()
        await test.run_test()
        logger.info("Test completed successfully")
    except Exception as e:
        logger.error(f"Test failed: {str(e)}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main()) 