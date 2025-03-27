#!/usr/bin/env python

import asyncio
import logging
import os
import sys
import argparse
import inspect
from decimal import Decimal

from hummingbot.core.clock import Clock, ClockMode
from hummingbot.logger import HummingbotLogger
from hummingbot.core.utils.async_utils import safe_ensure_future
from hummingbot.connector.exchange.zbit.zbit_exchange import ZbitExchange
from hummingbot.strategy.market_trading_pair_tuple import MarketTradingPairTuple

# 添加当前目录到路径
sys.path.append(os.path.dirname(os.path.realpath(__file__)))
from zbit_avellaneda_market_making import ZbitAvellanedaMarketMaking
from zbit_avellaneda_market_making_config import get_zbit_avellaneda_config

# 默认API密钥
DEFAULT_API_KEY = "vmPUZE6mv9SD5V5e14y7Ju91duEh8A"
DEFAULT_API_SECRET = "902ae3cb34ecee2779aa4d3e1d226686"


async def main(args):
    """
    Main function to run the Zbit Avellaneda Market Making strategy
    """
    try:
        # Load configuration
        config = get_zbit_avellaneda_config()
        
        # Override config with command line arguments if provided
        if args.trading_pair:
            config["trading_pair"] = args.trading_pair
            # Extract base and quote assets from trading pair
            base, quote = config["trading_pair"].split("-")
            config["base_asset"] = base
            config["quote_asset"] = quote
            
        if args.order_amount:
            config["order_amount"] = Decimal(str(args.order_amount))
            
        if args.risk_factor:
            config["risk_factor"] = Decimal(str(args.risk_factor))
            
        if args.min_spread:
            config["min_spread"] = Decimal(str(args.min_spread))
            
        if args.max_spread:
            config["max_spread"] = Decimal(str(args.max_spread))
            
        if args.inventory_target:
            config["inventory_target_base_pct"] = Decimal(str(args.inventory_target))
            
        if args.debug:
            config["debug_mode"] = True
            logging.getLogger().setLevel(logging.DEBUG)
        
        # Set up the market - 使用默认值或环境变量或命令行参数
        api_key = args.api_key or os.getenv("ZBIT_API_KEY", DEFAULT_API_KEY)
        api_secret = args.api_secret or os.getenv("ZBIT_API_SECRET", DEFAULT_API_SECRET)
        
        logging.getLogger().info(f"Using API key: {api_key[:5]}...{api_key[-5:]} for Zbit exchange")
        
        # 根据错误信息，直接使用预期的参数名称
        # 从错误信息看，需要zbit_api_key和zbit_api_secret参数
        market = ZbitExchange(
            zbit_api_key=api_key,
            zbit_api_secret=api_secret,
            trading_pairs=[config["trading_pair"]]
        )
        
        # Setup logging
        if config["debug_mode"]:
            logging.getLogger("hummingbot.core.utils.async_utils").setLevel(logging.DEBUG)
            logging.getLogger("hummingbot.connector.exchange.zbit").setLevel(logging.DEBUG)
            
        # Start the exchange and wait until ready
        logging.getLogger().info("Initializing Zbit exchange...")
        await market.start_network()
        
        # Wait for the market to be ready
        market_ready = asyncio.Event()
        
        def ready_callback(*args, **kwargs):
            market_ready.set()
            
        market.add_listener("ready", ready_callback)
        
        logging.getLogger().info("Waiting for market to be ready...")
        await asyncio.wait_for(market_ready.wait(), timeout=60.0)
        
        # Create market info
        market_info = MarketTradingPairTuple(
            market,
            config["trading_pair"],
            config["base_asset"],
            config["quote_asset"]
        )
        
        # Create and initialize the strategy
        strategy = ZbitAvellanedaMarketMaking(
            market_info=market_info,
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
        
        # Set up and run the clock
        clock = Clock(ClockMode.REALTIME)
        clock.add_iterator(market)
        clock.add_iterator(strategy)
        
        logging.getLogger().info(f"策略已创建并运行于交易对 {config['trading_pair']}.")
        logging.getLogger().info(f"风险因子: {config['risk_factor']}, 订单数量: {config['order_amount']} {config['base_asset']}")
        logging.getLogger().info(f"最小价差: {config['min_spread']*100}%, 最大价差: {config['max_spread']*100}%")
        logging.getLogger().info(f"订单层级: {config['order_levels']}, 刷新时间: {config['order_refresh_time']} 秒")
        
        # Run the clock
        while True:
            clock.tick()
            if args.runtime and clock.total_seconds > args.runtime:
                logging.getLogger().info(f"达到最大运行时间 {args.runtime} 秒. 停止策略.")
                break
            await asyncio.sleep(1.0)
            
    except KeyboardInterrupt:
        logging.getLogger().info("接收到键盘中断. 停止策略.")
    except Exception as e:
        logging.getLogger().error(f"运行策略时出错: {e}", exc_info=True)
    finally:
        # Clean up
        logging.getLogger().info("停止策略和交易所连接...")
        if 'market' in locals():
            await market.stop_network()
        logging.getLogger().info("策略已停止.")


if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="运行Zbit Avellaneda做市策略")
    
    # Market parameters
    parser.add_argument("--api-key", type=str, help="Zbit API密钥")
    parser.add_argument("--api-secret", type=str, help="Zbit API密钥")
    parser.add_argument("--trading-pair", type=str, help="交易对 (例如 BTC-USDT)")
    
    # Strategy parameters
    parser.add_argument("--order-amount", type=float, help="订单数量")
    parser.add_argument("--risk-factor", type=float, help="风险因子 (γ)")
    parser.add_argument("--min-spread", type=float, help="最小价差 (例如 0.001 表示 0.1%)")
    parser.add_argument("--max-spread", type=float, help="最大价差 (例如 0.05 表示 5%)")
    parser.add_argument("--inventory-target", type=float, help="目标库存百分比 (例如 50 表示 50%)")
    
    # Runtime parameters
    parser.add_argument("--runtime", type=int, help="最大运行时间(秒)")
    parser.add_argument("--debug", action="store_true", help="启用调试模式")
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Run the strategy
    asyncio.run(main(args)) 