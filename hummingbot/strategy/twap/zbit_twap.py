import logging
import statistics
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from hummingbot.client.performance import PerformanceMetrics
from hummingbot.connector.exchange_base import ExchangeBase
from hummingbot.core.clock import Clock
from hummingbot.core.data_type.common import OrderType, TradeType
from hummingbot.core.data_type.limit_order import LimitOrder
from hummingbot.core.data_type.order_book import OrderBook
from hummingbot.core.event.events import (
    MarketOrderFailureEvent,
    OrderCancelledEvent,
    OrderExpiredEvent,
    BuyOrderCompletedEvent,
    OrderFilledEvent,
)
from hummingbot.core.network_iterator import NetworkStatus
from hummingbot.logger import HummingbotLogger
from hummingbot.strategy.conditional_execution_state import ConditionalExecutionState, RunAlwaysExecutionState
from hummingbot.strategy.market_trading_pair_tuple import MarketTradingPairTuple
from hummingbot.strategy.strategy_py_base import StrategyPyBase

# 设置日志格式
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ZbitTwapTradeStrategy(StrategyPyBase):
    """
    Zbit Time-Weighted Average Price strategy
    This strategy is intended for executing trades evenly over a specified time period on Zbit exchange.
    """

    @classmethod
    def logger(cls) -> HummingbotLogger:
        global logger
        if logger is None:
            logger = logging.getLogger(__name__)
        return logger

    def __init__(self,
                 market_infos: List[MarketTradingPairTuple],
                 is_buy: bool,
                 target_asset_amount: Decimal,
                 order_step_size: Decimal,
                 order_price: Decimal,
                 order_delay_time: float = 10.0,
                 execution_state: ConditionalExecutionState = None,
                 cancel_order_wait_time: Optional[float] = 60.0,
                 status_report_interval: float = 900):
        """
        :param market_infos: list of market trading pairs
        :param is_buy: if the order is to buy
        :param target_asset_amount: qty of the order to place
        :param order_step_size: amount of base asset to be configured in each order
        :param order_price: price to place the order at
        :param order_delay_time: how long to wait between placing trades
        :param execution_state: execution state object with the conditions that should be satisfied to run each tick
        :param cancel_order_wait_time: how long to wait before canceling an order
        :param status_report_interval: how often to report network connection related warnings, if any
        """

        if len(market_infos) < 1:
            raise ValueError("market_infos must not be empty.")

        super().__init__()
        self._market_infos = {
            (market_info.market, market_info.trading_pair): market_info
            for market_info in market_infos
        }
        self._all_markets_ready = False
        self._place_orders = True
        self._status_report_interval = status_report_interval
        self._order_delay_time = order_delay_time
        self._quantity_remaining = target_asset_amount
        self._time_to_cancel = {}
        self._is_buy = is_buy
        self._target_asset_amount = target_asset_amount
        self._order_step_size = order_step_size
        self._first_order = True
        self._previous_timestamp = 0
        self._last_timestamp = 0
        self._order_price = order_price
        self._execution_state = execution_state or RunAlwaysExecutionState()
        self._cancel_order_wait_time = cancel_order_wait_time

        all_markets = set([market_info.market for market_info in market_infos])
        self.add_markets(list(all_markets))

        self.logger().info(f"Strategy initialized with target amount: {target_asset_amount}, step size: {order_step_size}, price: {order_price}")

    @property
    def active_bids(self) -> List[Tuple[ExchangeBase, LimitOrder]]:
        return self.order_tracker.active_bids

    @property
    def active_asks(self) -> List[Tuple[ExchangeBase, LimitOrder]]:
        return self.order_tracker.active_asks

    @property
    def active_limit_orders(self) -> List[Tuple[ExchangeBase, LimitOrder]]:
        return self.order_tracker.active_limit_orders

    @property
    def in_flight_cancels(self) -> Dict[str, float]:
        return self.order_tracker.in_flight_cancels

    @property
    def market_info_to_active_orders(self) -> Dict[MarketTradingPairTuple, List[LimitOrder]]:
        return self.order_tracker.market_pair_to_active_orders

    @property
    def place_orders(self):
        return self._place_orders

    def start(self, clock: Clock, timestamp: float):
        self.logger().info("Strategy starting...")
        self._previous_timestamp = timestamp
        super().start(clock, timestamp)

    def tick(self, timestamp: float):
        """
        Clock tick entry point.
        :param timestamp: current tick timestamp
        """
        if not self._all_markets_ready:
            self._all_markets_ready = all([market.ready for market in self.active_markets])
            if not self._all_markets_ready:
                # Markets not ready yet. Don't do anything.
                self.logger().debug("Markets not ready yet...")
                return
        
        self.logger().debug(f"Processing tick at {timestamp}")
        if self._execution_state.process_tick(timestamp, self):
            self.process_tick(timestamp)

    def process_tick(self, timestamp: float):
        """
        Process tick by placing orders if needed and checking for order timeouts.
        :param timestamp: current tick timestamp
        """
        if not self.place_orders:
            self.logger().debug("Orders are not allowed to be placed")
            return

        for market_info in self._market_infos.values():
            self.logger().debug(f"Processing market {market_info.trading_pair}")
            self.process_market(market_info)
            
        # Log status
        self.logger().info(f"Quantity remaining: {self._quantity_remaining}")
        self.logger().info(f"Active orders: {len(self.active_limit_orders)}")

    def process_market(self, market_info):
        """
        Process market by placing and managing orders.
        :param market_info: market info for current market
        """
        current_timestamp = self.current_timestamp
        self.logger().debug(f"Current timestamp: {current_timestamp}, Previous timestamp: {self._previous_timestamp}")
        if len(self.active_limit_orders) == 0:
            # No active orders - place new ones
            if self._quantity_remaining > 0:
                if current_timestamp - self._previous_timestamp >= self._order_delay_time or self._first_order:
                    self._first_order = False
                    self._previous_timestamp = current_timestamp
                    self.logger().info(f"Placing new order for {market_info.trading_pair}")
                    self.place_orders_for_market(market_info)
                else:
                    self.logger().debug(f"Waiting for order delay time ({self._order_delay_time} seconds)")
        else:
            # Check for order timeouts
            for order in self.active_limit_orders:
                if order[1].client_order_id in self._time_to_cancel:
                    if current_timestamp >= self._time_to_cancel[order[1].client_order_id]:
                        self.logger().info(f"Order timeout - cancelling order {order[1].client_order_id}")
                        self.cancel_order(market_info, order[1].client_order_id)
                    else:
                        self.logger().debug(f"Order {order[1].client_order_id} will be cancelled at {self._time_to_cancel[order[1].client_order_id]}")

    def place_orders_for_market(self, market_info):
        """
        Place orders for the specified market.
        :param market_info: market to place orders for
        """
        if not self.has_enough_balance(market_info, self._order_step_size):
            self.logger().warning(f"Not enough balance to place order of size {self._order_step_size}")
            return

        quantized_amount = market_info.market.quantize_order_amount(market_info.trading_pair, self._order_step_size)
        quantized_price = market_info.market.quantize_order_price(market_info.trading_pair, self._order_price)

        self.logger().debug(f"Placing {'buy' if self._is_buy else 'sell'} order for {quantized_amount} {market_info.base_asset} at {quantized_price} {market_info.quote_asset}")

        if self._is_buy:
            order_id = self.buy_with_specific_market(
                market_info,
                quantized_amount,
                order_type=OrderType.LIMIT,
                price=quantized_price
            )
        else:
            order_id = self.sell_with_specific_market(
                market_info,
                quantized_amount,
                order_type=OrderType.LIMIT,
                price=quantized_price
            )

        if order_id is not None:
            self._time_to_cancel[order_id] = self.current_timestamp + self._cancel_order_wait_time
            self.logger().info(f"Placed {'buy' if self._is_buy else 'sell'} order {order_id} for {quantized_amount} {market_info.base_asset} at {quantized_price} {market_info.quote_asset}")
            self.logger().debug(f"Order {order_id} will be cancelled at {self._time_to_cancel[order_id]}")
        else:
            self.logger().warning("Failed to place order")

    def has_enough_balance(self, market_info, amount: Decimal) -> bool:
        """
        Check if there is enough balance to place an order with the specified amount.
        :param market_info: market to check balance for
        :param amount: order amount
        :return: True if there is enough balance, False otherwise
        """
        if self._is_buy:
            quote_balance = market_info.market.get_available_balance(market_info.quote_asset)
            required_amount = amount * self._order_price
            return quote_balance >= required_amount
        else:
            base_balance = market_info.market.get_available_balance(market_info.base_asset)
            return base_balance >= amount

    def did_fill_order(self, order_filled_event):
        """
        Process order filled event.
        :param order_filled_event: order filled event to process
        """
        order_id = order_filled_event.order_id
        market_info = self.order_tracker.get_shadow_market_pair_from_order_id(order_id)
        if market_info is not None:
            self.logger().info(f"Order {order_id} filled for {order_filled_event.amount} {market_info.base_asset}")
            self._quantity_remaining -= order_filled_event.amount

    def did_complete_buy_order(self, order_completed_event):
        """
        Process buy order completed event.
        :param order_completed_event: order completed event to process
        """
        self.log_complete_order(order_completed_event)

    def did_complete_sell_order(self, order_completed_event):
        """
        Process sell order completed event.
        :param order_completed_event: order completed event to process
        """
        self.log_complete_order(order_completed_event)

    def log_complete_order(self, order_completed_event):
        """
        Log order completed event.
        :param order_completed_event: order completed event to log
        """
        market_info = self.order_tracker.get_market_pair_from_order_id(order_completed_event.order_id)
        if market_info is not None:
            self.logger().info(
                f"{'Buy' if isinstance(order_completed_event, BuyOrderCompletedEvent) else 'Sell'} order {order_completed_event.order_id} "
                f"completed for {order_completed_event.base_asset_amount} {market_info.base_asset} "
                f"at {order_completed_event.quote_asset_amount/order_completed_event.base_asset_amount} {market_info.quote_asset}"
            )

    def did_cancel_order(self, cancelled_event: OrderCancelledEvent):
        """
        Process order cancelled event.
        :param cancelled_event: order cancelled event to process
        """
        if cancelled_event.order_id in self._time_to_cancel:
            del self._time_to_cancel[cancelled_event.order_id]

    def did_fail_order(self, order_failed_event: MarketOrderFailureEvent):
        """
        Process order failed event.
        :param order_failed_event: order failed event to process
        """
        self.logger().error(f"Order {order_failed_event.order_id} failed: {order_failed_event.error_msg}")

    def did_expire_order(self, expired_event: OrderExpiredEvent):
        """
        Process order expired event.
        :param expired_event: order expired event to process
        """
        self.logger().info(f"Order {expired_event.order_id} expired")

    def update_remaining_after_removing_order(self, order_id: str, event_type: str):
        """
        Update remaining quantity after removing an order.
        :param order_id: order id to update for
        :param event_type: type of event that triggered the update
        """
        market_info = self.order_tracker.get_market_pair_from_order_id(order_id)
        if market_info is not None:
            self.logger().info(f"Order {order_id} {event_type} - updating remaining quantity")
            order = [o for o in self.active_limit_orders if o[1].client_order_id == order_id]
            if order:
                self._quantity_remaining += order[0][1].quantity