#!/usr/bin/env python

import logging
import math
from decimal import Decimal
from typing import List, Dict

import pandas as pd
import numpy as np

from hummingbot.connector.exchange_base import ExchangeBase
from hummingbot.core.clock import Clock
from hummingbot.core.data_type.common import TradeType, OrderType
from hummingbot.core.data_type.limit_order import LimitOrder
from hummingbot.strategy.market_trading_pair_tuple import MarketTradingPairTuple
from hummingbot.strategy.strategy_base import StrategyBase
from hummingbot.core.utils.async_utils import safe_ensure_future
from hummingbot.strategy.hanging_orders_tracker import HangingOrdersTracker


class ZbitAvellanedaMarketMaking(StrategyBase):
    """
    This is an implementation of the Avellaneda-Stoikov market making strategy for Zbit exchange.
    The strategy places buy and sell orders at prices determined by a formula that incorporates 
    market volatility, inventory risk, and time horizon.
    """

    # Strategy configuration parameters
    OPTION_LOG_CREATE_ORDER = 1 << 3
    OPTION_LOG_MAKER_ORDER_FILLED = 1 << 4
    OPTION_LOG_STATUS_REPORT = 1 << 5
    OPTION_LOG_ALL = 0x7fffffffffffffff

    def __init__(self,
                 market_info: MarketTradingPairTuple,
                 risk_factor: Decimal = Decimal("1.0"),  # γ parameter
                 order_amount: Decimal = Decimal("1.0"),
                 time_horizon: int = 3600,  # seconds
                 min_spread: Decimal = Decimal("0.0"),
                 max_spread: Decimal = Decimal("0.1"),  # 10% max spread
                 inventory_target_base_pct: Decimal = Decimal("50"),  # 50% target
                 vol_to_spread_multiplier: Decimal = Decimal("1.0"),
                 volatility_adjustment: bool = True,
                 order_refresh_time: float = 60.0,  # 1 minute
                 order_refresh_tolerance_pct: Decimal = Decimal("0.01"),  # 1%
                 order_optimization_enabled: bool = True,
                 filled_order_delay: float = 60.0,  # 1 minute
                 add_transaction_costs: bool = True,
                 hanging_orders_enabled: bool = False,
                 hanging_orders_cancel_pct: Decimal = Decimal("10.0"),  # 10%
                 order_levels: int = 1,
                 order_level_spread: Decimal = Decimal("0.01"),  # 1% level spread
                 logging_options: int = OPTION_LOG_ALL,
                 debug_mode: bool = False,
                 ):
        """
        Initializes the Zbit Avellaneda market making strategy.
        
        :param market_info: MarketTradingPairTuple for the market
        :param risk_factor: Risk aversion parameter (γ)
        :param order_amount: The order amount for each order
        :param time_horizon: Trading horizon in seconds
        :param min_spread: Minimum spread limit as percentage of mid price
        :param max_spread: Maximum spread limit as percentage of mid price
        :param inventory_target_base_pct: Target base asset balance percentage
        :param vol_to_spread_multiplier: Volatility to spread adjustment parameter
        :param volatility_adjustment: Enable volatility adjustment
        :param order_refresh_time: How often to refresh orders (in seconds)
        :param order_refresh_tolerance_pct: Tolerance for order refresh
        :param order_optimization_enabled: Enable order optimization
        :param filled_order_delay: Delay before placing a new order after a fill
        :param add_transaction_costs: Add transaction costs to order prices
        :param hanging_orders_enabled: Enable hanging orders
        :param hanging_orders_cancel_pct: Hanging orders cancellation spread %
        :param order_levels: Number of order levels to place
        :param order_level_spread: Spread between order levels
        :param logging_options: Logging option flags
        :param debug_mode: Enable debug mode for verbose logging
        """
        super().__init__()
        
        self._market_info = market_info
        self._risk_factor = risk_factor
        self._order_amount = order_amount
        self._time_horizon = time_horizon
        self._min_spread = min_spread
        self._max_spread = max_spread
        self._inventory_target_base_pct = inventory_target_base_pct / Decimal("100")
        self._vol_to_spread_multiplier = vol_to_spread_multiplier
        self._volatility_adjustment = volatility_adjustment
        self._order_refresh_time = order_refresh_time
        self._order_refresh_tolerance_pct = order_refresh_tolerance_pct / Decimal("100")
        self._order_optimization_enabled = order_optimization_enabled
        self._filled_order_delay = filled_order_delay
        self._add_transaction_costs = add_transaction_costs
        self._hanging_orders_enabled = hanging_orders_enabled
        self._hanging_orders_cancel_pct = hanging_orders_cancel_pct / Decimal("100")
        self._order_levels = order_levels
        self._order_level_spread = order_level_spread / Decimal("100")
        self._logging_options = logging_options
        self._debug_mode = debug_mode
        
        # Initialize dynamic variables
        self._last_timestamp = 0
        self._volatility = Decimal("0")
        self._kappa = Decimal("0")  # Market order arrival rate
        self._reservation_price = Decimal("0")
        self._optimal_spread = Decimal("0")
        self._optimal_bid = Decimal("0")
        self._optimal_ask = Decimal("0")
        self._last_mid_price = Decimal("0")
        self._all_markets_ready = False
        self._hanging_orders_tracker = HangingOrdersTracker(self, self._hanging_orders_cancel_pct)
        
        # Volatility calculation variables
        self._price_samples = []
        self._last_sampling_timestamp = 0
        self._sampling_interval = 5.0  # Sample price every 5 seconds
        self._volatility_window = 50  # Number of samples for volatility calculation
        
        # Performance tracking
        self._filled_buys_balance = 0
        self._filled_sells_balance = 0
        self._last_own_trade_price = Decimal("0")
        
        # Add trading pair market
        self.add_markets([market_info.market])
        self._logger = logging.getLogger(__name__)
        
        # Debug logging
        if self._debug_mode:
            self._logger.setLevel(logging.DEBUG)
        else:
            self._logger.setLevel(logging.INFO)

    def logger(self):
        return self._logger
        
    @property
    def active_orders(self) -> List[LimitOrder]:
        """Currently active limit orders (both AMM orders and hanging orders)"""
        return self.market_info_to_active_orders.get(self._market_info, [])

    @property
    def market_info_to_active_orders(self) -> Dict[MarketTradingPairTuple, List[LimitOrder]]:
        """Get dictionary of active orders mapped by market info"""
        return self._sb_order_tracker.market_pair_to_active_orders

    @property
    def active_buys(self) -> List[LimitOrder]:
        """List of active buy orders"""
        return [o for o in self.active_orders if o.is_buy]

    @property
    def active_sells(self) -> List[LimitOrder]:
        """List of active sell orders"""
        return [o for o in self.active_orders if not o.is_buy]
        
    @property
    def market_info(self) -> MarketTradingPairTuple:
        return self._market_info
        
    @property
    def trading_pair(self) -> str:
        return self._market_info.trading_pair
    
    @property
    def base_asset(self) -> str:
        return self._market_info.base_asset
    
    @property
    def quote_asset(self) -> str:
        return self._market_info.quote_asset
            
    def tick(self, timestamp: float):
        """
        Clock tick entry point.
        :param timestamp: current tick timestamp
        """
        if not self._all_markets_ready:
            self._all_markets_ready = all([market.ready for market in self._sb_markets])
            if not self._all_markets_ready:
                return
            else:
                self.logger().info("Markets ready. Starting Zbit Avellaneda Market Making strategy.")
                
        market = self._market_info.market
        trading_pair = self._market_info.trading_pair
        
        # Sample price for volatility calculation
        if timestamp - self._last_sampling_timestamp > self._sampling_interval:
            mid_price = self.get_mid_price()
            if mid_price > 0:
                self._price_samples.append(float(mid_price))
                # Keep window size fixed
                if len(self._price_samples) > self._volatility_window:
                    self._price_samples.pop(0)
                # Update volatility
                if len(self._price_samples) > 1:
                    self._volatility = Decimal(str(self.calculate_volatility()))
            self._last_sampling_timestamp = timestamp
            
        # Only process if necessary
        if timestamp > self._last_timestamp + self._order_refresh_time:
            # Update model parameters
            self.update_parameters(timestamp)
            # Cancel existing orders
            self.cancel_all_orders()
            # Create new orders
            self.create_new_orders()
            # Update timestamp
            self._last_timestamp = timestamp
        
    def update_parameters(self, timestamp: float):
        """
        Update the Avellaneda-Stoikov model parameters.
        :param timestamp: current timestamp
        """
        market = self._market_info.market
        trading_pair = self._market_info.trading_pair
        
        # Get market snapshot
        base_balance = market.get_balance(self.base_asset)
        quote_balance = market.get_balance(self.quote_asset)
        mid_price = self.get_mid_price()
        if mid_price == 0:
            return
        
        # Calculate inventory in base asset value
        total_balance_in_quote = base_balance * mid_price + quote_balance
        inventory_in_quote = total_balance_in_quote * Decimal('0.5')  # Assuming 50/50 target allocation
        
        # Inventory ratio q (between -1 and 1), 0 is neutral
        if total_balance_in_quote == Decimal('0'):
            inventory_ratio = Decimal('0')
        else:
            inventory_ratio = (base_balance * mid_price - inventory_in_quote) / total_balance_in_quote
            inventory_ratio = max(min(inventory_ratio, Decimal('1')), Decimal('-1'))
        
        # Calculate reservation price (adjusted mid price)
        inventory_risk_adjustment = mid_price * self._risk_factor * self._volatility * inventory_ratio
        self._reservation_price = mid_price - inventory_risk_adjustment
        
        # Calculate optimal spread
        remaining_time = Decimal(str(max(1, self._time_horizon - (timestamp % self._time_horizon))))
        self._kappa = Decimal('1')  # Market order arrival rate (simplified)
        spread_adjustment = Decimal('2') * self._risk_factor * self._volatility / self._kappa
        time_adjustment = Decimal('1') / remaining_time * Decimal(str(self._risk_factor * (self._volatility ** 2)))
        
        self._optimal_spread = spread_adjustment + time_adjustment
        
        # Apply min/max spread constraints
        self._optimal_spread = max(self._min_spread * mid_price, min(self._max_spread * mid_price, self._optimal_spread))
        
        # Calculate optimal bid and ask prices
        self._optimal_bid = self._reservation_price - self._optimal_spread / Decimal('2')
        self._optimal_ask = self._reservation_price + self._optimal_spread / Decimal('2')
        
        # Apply min spread constraint to ensure bid < ask
        if self._optimal_bid >= self._optimal_ask:
            avg_price = (self._optimal_bid + self._optimal_ask) / Decimal('2')
            min_half_spread = self._min_spread * mid_price / Decimal('2')
            self._optimal_bid = avg_price - min_half_spread
            self._optimal_ask = avg_price + min_half_spread
            
        # Log update (only in debug mode)
        if self._debug_mode:
            self.logger().debug(
                f"Updated parameters: mid_price={mid_price:.6f}, volatility={self._volatility:.6f}, "
                f"inventory_ratio={inventory_ratio:.4f}, reservation_price={self._reservation_price:.6f}, "
                f"optimal_spread={self._optimal_spread:.6f}, optimal_bid={self._optimal_bid:.6f}, "
                f"optimal_ask={self._optimal_ask:.6f}"
            )
    
    def calculate_volatility(self) -> float:
        """
        Calculate price volatility from recent price samples
        :return: calculated volatility
        """
        if len(self._price_samples) < 2:
            return 0.0
        
        # Calculate log returns
        df = pd.DataFrame({"price": self._price_samples})
        df["log_return"] = np.log(df["price"] / df["price"].shift(1))
        
        # Calculate volatility (annualized)
        volatility = df["log_return"].std() * math.sqrt(365 * 24 * 60 * 60 / self._sampling_interval)
        return volatility
    
    def get_mid_price(self) -> Decimal:
        """
        Get current market mid price
        :return: mid price
        """
        market = self._market_info.market
        trading_pair = self._market_info.trading_pair
        
        ticker = market.get_ticker(trading_pair)
        if ticker is None:
            return Decimal("0")
        
        mid_price = (Decimal(str(ticker["bid"])) + Decimal(str(ticker["ask"]))) / Decimal("2")
        return mid_price
    
    def cancel_all_orders(self):
        """
        Cancel all active orders
        """
        market = self._market_info.market
        active_orders = self.active_orders
        
        for order in active_orders:
            if not self._hanging_orders_tracker.is_order_id_tracked_as_hanging(order.client_order_id):
                market.cancel(self.trading_pair, order.client_order_id)
                
        # Log hanging orders if any
        hanging_orders = self._hanging_orders_tracker.hanging_orders
        if self._debug_mode and len(hanging_orders) > 0:
            self.logger().debug(f"Hanging orders not canceled: {len(hanging_orders)}")
    
    def create_new_orders(self):
        """
        Create new maker orders based on Avellaneda model
        """
        market = self._market_info.market
        trading_pair = self._market_info.trading_pair
        
        # Skip if no optimal prices calculated
        if self._optimal_bid == Decimal("0") or self._optimal_ask == Decimal("0"):
            return
            
        # Get remaining balance
        base_balance = market.get_balance(self.base_asset)
        quote_balance = market.get_balance(self.quote_asset)
        
        # Adjust for additional order levels
        order_levels_adjustment = [Decimal("0")] * self._order_levels
        for i in range(1, self._order_levels):
            order_levels_adjustment[i] = self._order_level_spread * i
        
        # Create buy orders
        for i in range(self._order_levels):
            price_adjustment = order_levels_adjustment[i]
            bid_price = self._optimal_bid * (Decimal("1") - price_adjustment)
            buy_order_amount = self._order_amount / (Decimal("1") + price_adjustment)  # Reduce size for further levels
            
            # Check if we have enough balance
            required_quote = buy_order_amount * bid_price
            if quote_balance < required_quote:
                self.logger().warning(f"Insufficient {self.quote_asset} balance for buy order. "
                                     f"Required: {required_quote}, Available: {quote_balance}")
                continue
                
            # Create the buy order
            market.buy(trading_pair, buy_order_amount, OrderType.LIMIT, bid_price)
            quote_balance -= required_quote
            
            if (self._logging_options & self.OPTION_LOG_CREATE_ORDER):
                self.logger().info(
                    f"Creating buy order: {trading_pair} {buy_order_amount} @ {bid_price}"
                )
        
        # Create sell orders
        for i in range(self._order_levels):
            price_adjustment = order_levels_adjustment[i]
            ask_price = self._optimal_ask * (Decimal("1") + price_adjustment)
            sell_order_amount = self._order_amount / (Decimal("1") + price_adjustment)  # Reduce size for further levels
            
            # Check if we have enough balance
            if base_balance < sell_order_amount:
                self.logger().warning(f"Insufficient {self.base_asset} balance for sell order. "
                                     f"Required: {sell_order_amount}, Available: {base_balance}")
                continue
                
            # Create the sell order
            market.sell(trading_pair, sell_order_amount, OrderType.LIMIT, ask_price)
            base_balance -= sell_order_amount
            
            if (self._logging_options & self.OPTION_LOG_CREATE_ORDER):
                self.logger().info(
                    f"Creating sell order: {trading_pair} {sell_order_amount} @ {ask_price}"
                )
    
    def did_fill_order(self, order_filled_event):
        """
        Function called when an order is filled.
        :param order_filled_event: Order filled event
        """
        order_id = order_filled_event.order_id
        trading_pair = order_filled_event.trading_pair
        
        # Continue tracking orders if they're partially filled
        if order_filled_event.trade_type is TradeType.BUY:
            self._filled_buys_balance += order_filled_event.amount
            if (self._logging_options & self.OPTION_LOG_MAKER_ORDER_FILLED):
                self.logger().info(
                    f"({trading_pair}) Buy order {order_id} filled for {order_filled_event.amount} "
                    f"{order_filled_event.base_asset} at {order_filled_event.price} {order_filled_event.quote_asset}."
                )
        else:
            self._filled_sells_balance += order_filled_event.amount
            if (self._logging_options & self.OPTION_LOG_MAKER_ORDER_FILLED):
                self.logger().info(
                    f"({trading_pair}) Sell order {order_id} filled for {order_filled_event.amount} "
                    f"{order_filled_event.base_asset} at {order_filled_event.price} {order_filled_event.quote_asset}."
                )
                
        # Update hanging orders tracker if enabled
        if self._hanging_orders_enabled:
            hanging_order_ids = [order.client_order_id for order in self.active_orders]
            self._hanging_orders_tracker.update_hanging_orders(hanging_order_ids)
            
        # Schedule a cancel & recreate for remaining orders after a delay
        safe_ensure_future(self.filled_order_delay(self._filled_order_delay))
    
    async def filled_order_delay(self, delay: float):
        """
        Delay before recreating orders after a fill
        :param delay: delay time in seconds
        """
        await asyncio.sleep(delay)
        if self._all_markets_ready:
            self.logger().info(f"Recreating orders after filled order delay ({delay}s)")
            self.cancel_all_orders()
            self.create_new_orders()
    
    def format_status(self) -> str:
        """
        Format status output for display
        :return: formatted status string
        """
        if not self._all_markets_ready:
            return "Markets are still starting up."
            
        # Get basic info
        mid_price = self.get_mid_price()
        base_balance = self._market_info.market.get_balance(self.base_asset)
        quote_balance = self._market_info.market.get_balance(self.quote_asset)
        
        # Calculate asset value in quote currency
        total_value_in_quote = base_balance * mid_price + quote_balance
        base_ratio = (base_balance * mid_price) / total_value_in_quote if total_value_in_quote > 0 else 0
        
        # Format status output
        lines = []
        lines.append(f"  Markets: {self.trading_pair} on {self._market_info.market.name}")
        lines.append(f"  Mid price: {mid_price:.8g}")
        lines.append(f"  Reservation price: {self._reservation_price:.8g}")
        lines.append(f"  Optimal spread: {self._optimal_spread:.8g}")
        lines.append(f"  Optimal bid: {self._optimal_bid:.8g}, optimal ask: {self._optimal_ask:.8g}")
        lines.append(f"  Volatility: {self._volatility:.8g}")
        
        # Inventory info
        lines.append(f"  Inventory: {self.base_asset}: {base_balance:.8g}, {self.quote_asset}: {quote_balance:.8g}")
        lines.append(f"  Inventory ratio: {base_ratio:.1%} {self.base_asset} ({self._inventory_target_base_pct:.1%} target)")
        
        # Strategy parameters
        lines.append(f"  Risk factor (γ): {self._risk_factor}")
        
        # Order info
        lines.append(f"  Active orders: {len(self.active_orders)} "
                    f"({len(self.active_buys)} buys, {len(self.active_sells)} sells)")
        
        # Trading stats
        lines.append(f"  Filled buys: {self._filled_buys_balance:.8g} {self.base_asset}")
        lines.append(f"  Filled sells: {self._filled_sells_balance:.8g} {self.base_asset}")
        
        return "\n".join(lines)

    def start(self, clock: Clock, timestamp: float):
        """
        Start strategy operation
        """
        self._last_timestamp = timestamp
        self._last_sampling_timestamp = timestamp

    def stop(self, clock: Clock):
        """
        Stop the strategy
        """
        self.cancel_all_orders()

    def on_tick(self, timestamp: float):
        """
        Called on each clock tick
        """
        self.tick(timestamp)

# Main function to start the strategy
def start(self):
    ZbitAvellanedaMarketMaking.logger().setLevel(logging.INFO)
    return ZbitAvellanedaMarketMaking(
        market_info=MarketTradingPairTuple(
            self._market,
            self._trading_pair,
            self._base_asset,
            self._quote_asset
        ),
        risk_factor=self._risk_factor,
        order_amount=self._order_amount,
        min_spread=self._min_spread,
        max_spread=self._max_spread,
        inventory_target_base_pct=self._inventory_target_base_pct,
        vol_to_spread_multiplier=self._vol_to_spread_multiplier,
        volatility_adjustment=self._volatility_adjustment,
        order_refresh_time=self._order_refresh_time,
        order_refresh_tolerance_pct=self._order_refresh_tolerance_pct,
        order_optimization_enabled=self._order_optimization_enabled,
        filled_order_delay=self._filled_order_delay,
        add_transaction_costs=self._add_transaction_costs,
        hanging_orders_enabled=self._hanging_orders_enabled,
        hanging_orders_cancel_pct=self._hanging_orders_cancel_pct,
        order_levels=self._order_levels,
        order_level_spread=self._order_level_spread,
    ) 