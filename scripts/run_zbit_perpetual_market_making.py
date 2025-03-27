#!/usr/bin/env python

import logging
import os
import asyncio
from decimal import Decimal
from typing import Dict, List

# 添加项目根目录到Python路径，以便能够导入hummingbot模块
import sys
sys.path.insert(0, os.path.realpath(os.path.join(__file__, "../../")))

from hummingbot.connector.derivative.zbit_perpetual.zbit_perpetual_derivative import ZbitPerpetualDerivative
from hummingbot.core.clock import Clock, ClockMode
from hummingbot.core.data_type.common import PositionMode
from hummingbot.strategy.market_trading_pair_tuple import MarketTradingPairTuple
from hummingbot.strategy.perpetual_market_making.perpetual_market_making import PerpetualMarketMakingStrategy
from hummingbot.strategy.perpetual_market_making.perpetual_market_making_config_map import perpetual_market_making_config_map
from hummingbot.client.settings import AllConnectorSettings, CONNECTOR_SETTINGS, DERIVATIVES
from hummingbot.core.utils.async_utils import safe_ensure_future

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 确保日志目录存在
if not os.path.exists("logs"):
    os.makedirs("logs")

# 配置文件日志
file_handler = logging.FileHandler("logs/zbit_perpetual_market_making.log")
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

# 策略配置
def get_zbit_perpetual_market_making_config() -> Dict:
    """获取ZBit永续市场做市策略配置"""
    return {
        # 基础配置
        "strategy": "perpetual_market_making",
        "exchange": "zbit_perpetual",
        "market": "BTC-USDT",
        
        # 订单配置
        "bid_spread": Decimal("0.01"),         # 买单价差 (1%)
        "ask_spread": Decimal("0.01"),         # 卖单价差 (1%)
        "order_amount": Decimal("0.01"),       # 订单数量 (0.01 BTC)
        "order_refresh_time": 30.0,            # 订单刷新时间 (30秒)
        "order_refresh_tolerance_pct": Decimal("0.01"),  # 订单刷新容差 (1%)
        "order_levels": 3,                     # 订单层级数
        "order_level_amount": Decimal("0.005"),  # 层级数量增量
        "order_level_spread": Decimal("0.005"),  # 层级价差
        
        # 持仓和杠杆配置
        "leverage": 10,                        # 杠杆倍数
        "position_mode": "Hedge",              # 持仓模式: Hedge(对冲) 或 ONEWAY(单向)
        
        # 止盈止损配置
        "long_profit_taking_spread": Decimal("0.02"),    # 多头止盈价差 (2%)
        "short_profit_taking_spread": Decimal("0.02"),   # 空头止盈价差 (2%)
        "stop_loss_spread": Decimal("0.05"),             # 止损价差 (5%)
        "time_between_stop_loss_orders": 60.0,           # 止损订单间隔时间 (60秒)
        "stop_loss_slippage_buffer": Decimal("0.001"),   # 止损滑点缓冲 (0.1%)
        
        # 高级配置
        "minimum_spread": Decimal("0.005"),              # 最小价差 (0.5%)
        "price_ceiling": Decimal("55000"),               # 价格上限
        "price_floor": Decimal("45000"),                 # 价格下限
        "order_optimization_enabled": True,              # 启用订单优化
        "ask_order_optimization_depth": Decimal("0.5"),  # 卖单优化深度
        "bid_order_optimization_depth": Decimal("0.5"),  # 买单优化深度
        "price_type": "mid_price",                       # 价格类型: mid_price, last_price, last_own_trade_price, best_bid, best_ask
        "filled_order_delay": 60.0,                      # 成交订单延迟 (60秒)
        "hanging_orders_enabled": False,                 # 启用挂单
        "hanging_orders_cancel_pct": Decimal("0.1"),     # 挂单取消百分比
        
        # 日志和通知
        "logging_options": PerpetualMarketMakingStrategy.OPTION_LOG_ALL,  # 日志选项
        "hb_app_notification": False,                    # 应用通知
        
        # API密钥配置 - 注意：建议在正式环境中通过环境变量或安全方式传递
        "api_key": "",                                   # API密钥
        "api_secret": "",                                # API密钥密码
        
        # 自定义订单配置
        "order_override": {},                            # 订单覆盖配置
    }

def load_config_from_environment():
    """从环境变量加载配置"""
    config = get_zbit_perpetual_market_making_config()
    
    # 加载API密钥
    config["api_key"] = os.environ.get("ZBIT_API_KEY", "")
    config["api_secret"] = os.environ.get("ZBIT_API_SECRET", "")
    
    # 加载其他可能的环境变量配置
    if "ZBIT_MARKET" in os.environ:
        config["market"] = os.environ["ZBIT_MARKET"]
    
    if "ZBIT_LEVERAGE" in os.environ:
        config["leverage"] = int(os.environ["ZBIT_LEVERAGE"])
    
    if "ZBIT_ORDER_AMOUNT" in os.environ:
        config["order_amount"] = Decimal(os.environ["ZBIT_ORDER_AMOUNT"])
    
    if "ZBIT_BID_SPREAD" in os.environ:
        config["bid_spread"] = Decimal(os.environ["ZBIT_BID_SPREAD"])
    
    if "ZBIT_ASK_SPREAD" in os.environ:
        config["ask_spread"] = Decimal(os.environ["ZBIT_ASK_SPREAD"])
    
    return config

class ZbitPerpetualMarketMaking:
    """ZBit永续市场做市策略运行器"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.markets = {}
        self.strategy = None
        self.clock = None
        self.market_trading_pair_tuple = None
    
    async def setup_exchange(self):
        """设置交易所和市场"""
        logger.info(f"设置交易所：{self.config['exchange']}")
        
        exchange = self.config["exchange"]
        market = self.config["market"]
        
        # 验证API密钥
        if not self.config["api_key"] or not self.config["api_secret"]:
            raise ValueError("请提供API密钥和密钥密码")
        
        # 创建交易所实例
        market_instance = ZbitPerpetualDerivative(
            api_key=self.config["api_key"],
            api_secret=self.config["api_secret"],
            trading_pairs=[market],
            trading_required=True,
        )
        
        self.markets = {exchange: market_instance}
        
        # 允许交易所连接
        await asyncio.sleep(1)
        
        # 检查交易所是否已准备好
        if not market_instance.ready:
            logger.info("等待交易所准备就绪...")
            while not market_instance.ready:
                await asyncio.sleep(1)
        
        logger.info(f"交易所 {exchange} 已准备就绪")
        
        # 设置交易对元组
        base, quote = market.split("-")
        self.market_trading_pair_tuple = MarketTradingPairTuple(
            market_instance, market, base, quote
        )
        
        # 设置杠杆和持仓模式
        logger.info(f"设置杠杆：{self.config['leverage']}x")
        await market_instance.set_leverage(market, self.config["leverage"])
        
        position_mode = PositionMode.HEDGE if self.config["position_mode"] == "Hedge" else PositionMode.ONEWAY
        logger.info(f"设置持仓模式：{position_mode.name}")
        await market_instance.set_position_mode(position_mode)
    
    def set_strategy_config_map(self):
        """设置策略配置"""
        config_map = perpetual_market_making_config_map
        
        # 设置基本配置
        config_map["derivative"].value = self.config["exchange"]
        config_map["market"].value = self.config["market"]
        config_map["leverage"].value = self.config["leverage"]
        config_map["position_mode"].value = self.config["position_mode"]
        
        # 设置订单配置
        config_map["bid_spread"].value = self.config["bid_spread"] * Decimal("100")
        config_map["ask_spread"].value = self.config["ask_spread"] * Decimal("100")
        config_map["order_amount"].value = self.config["order_amount"]
        config_map["order_refresh_time"].value = self.config["order_refresh_time"]
        config_map["order_refresh_tolerance_pct"].value = self.config["order_refresh_tolerance_pct"] * Decimal("100")
        config_map["order_levels"].value = self.config["order_levels"]
        config_map["order_level_amount"].value = self.config["order_level_amount"] 
        config_map["order_level_spread"].value = self.config["order_level_spread"] * Decimal("100")
        
        # 设置止盈止损配置
        config_map["long_profit_taking_spread"].value = self.config["long_profit_taking_spread"] * Decimal("100") 
        config_map["short_profit_taking_spread"].value = self.config["short_profit_taking_spread"] * Decimal("100")
        config_map["stop_loss_spread"].value = self.config["stop_loss_spread"] * Decimal("100")
        config_map["time_between_stop_loss_orders"].value = self.config["time_between_stop_loss_orders"]
        config_map["stop_loss_slippage_buffer"].value = self.config["stop_loss_slippage_buffer"] * Decimal("100")
        
        # 设置高级配置
        config_map["minimum_spread"].value = self.config["minimum_spread"] * Decimal("100")
        config_map["price_ceiling"].value = self.config["price_ceiling"]
        config_map["price_floor"].value = self.config["price_floor"]
        config_map["order_optimization_enabled"].value = self.config["order_optimization_enabled"]
        config_map["ask_order_optimization_depth"].value = self.config["ask_order_optimization_depth"]
        config_map["bid_order_optimization_depth"].value = self.config["bid_order_optimization_depth"]
        config_map["price_type"].value = self.config["price_type"]
        config_map["filled_order_delay"].value = self.config["filled_order_delay"]
        
        logger.info("策略配置已设置")
    
    def create_strategy(self):
        """创建策略实例"""
        logger.info("创建永续市场做市策略实例...")
        
        self.strategy = PerpetualMarketMakingStrategy()
        self.strategy.init_params(
            market_info=self.market_trading_pair_tuple,
            leverage=self.config["leverage"],
            position_mode=self.config["position_mode"],
            bid_spread=self.config["bid_spread"],
            ask_spread=self.config["ask_spread"],
            order_amount=self.config["order_amount"],
            long_profit_taking_spread=self.config["long_profit_taking_spread"],
            short_profit_taking_spread=self.config["short_profit_taking_spread"],
            stop_loss_spread=self.config["stop_loss_spread"],
            time_between_stop_loss_orders=self.config["time_between_stop_loss_orders"],
            stop_loss_slippage_buffer=self.config["stop_loss_slippage_buffer"],
            order_levels=self.config["order_levels"],
            order_level_spread=self.config["order_level_spread"],
            order_level_amount=self.config["order_level_amount"],
            order_refresh_time=self.config["order_refresh_time"],
            order_refresh_tolerance_pct=self.config["order_refresh_tolerance_pct"],
            filled_order_delay=self.config["filled_order_delay"],
            order_optimization_enabled=self.config["order_optimization_enabled"],
            ask_order_optimization_depth=self.config["ask_order_optimization_depth"],
            bid_order_optimization_depth=self.config["bid_order_optimization_depth"],
            price_type=self.config["price_type"],
            price_ceiling=self.config["price_ceiling"],
            price_floor=self.config["price_floor"],
            logging_options=self.config["logging_options"],
            minimum_spread=self.config["minimum_spread"],
            hb_app_notification=self.config["hb_app_notification"],
            order_override=self.config["order_override"],
        )
        
        logger.info("永续市场做市策略实例已创建")
    
    async def run_clock(self):
        """运行时钟"""
        self.clock = Clock(ClockMode.REALTIME)
        
        # 添加交易所到时钟
        for market in self.markets.values():
            self.clock.add_iterator(market)
        
        # 添加策略到时钟
        self.clock.add_iterator(self.strategy)
        
        # 运行时钟
        with self.clock as clock:
            await clock.run()
    
    async def run(self):
        """运行策略"""
        try:
            # 设置交易所
            await self.setup_exchange()
            
            # 设置策略配置映射
            self.set_strategy_config_map()
            
            # 创建策略
            self.create_strategy()
            
            # 打印策略配置
            self.print_strategy_config()
            
            # 运行策略
            logger.info("启动ZBit永续市场做市策略...")
            await self.run_clock()
            
        except KeyboardInterrupt:
            logger.info("用户中断，正在停止策略...")
        except Exception as e:
            logger.error(f"运行策略时发生错误: {e}", exc_info=True)
        finally:
            # 清理资源
            self.cleanup()
    
    def cleanup(self):
        """清理资源"""
        logger.info("清理资源...")
        # 这里可以添加任何必要的清理代码
        logger.info("资源清理完成")
    
    def print_strategy_config(self):
        """打印策略配置"""
        logger.info("\n========== 策略配置 ==========")
        logger.info(f"交易所: {self.config['exchange']}")
        logger.info(f"交易对: {self.config['market']}")
        logger.info(f"杠杆: {self.config['leverage']}x")
        logger.info(f"持仓模式: {self.config['position_mode']}")
        logger.info(f"买单价差: {self.config['bid_spread'] * 100}%")
        logger.info(f"卖单价差: {self.config['ask_spread'] * 100}%")
        logger.info(f"订单数量: {self.config['order_amount']}")
        logger.info(f"订单层级: {self.config['order_levels']}")
        logger.info(f"订单刷新时间: {self.config['order_refresh_time']}秒")
        logger.info(f"多头止盈价差: {self.config['long_profit_taking_spread'] * 100}%")
        logger.info(f"空头止盈价差: {self.config['short_profit_taking_spread'] * 100}%")
        logger.info(f"止损价差: {self.config['stop_loss_spread'] * 100}%")
        logger.info("================================\n")

async def main():
    # 加载配置
    config = load_config_from_environment()
    
    # 创建并运行策略
    market_maker = ZbitPerpetualMarketMaking(config)
    await market_maker.run()

if __name__ == "__main__":
    print("启动ZBit永续市场做市策略...")
    
    # 注册交易所设置
    if "zbit_perpetual" not in CONNECTOR_SETTINGS:
        CONNECTOR_SETTINGS.update(AllConnectorSettings.create_derivative_connector_settings([(DERIVATIVES, "zbit_perpetual")]))
    
    # 运行策略
    ev_loop = asyncio.get_event_loop()
    try:
        ev_loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("用户中断...")
    finally:
        print("ZBit永续市场做市策略已停止")
        ev_loop.close() 