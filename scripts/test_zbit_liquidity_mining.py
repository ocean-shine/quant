#!/usr/bin/env python

import asyncio
import logging
import time
from decimal import Decimal
from typing import Dict, List, Any, Optional

from hummingbot.connector.exchange.zbit.zbit_exchange import ZbitExchange
from hummingbot.core.clock import Clock, ClockMode
from hummingbot.core.event.event_logger import EventLogger
from hummingbot.core.utils.async_utils import safe_ensure_future
from hummingbot.core.data_type.common import OrderType, TradeType
from hummingbot.core.data_type.trade_fee import AddedToCostTradeFee
from hummingbot.strategy.market_trading_pair_tuple import MarketTradingPairTuple
from hummingbot.strategy.liquidity_mining.liquidity_mining import LiquidityMiningStrategy
from zbit_liquidity_mining_config import get_zbit_liquidity_mining_config

# 配置日志记录器
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_zbit_liquidity_mining")
logger.setLevel(logging.INFO)

# 添加文件处理程序
file_handler = logging.FileHandler("logs/test_zbit_liquidity_mining.log")
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

class MockZbitExchange(ZbitExchange):
    """
    ZBit交易所的模拟版本，用于测试
    """
    def __init__(self, 
                 zbit_api_key: str,
                 zbit_api_secret: str,
                 trading_pairs: List[str],
                 trading_required: bool = True):
        super().__init__(zbit_api_key, zbit_api_secret, trading_pairs, trading_required)
        self._account_balances = {}
        self._account_available_balances = {}
        self._trading_pairs = trading_pairs
        self._trading_required = trading_required
        self._order_book_tracker = None
        self._in_flight_orders = {}
        self._mock_limit_orders = []
        
        # 创建一个简单的模拟客户端配置对象
        class MockClientConfig:
            def __init__(self):
                self.balance_asset_limit = {}
        
        self._client_config = MockClientConfig()
        
    @property
    def limit_orders(self):
        return self._mock_limit_orders
        
    async def start_network(self):
        # 模拟启动网络
        return
        
    async def stop_network(self):
        # 模拟停止网络
        return
        
    def get_balance(self, currency: str) -> Decimal:
        # 返回模拟余额
        if currency == "BTC":
            return Decimal("1.0")
        elif currency == "USDT":
            return Decimal("50000.0")
        else:
            return Decimal("0")
            
    def get_available_balance(self, currency: str) -> Decimal:
        # 返回可用模拟余额
        return self.get_balance(currency)
        
    def get_price(self, trading_pair: str, is_buy: bool) -> Decimal:
        # 设置BTC-USDT的模拟价格
        mid_price = Decimal("50000")
        spread = Decimal("0.01")  # 1%价差
        
        if is_buy:  # 如果是买单，返回卖盘价格(ask)
            return mid_price * (Decimal("1") + spread / Decimal("2"))
        else:  # 如果是卖单，返回买盘价格(bid)
            return mid_price * (Decimal("1") - spread / Decimal("2"))
            
    def get_mid_price(self, trading_pair: str) -> Decimal:
        # 返回模拟中间价格
        return Decimal("50000")
        
    def get_fee(self, 
                trading_pair: str,
                order_type: OrderType,
                order_side: TradeType,
                amount: Decimal,
                price: Decimal = Decimal("0"),
                is_maker: Optional[bool] = None) -> AddedToCostTradeFee:
        # 返回模拟交易费用 (0.1%)
        return AddedToCostTradeFee(percent=Decimal("0.001"))
        
    async def cancel_all(self, timeout_seconds: float) -> List:
        # 模拟取消所有订单
        return []

class ZbitLiquidityMiningTester:
    """
    ZBit流动性挖矿策略测试类
    """
    
    def __init__(
        self,
        zbit_api_key: str = "vmPUZE6mv9SD5VNHk4HlWFsOr6aKE2zvsw0MuIgwCIPy6utIco14y7Ju91duEh8A",  # 测试API密钥
        zbit_api_secret: str = "NhqPtmdSJYdKjVHjA7PZj4Mge3R5YNiP1e3UZjInClVN65XAbvqqM6A7H5fATj0j",  # 测试API密钥密码
        base_token: str = "BTC",  # 基础代币
        quote_token: str = "USDT",  # 报价代币
        token: str = "USDT",  # 要挖矿的代币
        order_amount: Decimal = Decimal("0.01"),  # 订单量
        spread: Decimal = Decimal("0.01"),  # 价差
        inventory_skew_enabled: bool = True,  # 库存偏斜是否启用
        target_base_pct: Decimal = Decimal("0.5"),  # 目标基础资产百分比
        order_refresh_time: float = 60.0,  # 订单刷新时间
        test_duration: int = 15  # 测试持续时间（秒）
    ):
        """
        初始化ZBit流动性挖矿测试
        
        :param zbit_api_key: ZBit API密钥
        :param zbit_api_secret: ZBit API密钥密码
        :param base_token: 基础代币
        :param quote_token: 报价代币
        :param token: 要挖矿的代币
        :param order_amount: 订单量
        :param spread: 价差
        :param inventory_skew_enabled: 库存偏斜是否启用
        :param target_base_pct: 目标基础资产百分比
        :param order_refresh_time: 订单刷新时间
        :param test_duration: 测试持续时间（秒）
        """
        self._zbit_api_key = zbit_api_key
        self._zbit_api_secret = zbit_api_secret
        self._base_token = base_token
        self._quote_token = quote_token
        self._trading_pair = f"{base_token}-{quote_token}"
        self._token = token
        self._order_amount = order_amount
        self._spread = spread
        self._inventory_skew_enabled = inventory_skew_enabled
        self._target_base_pct = target_base_pct
        self._order_refresh_time = order_refresh_time
        self._test_duration = test_duration
        
        # 设置测试组件
        self._clock = None
        self._zbit_market = None
        self._strategy = None
        self._market_info = None
        self._clock_task = None
        
        # 设置事件记录器
        self._market_event_logger = EventLogger()

    def run(self):
        """
        运行测试
        """
        logger.info("运行ZBit流动性挖矿测试...")
        asyncio.get_event_loop().run_until_complete(self._run_test_async())
        logger.info("ZBit流动性挖矿测试完成")
    
    async def _run_test_async(self):
        """
        异步运行测试
        """
        try:
            # 设置测试环境
            await self._setup_test()
            
            # 执行测试
            await self._run_clock()
            
            # 打印结果
            self._print_summary()
            
            # 清理测试环境
            await self._cleanup()
        except Exception as e:
            logger.error(f"测试过程中发生错误: {str(e)}", exc_info=True)
    
    async def _setup_test(self):
        """
        设置测试环境
        """
        logger.info("设置测试环境...")
        
        # 创建ZBit交易所实例
        self._zbit_market = MockZbitExchange(
            zbit_api_key=self._zbit_api_key,
            zbit_api_secret=self._zbit_api_secret,
            trading_pairs=[self._trading_pair],
            trading_required=True
        )
        
        # 启动ZBit交易所网络
        await self._zbit_market.start_network()
        logger.info(f"ZBit交易所设置完成")
        
        # 设置市场信息
        self._market_info = MarketTradingPairTuple(
            self._zbit_market,
            self._trading_pair,
            self._base_token,
            self._quote_token
        )
        
        # 创建市场信息字典
        market_infos = {self._trading_pair: self._market_info}
        
        # 创建时钟
        self._clock = Clock(ClockMode.BACKTEST, 1.0, time.time(), time.time())
        self._clock.add_iterator(self._zbit_market)
        
        # 创建策略
        self._strategy = LiquidityMiningStrategy()
        
        self._strategy.init_params(
            client_config_map=self._zbit_market._client_config,
            exchange=self._zbit_market,
            market_infos=market_infos,
            token=self._token,
            order_amount=self._order_amount,
            spread=self._spread,
            inventory_skew_enabled=self._inventory_skew_enabled,
            target_base_pct=self._target_base_pct,
            order_refresh_time=self._order_refresh_time,
            order_refresh_tolerance_pct=Decimal("0.2"),
            inventory_range_multiplier=Decimal("1"),
            volatility_interval=300,
            avg_volatility_period=10,
            volatility_to_spread_multiplier=Decimal("1"),
            max_spread=Decimal("-1"),
            max_order_age=3600.0,
            status_report_interval=1.0,
            hb_app_notification=False
        )
        
        # 添加策略到时钟
        self._clock.add_iterator(self._strategy)
        
        # 注册事件处理程序
        from hummingbot.core.event.events import MarketEvent
        self._zbit_market.add_listener(MarketEvent.BuyOrderCreated, self._market_event_logger)
        
        # 启动策略
        self._strategy.start(self._clock, time.time())
        
        # 手动设置策略就绪状态
        self._strategy._ready_to_trade = True
        logger.info("测试环境设置完成")
    
    async def _run_clock(self):
        """
        运行时钟
        """
        logger.info(f"运行时钟，测试持续时间: {self._test_duration}秒")
        
        # 使用with语句运行时钟
        with self._clock:
            # 等待指定的测试持续时间
            await asyncio.sleep(self._test_duration)
        
        logger.info("时钟任务已完成")
    
    def _print_summary(self):
        """
        打印测试结果摘要
        """
        logger.info("测试结果摘要:")
        
        # 打印市场状态
        logger.info("市场状态:")
        logger.info(f"  交易对: {self._trading_pair}")
        logger.info(f"  中间价格: {self._zbit_market.get_mid_price(self._trading_pair)}")
        logger.info(f"  买入价格(Bid): {self._zbit_market.get_price(self._trading_pair, False)}")
        logger.info(f"  卖出价格(Ask): {self._zbit_market.get_price(self._trading_pair, True)}")
        
        # 打印账户余额
        logger.info("账户余额:")
        logger.info(f"  {self._base_token}: {self._zbit_market.get_balance(self._base_token)}")
        logger.info(f"  {self._quote_token}: {self._zbit_market.get_balance(self._quote_token)}")
        
        # 打印活跃订单
        logger.info("活跃订单:")
        if len(self._strategy.active_orders) == 0:
            logger.info("  无活跃订单")
        else:
            for i, order in enumerate(self._strategy.active_orders):
                logger.info(f"  订单 {i+1}: {order.trading_pair} {'买入' if order.is_buy else '卖出'} "
                           f"{order.quantity} @ {order.price}")
        
        # 打印策略参数
        logger.info("策略参数:")
        logger.info(f"  代币: {self._token}")
        logger.info(f"  订单量: {self._order_amount}")
        logger.info(f"  价差: {self._spread}")
        logger.info(f"  库存偏斜启用: {self._inventory_skew_enabled}")
        logger.info(f"  目标基础百分比: {self._target_base_pct}")
        logger.info(f"  订单刷新时间: {self._order_refresh_time}")
    
    async def _cleanup(self):
        """
        清理测试环境
        """
        logger.info("清理测试环境...")
        
        # 取消所有活跃订单
        if self._zbit_market is not None:
            await self._zbit_market.cancel_all(10.0)
            logger.info("所有订单已取消")
        
        # 停止策略
        if self._strategy is not None:
            self._strategy.stop(self._clock)
            logger.info("策略已停止")
        
        # 停止交易所网络
        if self._zbit_market is not None:
            await self._zbit_market.stop_network()
            logger.info("交易所网络已停止")
        
        # 移除事件监听器
        if self._zbit_market is not None and self._market_event_logger is not None:
            try:
                from hummingbot.core.event.events import MarketEvent
                self._zbit_market.remove_listener(MarketEvent.BuyOrderCreated, self._market_event_logger)
                logger.info("事件监听器已移除")
            except Exception as e:
                logger.warning(f"移除事件监听器时发生错误: {str(e)}")
        
        logger.info("测试环境清理完成")


def main():
    """
    主函数
    """
    # 读取配置
    config = get_zbit_liquidity_mining_config()
    
    # 创建测试实例
    tester = ZbitLiquidityMiningTester(
        token=config["token"],
        order_amount=config["order_amount"],
        spread=config["spread"],
        inventory_skew_enabled=config["inventory_skew_enabled"],
        target_base_pct=config["target_base_pct"],
        order_refresh_time=config["order_refresh_time"]
    )
    
    # 运行测试
    tester.run()


if __name__ == "__main__":
    main() 