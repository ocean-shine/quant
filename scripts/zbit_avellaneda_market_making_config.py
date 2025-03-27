#!/usr/bin/env python

from decimal import Decimal
import logging

# Configuration for Zbit Avellaneda Market Making strategy
zbit_avellaneda_config = {
    # Exchange configuration
    "exchange": "zbit",  
    "trading_pair": "BTC-USDT",  # Change to the trading pair you want to trade
    "base_asset": "BTC",         # Base asset of the trading pair
    "quote_asset": "USDT",       # Quote asset of the trading pair
    
    # Strategy parameters
    "risk_factor": Decimal("1.0"),               # γ parameter (risk aversion)
    "order_amount": Decimal("0.01"),             # Order size in base asset
    "time_horizon": 3600,                        # Trading horizon in seconds (1 hour)
    "min_spread": Decimal("0.001"),              # Minimum spread (0.1%)
    "max_spread": Decimal("0.05"),               # Maximum spread (5%)
    "inventory_target_base_pct": Decimal("50"),  # Target inventory ratio (50%)
    
    # Volatility configuration
    "vol_to_spread_multiplier": Decimal("1.0"),  # Volatility adjustment factor
    "volatility_adjustment": True,               # Enable volatility adjustment
    
    # Order parameters
    "order_refresh_time": 60.0,                   # Refresh orders every 60 seconds
    "order_refresh_tolerance_pct": Decimal("0.01"), # 1% tolerance
    "order_optimization_enabled": True,           # Enable order price optimization
    "filled_order_delay": 60.0,                   # Delay after order fill
    "add_transaction_costs": True,                # Add transaction costs to prices
    
    # Multi-level orders
    "order_levels": 2,                            # Use 2 levels of orders
    "order_level_spread": Decimal("0.01"),        # 1% spread between levels
    
    # Hanging orders
    "hanging_orders_enabled": True,               # Enable hanging orders
    "hanging_orders_cancel_pct": Decimal("10.0"), # Cancel at 10% spread
    
    # Logging and debug
    "logging_options": 0x7fffffffffffffff,        # Log all events
    "debug_mode": False,                          # Enable debug mode
}

def get_zbit_avellaneda_config():
    """
    Returns the configuration dictionary for the Zbit Avellaneda market making strategy.
    This can be modified programmatically before passing to the strategy.
    """
    return zbit_avellaneda_config

def print_config():
    """
    Prints the current configuration settings
    """
    config = get_zbit_avellaneda_config()
    
    print("\n=== Zbit Avellaneda Market Making Configuration ===\n")
    
    print("Exchange Settings:")
    print(f"  Exchange: {config['exchange']}")
    print(f"  Trading Pair: {config['trading_pair']}")
    
    print("\nStrategy Parameters:")
    print(f"  Risk Factor (γ): {config['risk_factor']}")
    print(f"  Order Amount: {config['order_amount']} {config['base_asset']}")
    print(f"  Time Horizon: {config['time_horizon']} seconds")
    print(f"  Min Spread: {config['min_spread'] * 100}%")
    print(f"  Max Spread: {config['max_spread'] * 100}%")
    print(f"  Inventory Target: {config['inventory_target_base_pct']}%")
    
    print("\nOrder Settings:")
    print(f"  Refresh Time: {config['order_refresh_time']} seconds")
    print(f"  Refresh Tolerance: {config['order_refresh_tolerance_pct']}%")
    print(f"  Optimization Enabled: {config['order_optimization_enabled']}")
    print(f"  Order Levels: {config['order_levels']}")
    print(f"  Level Spread: {config['order_level_spread'] * 100}%")
    
    print("\nHanging Orders:")
    print(f"  Enabled: {config['hanging_orders_enabled']}")
    print(f"  Cancel Threshold: {config['hanging_orders_cancel_pct']}%")
    
    print("\n=== End of Configuration ===\n")

if __name__ == "__main__":
    # Print the configuration if script is run directly
    print_config() 