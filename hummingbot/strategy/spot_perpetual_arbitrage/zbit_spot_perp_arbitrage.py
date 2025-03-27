#!/usr/bin/env python

import logging
from decimal import Decimal
from typing import Dict, List
import pandas as pd

from hummingbot.connector.exchange.zbit.zbit_exchange import ZbitExchange
from hummingbot.connector.derivative.zbit_perpetual.zbit_perpetual_derivative import ZbitPerpetualDerivative
from hummingbot.core.clock import Clock
from hummingbot.core.data_type.common import OrderType, PositionAction, PositionMode, TradeType
from hummingbot.core.event.events import MarketEvent, OrderCancelledEvent, OrderFilledEvent
from hummingbot.core.utils.async_utils import safe_ensure_future
from hummingbot.logger import HummingbotLogger
from hummingbot.strategy.market_trading_pair_tuple import MarketTradingPairTuple
from hummingbot.strategy.spot_perpetual_arbitrage.spot_perpetual_arbitrage import SpotPerpetualArbitrageStrategy
from hummingbot.strategy.spot_perpetual_arbitrage.arb_proposal import ArbProposal, ArbProposalSide

zspa_logger = None


class ZbitSpotPerpArbitrageStrategy(SpotPerpetualArbitrageStrategy):
    """
    This strategy extends the base SpotPerpetualArbitrageStrategy with ZBit-specific optimizations.
    It keeps the same core arbitrage logic but adds enhancements for the ZBit exchange and
    ZBit perpetual markets.
    """

    @classmethod
    def logger(cls) -> HummingbotLogger:
        global zspa_logger
        if zspa_logger is None:
            zspa_logger = logging.getLogger(__name__)
        return zspa_logger

    def __init__(self):
        super().__init__()
        self._zbit_spot_fee_tier = 0  # 默认费率等级
        self._zbit_perp_fee_tier = 0  # 默认费率等级
        self._use_zbit_order_book_for_pricing = True  # 使用ZBit订单簿数据优化定价

    def init_params(self,
                    spot_market_info: MarketTradingPairTuple,
                    perp_market_info: MarketTradingPairTuple,
                    order_amount: Decimal,
                    perp_leverage: int,
                    min_opening_arbitrage_pct: Decimal,
                    min_closing_arbitrage_pct: Decimal,
                    spot_market_slippage_buffer: Decimal = Decimal("0"),
                    perp_market_slippage_buffer: Decimal = Decimal("0"),
                    next_arbitrage_opening_delay: float = 120,
                    status_report_interval: float = 10,
                    zbit_spot_fee_tier: int = 0,
                    zbit_perp_fee_tier: int = 0,
                    use_zbit_order_book_for_pricing: bool = True):
        """
        扩展初始化参数以包括ZBit特定的配置
        """
        super().init_params(
            spot_market_info=spot_market_info,
            perp_market_info=perp_market_info,
            order_amount=order_amount,
            perp_leverage=perp_leverage,
            min_opening_arbitrage_pct=min_opening_arbitrage_pct,
            min_closing_arbitrage_pct=min_closing_arbitrage_pct,
            spot_market_slippage_buffer=spot_market_slippage_buffer,
            perp_market_slippage_buffer=perp_market_slippage_buffer,
            next_arbitrage_opening_delay=next_arbitrage_opening_delay,
            status_report_interval=status_report_interval
        )
        
        self._zbit_spot_fee_tier = zbit_spot_fee_tier
        self._zbit_perp_fee_tier = zbit_perp_fee_tier
        self._use_zbit_order_book_for_pricing = use_zbit_order_book_for_pricing
        
        # 检查市场是否为ZBit或ZBit永续
        if not isinstance(self._spot_market_info.market, ZbitExchange):
            self.logger().warning("现货市场不是ZBit交易所，将使用通用套利逻辑")
        if not isinstance(self._perp_market_info.market, ZbitPerpetualDerivative):
            self.logger().warning("永续市场不是ZBit永续合约，将使用通用套利逻辑")

    def apply_zbit_initial_settings(self):
        """
        应用ZBit特定的初始设置，包括费率和API配置
        """
        if isinstance(self._spot_market_info.market, ZbitExchange):
            self.logger().info(f"设置ZBit现货市场费率层级: {self._zbit_spot_fee_tier}")
            # 这里可以添加ZBit特定的API调用，例如设置费率等级
        
        if isinstance(self._perp_market_info.market, ZbitPerpetualDerivative):
            self.logger().info(f"设置ZBit永续市场费率层级: {self._zbit_perp_fee_tier}")
            # 设置杠杆和持仓模式
            self._perp_market_info.market.set_leverage(self._perp_market_info.trading_pair, self._perp_leverage)
            self._perp_market_info.market.set_position_mode(PositionMode.ONEWAY)
    
    async def get_optimal_arbitrage_prices(self, proposal: ArbProposal) -> ArbProposal:
        """
        使用ZBit订单簿数据优化套利价格
        """
        if not self._use_zbit_order_book_for_pricing:
            return proposal
        
        try:
            # 如果是ZBit交易所，尝试使用订单簿深度数据优化价格
            if isinstance(self._spot_market_info.market, ZbitExchange) and \
               isinstance(self._perp_market_info.market, ZbitPerpetualDerivative):
                
                spot_order_book = await self._spot_market_info.market.get_order_book(self._spot_market_info.trading_pair)
                perp_order_book = await self._perp_market_info.market.get_order_book(self._perp_market_info.trading_pair)
                
                # 根据订单簿深度优化价格
                if proposal.spot_side == ArbProposalSide.BUY:
                    # 现货买入：尝试找到更好的买入价格，但要确保能成交
                    best_ask_price = spot_order_book.get_price(False)  # 最佳卖价
                    optimized_spot_price = min(proposal.spot_price, best_ask_price * (1 + self._spot_market_slippage_buffer))
                    proposal.spot_price = optimized_spot_price
                else:
                    # 现货卖出：尝试找到更好的卖出价格，但要确保能成交
                    best_bid_price = spot_order_book.get_price(True)  # 最佳买价
                    optimized_spot_price = max(proposal.spot_price, best_bid_price * (1 - self._spot_market_slippage_buffer))
                    proposal.spot_price = optimized_spot_price
                
                if proposal.perp_side == ArbProposalSide.BUY:
                    # 永续买入：尝试找到更好的买入价格
                    best_ask_price = perp_order_book.get_price(False)  # 最佳卖价
                    optimized_perp_price = min(proposal.perp_price, best_ask_price * (1 + self._perp_market_slippage_buffer))
                    proposal.perp_price = optimized_perp_price
                else:
                    # 永续卖出：尝试找到更好的卖出价格
                    best_bid_price = perp_order_book.get_price(True)  # 最佳买价
                    optimized_perp_price = max(proposal.perp_price, best_bid_price * (1 - self._perp_market_slippage_buffer))
                    proposal.perp_price = optimized_perp_price
                
                self.logger().info(f"已优化套利价格 - 现货: {proposal.spot_price}, 永续: {proposal.perp_price}")
        except Exception as e:
            self.logger().error(f"优化套利价格时出错: {e}", exc_info=True)
        
        return proposal
    
    async def create_base_proposals(self) -> List[ArbProposal]:
        """
        重写创建套利提案的方法，添加ZBit特定的优化
        """
        # 首先使用基类的方法创建基本提案
        proposals = await super().create_base_proposals()
        
        # 对每个提案应用ZBit特定的优化
        optimized_proposals = []
        for proposal in proposals:
            optimized_proposal = await self.get_optimal_arbitrage_prices(proposal)
            optimized_proposals.append(optimized_proposal)
        
        return optimized_proposals
    
    async def execute_arb_proposal(self, proposal: ArbProposal):
        """
        执行套利提案，添加ZBit特定的优化
        """
        if isinstance(self._spot_market_info.market, ZbitExchange) and \
           isinstance(self._perp_market_info.market, ZbitPerpetualDerivative):
            
            self.logger().info(f"执行ZBit套利 - 现货{proposal.spot_side.name}@{proposal.spot_price}, "
                              f"永续{proposal.perp_side.name}@{proposal.perp_price}")
        
        # 调用基类方法执行套利
        await super().execute_arb_proposal(proposal)
    
    async def check_and_handle_zbit_funding_rate(self):
        """
        检查并处理ZBit的资金费率机会
        """
        if not isinstance(self._perp_market_info.market, ZbitPerpetualDerivative):
            return
        
        try:
            # 获取当前资金费率信息
            funding_info = await self._perp_market_info.market.get_funding_info(self._perp_market_info.trading_pair)
            
            if funding_info:
                funding_rate = funding_info.rate
                next_funding_time = funding_info.next_funding_utc_timestamp
                
                self.logger().info(f"当前资金费率: {funding_rate}, 下次资金费时间: {next_funding_time}")
                
                # 根据资金费率调整策略行为
                # 例如，如果资金费率很高，可以考虑提前平仓或者调整套利阈值
                if funding_rate > Decimal("0.001"):  # 0.1%，较高的正资金费率
                    self.logger().info("检测到较高的正资金费率，调整套利策略...")
                    # 这里可以添加调整逻辑，例如提高平仓阈值
                elif funding_rate < Decimal("-0.001"):  # -0.1%，较高的负资金费率
                    self.logger().info("检测到较高的负资金费率，调整套利策略...")
                    # 这里可以添加调整逻辑，例如降低平仓阈值
        except Exception as e:
            self.logger().error(f"检查资金费率时出错: {e}", exc_info=True)
    
    def tick(self, timestamp: float):
        """
        Tick入口点，每秒调用一次（在正常tick设置下）
        添加ZBit特定的逻辑
        """
        # 调用基类的tick方法
        super().tick(timestamp)
        
        # 仅在策略就绪后执行ZBit特定的逻辑
        if self._all_markets_ready and self._position_mode_ready and self._trading_started:
            # 每隔一段时间检查资金费率
            if self._last_timestamp > 0 and timestamp - self._last_timestamp > 60:  # 每分钟检查一次
                safe_ensure_future(self.check_and_handle_zbit_funding_rate())
    
    async def on_market_events(self):
        """
        处理ZBit特定的市场事件
        """
        # 这里可以添加监听特定市场事件的代码
        pass
    
    def active_positions_df(self) -> pd.DataFrame:
        """
        获取活跃头寸的DataFrame，添加ZBit特定的字段
        """
        # 调用基类方法获取基本DataFrame
        df = super().active_positions_df()
        
        # 如果是ZBit永续市场，添加额外信息
        if isinstance(self._perp_market_info.market, ZbitPerpetualDerivative) and not df.empty:
            # 这里可以添加ZBit特定的字段，例如资金费率等
            pass
        
        return df
    
    def format_status(self) -> str:
        """
        格式化策略状态显示，添加ZBit特定的信息
        """
        # 获取基类的状态格式
        status = super().format_status()
        
        # 添加ZBit特定的信息
        if isinstance(self._spot_market_info.market, ZbitExchange) or \
           isinstance(self._perp_market_info.market, ZbitPerpetualDerivative):
            
            # 这里可以添加ZBit特定的状态信息
            zbit_info = (
                "\n  ZBit特定信息:\n"
                f"    现货费率层级: {self._zbit_spot_fee_tier}\n"
                f"    永续费率层级: {self._zbit_perp_fee_tier}\n"
                f"    使用订单簿优化: {self._use_zbit_order_book_for_pricing}"
            )
            
            # 在基类状态信息之后插入ZBit特定信息
            status_lines = status.split("\n")
            insertion_index = next((i for i, line in enumerate(status_lines) if line.strip() == ""), len(status_lines))
            status_lines.insert(insertion_index, zbit_info)
            status = "\n".join(status_lines)
        
        return status 