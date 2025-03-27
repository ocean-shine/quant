#!/usr/bin/env python

import asyncio
import logging
import time
import os
import sys
from typing import Dict, List
from decimal import Decimal

from hummingbot.core.clock import Clock, ClockMode
from hummingbot.core.utils.async_utils import safe_ensure_future
from hummingbot.logger import HummingbotLogger
from hummingbot.core.data_type.limit_order import LimitOrder
from hummingbot.core.event.event_logger import EventLogger
from hummingbot.core.event.events import (MarketEvent, OrderBookEvent, 
                                         OrderBookTradeEvent, TradeType,
                                         OrderType, MarketOrderFailureEvent)
from hummingbot.core.data_type.order_book_tracker import OrderBookTrackerDataSourceType
from hummingbot.connector.exchange.zbit.zbit_exchange import ZbitExchange
from hummingbot.strategy.market_trading_pair_tuple import MarketTradingPairTuple

# 添加当前目录到路径
sys.path.append(os.path.dirname(os.path.realpath(__file__)))
from zbit_avellaneda_market_making import ZbitAvellanedaMarketMaking
from zbit_avellaneda_market_making_config import get_zbit_avellaneda_config


class ZbitAvellanedaMarketMakingTester:
    """
    Test harness for the Zbit Avellaneda Market Making strategy
    """
    
    # 默认API密钥
    DEFAULT_API_KEY = "vmPUZE6mv9SD5V5e14y7Ju91duEh8A"
    DEFAULT_API_SECRET = "902ae3cb34ecee2779aa4d3e1d226686"
    
    @classmethod
    def logger(cls) -> HummingbotLogger:
        return logging.getLogger(__name__)
    
    def __init__(self):
        self._clock: Clock = None
        self._strategy: ZbitAvellanedaMarketMaking = None
        self._market: ZbitExchange = None
        self._config = get_zbit_avellaneda_config()
        self._trading_pair = self._config["trading_pair"]
        self._market_info = None
        self._market_events_logger = None
        
    async def run_clock(self):
        """
        Run clock for a fixed amount of time
        """
        self.logger().info("Running Zbit Avellaneda Market Making strategy test...")
        await asyncio.sleep(60)  # Let the strategy run for 60 seconds
        
    async def run(self):
        """
        Sets up and runs the test
        """
        try:
            # Set up the market
            self._market = await self.setup_zbit_exchange()
            
            # Setup events logger to capture market events
            self._market_events_logger = EventLogger()
            for event_tag in [MarketEvent.BuyOrderCreated,
                              MarketEvent.SellOrderCreated,
                              MarketEvent.OrderFilled,
                              MarketEvent.OrderCancelled,
                              MarketEvent.BuyOrderCompleted,
                              MarketEvent.SellOrderCompleted,
                              MarketEvent.OrderFailure]:
                self._market.add_listener(event_tag, self._market_events_logger)
            
            # Create market info and strategy
            self._market_info = MarketTradingPairTuple(
                self._market, 
                self._trading_pair, 
                self._config["base_asset"], 
                self._config["quote_asset"]
            )
            
            # For testing only - setup a mock order book
            # This is not needed in production
            self._market._set_current_timestamp(int(time.time()))

            # Initialize the strategy
            self._strategy = self.create_strategy()
            
            # Set up and run the clock
            self._clock = Clock(ClockMode.REALTIME)
            self._clock.add_iterator(self._market)
            self._clock.add_iterator(self._strategy)
            
            self.logger().info("Starting clock...")
            with self._clock:
                await self.run_clock()
            
            # Print test results
            self.print_stats()
            
        except Exception as e:
            self.logger().error(f"Error encountered during testing: {e}", exc_info=True)
        finally:
            # Clean up
            self.logger().info("Cleaning up...")
            await self.cleanup()
            
    def create_strategy(self) -> ZbitAvellanedaMarketMaking:
        """
        Create and configure the strategy
        """
        config = self._config
        
        # Create strategy instance
        strategy = ZbitAvellanedaMarketMaking(
            market_info=self._market_info,
            risk_factor=config["risk_factor"],
            order_amount=config["order_amount"],
            time_horizon=config["time_horizon"],
            min_spread=config["min_spread"],
            max_spread=config["max_spread"],
            inventory_target_base_pct=config["inventory_target_base_pct"],
            vol_to_spread_multiplier=config["vol_to_spread_multiplier"],
            volatility_adjustment=config["volatility_adjustment"],
            order_refresh_time=config["order_refresh_time"],
            order_refresh_tolerance_pct=config["order_refresh_tolerance_pct"],
            order_optimization_enabled=config["order_optimization_enabled"],
            filled_order_delay=config["filled_order_delay"],
            add_transaction_costs=config["add_transaction_costs"],
            hanging_orders_enabled=config["hanging_orders_enabled"],
            hanging_orders_cancel_pct=config["hanging_orders_cancel_pct"],
            order_levels=config["order_levels"],
            order_level_spread=config["order_level_spread"],
            logging_options=config["logging_options"],
            debug_mode=config["debug_mode"],
        )
        
        # Add mock format_status method to avoid NotImplementedError
        strategy.format_status = lambda: "Avellaneda Market Making Strategy (Mock)"
        
        return strategy
    
    async def setup_zbit_exchange(self) -> ZbitExchange:
        """
        Sets up the Zbit exchange connector
        """
        # Get API credentials - 使用默认值或环境变量
        api_key = os.getenv("ZBIT_API_KEY", self.DEFAULT_API_KEY)
        api_secret = os.getenv("ZBIT_API_SECRET", self.DEFAULT_API_SECRET)
        
        self.logger().info(f"Using API key: {api_key[:5]}...{api_key[-5:]} for Zbit exchange")
        
        # 根据错误信息，直接使用预期的参数名称
        # 从错误信息看，需要zbit_api_key和zbit_api_secret参数
        market = ZbitExchange(
            zbit_api_key=api_key,
            zbit_api_secret=api_secret,
            trading_pairs=[self._trading_pair]
        )
        
        # Connect to exchange
        try:
            await market._update_balances()
        except Exception as e:
            self.logger().warning(f"Error updating balances (likely connection error): {e}")
        
        # Start the market and use a wait mechanism that doesn't rely on MarketEvent.Ready
        await market.start_network()
        
        # Instead of waiting for a Ready event, wait for the market's ready property to be True
        # or continue after a timeout
        for _ in range(10):  # Try for up to 10 seconds
            if market.ready:
                break
            await asyncio.sleep(1)
        
        self.logger().info(f"Market {market.name} initialized.")
        return market
    
    async def cleanup(self):
        """
        Clean up all active orders and connections
        """
        if self._market is not None:
            self.logger().info("Canceling all orders...")
            try:
                # Cancel all active orders
                await self._market.cancel_all(timeout_seconds=10)
                
                # Stop the network
                # Remove all event listeners but not MarketEvent.Ready since it doesn't exist
                for event_tag in [MarketEvent.BuyOrderCreated,
                                 MarketEvent.SellOrderCreated,
                                 MarketEvent.OrderFilled,
                                 MarketEvent.OrderCancelled,
                                 MarketEvent.BuyOrderCompleted,
                                 MarketEvent.SellOrderCompleted,
                                 MarketEvent.OrderFailure]:
                    self._market.remove_listener(event_tag, self._market_events_logger)
                
                await self._market.stop_network()
                
            except Exception as e:
                self.logger().error(f"Error in cleanup: {e}", exc_info=True)
    
    def print_stats(self):
        """
        Print test statistics
        """
        if self._market_events_logger is not None:
            # Extract events
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
            
            # Print summary
            self.logger().info("\n" + "*" * 50)
            self.logger().info("  Zbit Avellaneda Market Making - Test Results ")
            self.logger().info("*" * 50)
            self.logger().info(f"Total test duration: {60} seconds")
            self.logger().info(f"Trading pair: {self._trading_pair}")
            self.logger().info(f"Buy orders created: {len(buy_orders_created)}")
            self.logger().info(f"Sell orders created: {len(sell_orders_created)}")
            self.logger().info(f"Orders filled: {len(orders_filled)}")
            self.logger().info(f"Orders cancelled: {len(orders_cancelled)}")
            self.logger().info(f"Orders failed: {len(orders_failed)}")
            
            # Print strategy status
            if self._strategy is not None:
                self.logger().info("\nStrategy Status:")
                self.logger().info(self._strategy.format_status())
            
            self.logger().info("*" * 50 + "\n")
            
            # Print market analysis
            if self._market is not None:
                base_balance = self._market.get_balance(self._config["base_asset"])
                quote_balance = self._market.get_balance(self._config["quote_asset"])
                self.logger().info(f"Final balances: {base_balance} {self._config['base_asset']}, "
                                  f"{quote_balance} {self._config['quote_asset']}")
                
                # Get currently active orders
                active_orders = self._strategy.active_orders if self._strategy is not None else []
                self.logger().info(f"Active orders at end of test: {len(active_orders)}")
                
                for i, order in enumerate(active_orders):
                    side = "BUY" if order.is_buy else "SELL"
                    self.logger().info(f"  Order {i+1}: {side} {order.quantity} {self._config['base_asset']} @ "
                                      f"{order.price} {self._config['quote_asset']}")


def main():
    """
    Main function to run the test
    """
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # 创建并运行测试器
    tester = ZbitAvellanedaMarketMakingTester()
    asyncio.run(tester.run())


if __name__ == "__main__":
    main() 