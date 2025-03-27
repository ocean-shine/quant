#!/usr/bin/env python

import asyncio
import logging
import math
import time
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from hummingbot.connector.exchange_base import ExchangeBase
from hummingbot.core.clock import Clock
from hummingbot.core.data_type.limit_order import LimitOrder
from hummingbot.core.data_type.market_order import MarketOrder
from hummingbot.core.event.events import OrderType, TradeType
from hummingbot.core.utils.async_utils import safe_ensure_future
from hummingbot.core.utils.estimate_fee import estimate_fee
from hummingbot.strategy.market_trading_pair_tuple import MarketTradingPairTuple
from hummingbot.strategy.strategy_base import StrategyBase


class ZbitCrossExchangeMarketMaking(StrategyBase):
    """
    ZBit跨交易所做市策略
    
    该策略基于经典的跨交易所做市策略，从一个交易所的订单簿获取价格，然后在ZBit交易所下单，
    赚取两个交易所之间的价差。
    """
    
    # 日志选项
    OPTION_LOG_CREATE_ORDER = 1 << 3
    OPTION_LOG_MAKER_ORDER_FILLED = 1 << 4
    OPTION_LOG_STATUS_REPORT = 1 << 5
    OPTION_LOG_ALL = 0x7fffffffffffffff
    
    def __init__(self,
                 maker_market: ExchangeBase,  # ZBit做市商交易所
                 taker_market: ExchangeBase,  # 对手方交易所
                 maker_market_trading_pair: str,  # ZBit交易对
                 taker_market_trading_pair: str,  # 对手方交易对
                 min_profitability: Decimal,  # 最低盈利要求
                 order_amount: Decimal,  # 订单数量
                 adjust_order_enabled: bool = True,  # 是否启用订单调整
                 active_order_canceling: bool = True,  # 主动取消订单
                 min_order_amount: Optional[Decimal] = None,  # 最小订单数量
                 limit_order_min_expiration: float = 130.0,  # 限价单最小过期时间
                 cancel_order_threshold: Optional[Decimal] = None,  # 取消订单阈值
                 top_depth_tolerance: Decimal = Decimal(0),  # 顶部深度容忍度
                 anti_hysteresis_duration: float = 60.0,  # 防滞后持续时间
                 order_refresh_time: float = 30.0,  # 订单刷新时间
                 order_refresh_tolerance_pct: Decimal = Decimal("0.02"),  # 订单刷新容差
                 filled_order_delay: float = 60.0,  # 已成交订单延迟
                 order_optimization_enabled: bool = False,  # 订单优化开关
                 ask_order_optimization_depth: Decimal = Decimal("0"),  # 卖单优化深度
                 bid_order_optimization_depth: Decimal = Decimal("0"),  # 买单优化深度
                 add_transaction_costs_to_orders: bool = True,  # 在订单中添加交易成本
                 logging_options: int = OPTION_LOG_ALL,  # 日志选项
                 status_report_interval: float = 900,  # 状态报告间隔
                 taker_to_maker_base_conversion_rate: Decimal = Decimal("1"),  # 基础资产汇率
                 taker_to_maker_quote_conversion_rate: Decimal = Decimal("1"),  # 报价资产汇率
                 slippage_buffer: Decimal = Decimal("0.05")  # 滑点缓冲
                 ):
        """
        初始化ZBit跨交易所做市策略
        
        :param maker_market: 做市商交易所（ZBit）
        :param taker_market: 做市商交易所（如币安）
        :param maker_market_trading_pair: 做市商交易对，如"BTC-USDT"
        :param taker_market_trading_pair: 对手方交易对，如"BTC-USDT"
        :param min_profitability: 最低盈利要求，以小数表示，例如0.01代表1%
        :param order_amount: 订单数量
        :param adjust_order_enabled: 是否启用订单调整
        :param active_order_canceling: 是否主动取消订单
        :param min_order_amount: 最小订单数量，默认无
        :param limit_order_min_expiration: 限价单最小过期时间
        :param cancel_order_threshold: 取消订单阈值
        :param top_depth_tolerance: 顶部深度容忍度
        :param anti_hysteresis_duration: 防滞后持续时间
        :param order_refresh_time: 订单刷新时间
        :param order_refresh_tolerance_pct: 订单刷新容差百分比
        :param filled_order_delay: 已成交订单延迟
        :param order_optimization_enabled: 是否启用订单优化
        :param ask_order_optimization_depth: 卖单优化深度
        :param bid_order_optimization_depth: 买单优化深度
        :param add_transaction_costs_to_orders: 是否在订单中添加交易成本
        :param logging_options: 日志选项
        :param status_report_interval: 状态报告间隔
        :param taker_to_maker_base_conversion_rate: 基础资产汇率
        :param taker_to_maker_quote_conversion_rate: 报价资产汇率
        :param slippage_buffer: 滑点缓冲
        """
        super().__init__()
        
        # 保存参数
        self._maker_market = maker_market
        self._taker_market = taker_market
        
        # 解析交易对
        self._maker_market_trading_pair = maker_market_trading_pair
        self._taker_market_trading_pair = taker_market_trading_pair
        
        # 获取交易对的基础资产和报价资产
        maker_base, maker_quote = maker_market_trading_pair.split("-")
        taker_base, taker_quote = taker_market_trading_pair.split("-")
        
        # 保存交易对的基础资产和报价资产
        self._maker_base = maker_base
        self._maker_quote = maker_quote
        self._taker_base = taker_base
        self._taker_quote = taker_quote
        
        # 创建市场交易对元组
        self._maker_market_tuple = MarketTradingPairTuple(maker_market, maker_market_trading_pair, maker_base, maker_quote)
        self._taker_market_tuple = MarketTradingPairTuple(taker_market, taker_market_trading_pair, taker_base, taker_quote)
        
        # 策略参数
        self._min_profitability = min_profitability
        self._order_amount = order_amount
        self._adjust_order_enabled = adjust_order_enabled
        self._active_order_canceling = active_order_canceling
        self._min_order_amount = min_order_amount
        self._limit_order_min_expiration = limit_order_min_expiration
        self._cancel_order_threshold = cancel_order_threshold or min_profitability
        self._top_depth_tolerance = top_depth_tolerance
        self._anti_hysteresis_duration = anti_hysteresis_duration
        self._order_refresh_time = order_refresh_time
        self._order_refresh_tolerance_pct = order_refresh_tolerance_pct
        self._filled_order_delay = filled_order_delay
        self._order_optimization_enabled = order_optimization_enabled
        self._ask_order_optimization_depth = ask_order_optimization_depth
        self._bid_order_optimization_depth = bid_order_optimization_depth
        self._add_transaction_costs_to_orders = add_transaction_costs_to_orders
        self._logging_options = logging_options
        self._status_report_interval = status_report_interval
        self._taker_to_maker_base_conversion_rate = taker_to_maker_base_conversion_rate
        self._taker_to_maker_quote_conversion_rate = taker_to_maker_quote_conversion_rate
        self._slippage_buffer = slippage_buffer
        
        # 状态变量
        self._last_timestamp = 0
        self._all_markets_ready = False
        self._active_bids = []
        self._active_asks = []
        self._anti_hysteresis_timers = {}
        self._order_fill_buy_events = []
        self._order_fill_sell_events = []
        self._last_order_refresh_time = 0
        self._last_report_time = 0
        self._suggested_price_samples = []
        
        # 添加市场
        self.add_markets([self._maker_market, self._taker_market])
        self._logger = logging.getLogger(__name__)
    
    def format_status(self) -> str:
        """
        获取策略状态字符串
        """
        if not self._all_markets_ready:
            return "市场数据未就绪."
            
        # 获取限价单列表
        lines = []
        warning_lines = []
        
        # 报告资产余额信息
        maker_base, maker_quote = self._maker_market_tuple.base_asset, self._maker_market_tuple.quote_asset
        taker_base, taker_quote = self._taker_market_tuple.base_asset, self._taker_market_tuple.quote_asset
        
        # 报告ZBit市场余额
        maker_base_balance = self._maker_market.get_balance(maker_base)
        maker_quote_balance = self._maker_market.get_balance(maker_quote)
        
        # 报告对手方市场余额
        taker_base_balance = self._taker_market.get_balance(taker_base)
        taker_quote_balance = self._taker_market.get_balance(taker_quote)
        
        lines.extend([
            f"  策略资产:  {maker_base} | {maker_quote}",
            f"  ZBit {maker_base} 余额: {maker_base_balance}",
            f"  ZBit {maker_quote} 余额: {maker_quote_balance}",
            f"  对手方市场 {taker_base} 余额: {taker_base_balance}",
            f"  对手方市场 {taker_quote} 余额: {taker_quote_balance}",
            "\n  活跃订单:"
        ])
        
        # 报告活跃订单
        if len(self._active_bids) > 0:
            avg_bid = sum([o.price for o in self._active_bids]) / len(self._active_bids)
            best_bid_price = max([o.price for o in self._active_bids])
            lines.append(f"    买单  | 价格: {avg_bid:.6f} | 最佳价格: {best_bid_price:.6f} | 数量: {sum([o.quantity for o in self._active_bids])}")
        
        if len(self._active_asks) > 0:
            avg_ask = sum([o.price for o in self._active_asks]) / len(self._active_asks)
            best_ask_price = min([o.price for o in self._active_asks])
            lines.append(f"    卖单  | 价格: {avg_ask:.6f} | 最佳价格: {best_ask_price:.6f} | 数量: {sum([o.quantity for o in self._active_asks])}")
        
        # 获取市场价格
        maker_bid_price = self._maker_market.get_price(self._maker_market_trading_pair, False)
        maker_ask_price = self._maker_market.get_price(self._maker_market_trading_pair, True)
        taker_bid_price = self._taker_market.get_price(self._taker_market_trading_pair, False)
        taker_ask_price = self._taker_market.get_price(self._taker_market_trading_pair, True)
        
        # 价格比较
        maker_price_dict = {"bid": maker_bid_price, "ask": maker_ask_price}
        taker_price_dict = {"bid": taker_bid_price, "ask": taker_ask_price}
        
        lines.extend([
            "\n  市场价格比较:",
            f"    ZBit {self._maker_market_trading_pair} | 买入: {maker_bid_price:.6f} | 卖出: {maker_ask_price:.6f}",
            f"    对手方 {self._taker_market_trading_pair} | 买入: {taker_bid_price:.6f} | 卖出: {taker_ask_price:.6f}",
            f"    买入套利机会: {(taker_bid_price - maker_ask_price) / maker_ask_price:.4%}",
            f"    卖出套利机会: {(maker_bid_price - taker_ask_price) / taker_ask_price:.4%}"
        ])
        
        # 成交事件分析
        if len(self._order_fill_buy_events) > 0:
            lines.append("\n  买入成交事件:")
            for buy_event in self._order_fill_buy_events[-5:]:
                lines.append(f"    {buy_event.trading_pair} | 价格: {buy_event.price:.6f} | 数量: {buy_event.amount:.6f}")
        
        if len(self._order_fill_sell_events) > 0:
            lines.append("\n  卖出成交事件:")
            for sell_event in self._order_fill_sell_events[-5:]:
                lines.append(f"    {sell_event.trading_pair} | 价格: {sell_event.price:.6f} | 数量: {sell_event.amount:.6f}")
        
        # 添加警告
        if len(warning_lines) > 0:
            lines.append("\n  警告:")
            lines.extend(warning_lines)
            
        return "\n".join(lines)
    
    def tick(self, timestamp: float):
        """
        策略的主要循环，每个时钟周期调用一次
        :param timestamp: 当前时间戳
        """
        # 检查所有市场是否就绪
        if not self._all_markets_ready:
            # 添加调试日志，打印市场就绪状态
            maker_ready = self._maker_market.ready if hasattr(self._maker_market, "ready") else False
            taker_ready = self._taker_market.ready if hasattr(self._taker_market, "ready") else False
            self._logger.info(f"市场就绪检查: 做市商={maker_ready}, 对手方={taker_ready}")

            self._all_markets_ready = all(market.ready for market in [self._maker_market, self._taker_market])
            
            # 添加调试日志，打印_all_markets_ready的值
            self._logger.info(f"策略就绪状态更新为: {self._all_markets_ready}")
            
            if not self._all_markets_ready:
                return
        
        # 记录当前时间戳
        self._last_timestamp = timestamp
        
        # 状态报告
        if self._logging_options & self.OPTION_LOG_STATUS_REPORT and timestamp - self._last_report_time > self._status_report_interval:
            self._logger.info(self.format_status())
            self._last_report_time = timestamp
        
        # 主要做市逻辑
        self._process_market_pair()
        
        # 刷新订单逻辑
        if timestamp - self._last_order_refresh_time > self._order_refresh_time:
            self._check_and_cancel_active_orders()
            self._create_proposal()
            self._last_order_refresh_time = timestamp
    
    def _process_market_pair(self):
        """
        处理做市商和对手方市场的交易对
        """
        self._logger.info("处理市场对...")
        self._check_taker_market_price()
        self._recalculate_price_proposal()
    
    def _check_taker_market_price(self):
        """
        检查对手方市场价格，更新价格样本
        """
        taker_bid_price = self._taker_market.get_price(self._taker_market_trading_pair, False)
        taker_ask_price = self._taker_market.get_price(self._taker_market_trading_pair, True)
        
        # 打印价格信息
        self._logger.info(f"对手方市场价格: 买入={taker_bid_price:.6f}, 卖出={taker_ask_price:.6f}")
        
        # 转换为做市商市场的价格
        maker_bid_price = taker_bid_price * self._taker_to_maker_quote_conversion_rate / self._taker_to_maker_base_conversion_rate
        maker_ask_price = taker_ask_price * self._taker_to_maker_quote_conversion_rate / self._taker_to_maker_base_conversion_rate
        
        # 存储价格样本
        self._suggested_price_samples.append((maker_bid_price, maker_ask_price))
        # 保持最后10个样本
        if len(self._suggested_price_samples) > 10:
            self._suggested_price_samples.pop(0)
        
        self._logger.info(f"更新价格样本: {maker_bid_price:.6f}, {maker_ask_price:.6f}")
    
    def _recalculate_price_proposal(self):
        """
        基于对手方市场价格重新计算价格建议
        """
        if len(self._suggested_price_samples) < 1:
            self._logger.info("价格样本不足，跳过价格建议计算")
            return
        
        # 计算平均价格
        sum_bid, sum_ask = 0, 0
        for bid, ask in self._suggested_price_samples:
            sum_bid += bid
            sum_ask += ask
        
        avg_bid = sum_bid / len(self._suggested_price_samples)
        avg_ask = sum_ask / len(self._suggested_price_samples)
        
        self._logger.info(f"平均价格: 买入={avg_bid:.6f}, 卖出={avg_ask:.6f}")
        
        # 考虑滑点缓冲
        adj_bid = avg_bid * (Decimal("1") - self._slippage_buffer)
        adj_ask = avg_ask * (Decimal("1") + self._slippage_buffer)
        
        self._logger.info(f"调整后价格(滑点): 买入={adj_bid:.6f}, 卖出={adj_ask:.6f}")
        
        # 考虑交易手续费
        maker_fee = self._maker_market.get_fee(
            self._maker_market_trading_pair,
            OrderType.LIMIT,
            TradeType.SELL,
            self._order_amount,
            adj_ask
        )
        taker_fee = self._taker_market.get_fee(
            self._taker_market_trading_pair,
            OrderType.MARKET,
            TradeType.BUY,
            self._order_amount,
            adj_bid
        )
        
        self._logger.info(f"手续费: 做市商={maker_fee.percent}, 对手方={taker_fee.percent}")
        
        # 如果需要考虑交易成本，调整价格
        if self._add_transaction_costs_to_orders:
            adj_bid = adj_bid * (Decimal("1") - maker_fee.percent)
            adj_ask = adj_ask * (Decimal("1") + maker_fee.percent)
            self._logger.info(f"调整后价格(手续费): 买入={adj_bid:.6f}, 卖出={adj_ask:.6f}")
        
        # 确保有足够的盈利空间
        min_bid = avg_bid * (Decimal("1") + self._min_profitability)
        max_ask = avg_ask * (Decimal("1") - self._min_profitability)
        
        self._logger.info(f"盈利要求: 买入>={min_bid:.6f}, 卖出<={max_ask:.6f}")
        
        # 最终价格
        final_bid = min(adj_bid, min_bid)
        final_ask = max(adj_ask, max_ask)
        
        self._logger.info(f"最终价格: 买入={final_bid:.6f}, 卖出={final_ask:.6f}")
        
        # 创建和执行订单建议
        self._create_and_execute_proposal(final_bid, final_ask)
    
    def _create_and_execute_proposal(self, bid_price: Decimal, ask_price: Decimal):
        """
        创建和执行订单建议
        :param bid_price: 买单价格
        :param ask_price: 卖单价格
        """
        # 确保价格合理
        if bid_price >= ask_price:
            self._logger.warning("买入价格高于卖出价格，跳过创建订单")
            return
        
        # 检查价格与现有订单的差异
        if self._active_bids and self._active_asks:
            avg_bid = sum([o.price for o in self._active_bids]) / len(self._active_bids)
            avg_ask = sum([o.price for o in self._active_asks]) / len(self._active_asks)
            
            bid_diff_pct = abs(avg_bid - bid_price) / avg_bid if avg_bid else Decimal("0")
            ask_diff_pct = abs(avg_ask - ask_price) / avg_ask if avg_ask else Decimal("0")
            
            self._logger.info(f"价格变动百分比: 买入={bid_diff_pct:.4%}, 卖出={ask_diff_pct:.4%}, 阈值={self._order_refresh_tolerance_pct:.4%}")
            
            # 如果价格变动小于容差，跳过刷新
            if bid_diff_pct < self._order_refresh_tolerance_pct and ask_diff_pct < self._order_refresh_tolerance_pct:
                self._logger.info("价格变动小于容差，保持现有订单")
                return
        
        # 取消现有订单
        self._cancel_all_maker_orders()
        
        # 检查余额
        maker_base, maker_quote = self._maker_market_tuple.base_asset, self._maker_market_tuple.quote_asset
        maker_base_balance = self._maker_market.get_available_balance(maker_base)
        maker_quote_balance = self._maker_market.get_available_balance(maker_quote)
        
        self._logger.info(f"可用余额: {maker_base}={maker_base_balance}, {maker_quote}={maker_quote_balance}")
        
        # 创建买单
        bid_amount = min(
            self._order_amount,
            maker_quote_balance / bid_price
        )
        
        # 创建卖单
        ask_amount = min(
            self._order_amount,
            maker_base_balance
        )
        
        self._logger.info(f"计划订单数量: 买入={bid_amount:.6f}, 卖出={ask_amount:.6f}, 最小数量={self._min_order_amount}")
        
        # 如果金额大于最小订单金额，才创建订单
        if bid_amount > (self._min_order_amount or Decimal("0")):
            if self._logging_options & self.OPTION_LOG_CREATE_ORDER:
                self._logger.info(f"创建买单，价格: {bid_price:.6f}, 数量: {bid_amount:.6f}")
            
            # 创建买单
            order_id = self._maker_market.buy(
                self._maker_market_trading_pair,
                bid_amount,
                OrderType.LIMIT,
                bid_price
            )
            
            # 记录订单
            self._active_bids.append(LimitOrder(
                order_id,
                self._maker_market_trading_pair,
                True,
                self._maker_base,
                self._maker_quote,
                bid_price,
                bid_amount
            ))
            
            self._logger.info(f"买单已创建，订单ID: {order_id}")
        else:
            self._logger.info("买单数量不足，跳过创建")
        
        if ask_amount > (self._min_order_amount or Decimal("0")):
            if self._logging_options & self.OPTION_LOG_CREATE_ORDER:
                self._logger.info(f"创建卖单，价格: {ask_price:.6f}, 数量: {ask_amount:.6f}")
            
            # 创建卖单
            order_id = self._maker_market.sell(
                self._maker_market_trading_pair,
                ask_amount,
                OrderType.LIMIT,
                ask_price
            )
            
            # 记录订单
            self._active_asks.append(LimitOrder(
                order_id,
                self._maker_market_trading_pair,
                False,
                self._maker_base,
                self._maker_quote,
                ask_price,
                ask_amount
            ))
            
            self._logger.info(f"卖单已创建，订单ID: {order_id}")
        else:
            self._logger.info("卖单数量不足，跳过创建")
    
    def _cancel_all_maker_orders(self):
        """
        取消所有做市商的订单
        """
        for order in self._active_bids + self._active_asks:
            self._maker_market.cancel(self._maker_market_trading_pair, order.client_order_id)
        
        # 清空记录
        self._active_bids = []
        self._active_asks = []
    
    def _check_and_cancel_active_orders(self):
        """
        检查和取消活跃订单
        """
        # 如果订单需要取消或重新下单，则取消
        if self._active_order_canceling:
            self._cancel_all_maker_orders()
        
        # 如果没有活跃订单，也需要创建
        if not self._active_bids and not self._active_asks:
            self._create_proposal()
    
    def _create_proposal(self):
        """
        创建订单建议
        """
        # 计算价格
        if len(self._suggested_price_samples) > 0:
            # 获取最后一条价格样本
            bid_price, ask_price = self._suggested_price_samples[-1]
            
            # 考虑交易成本和盈利要求
            adj_bid = bid_price * (Decimal("1") - self._min_profitability)
            adj_ask = ask_price * (Decimal("1") + self._min_profitability)
            
            # 创建和执行订单
            self._create_and_execute_proposal(adj_bid, adj_ask)
    
    @property
    def _current_timestamp(self) -> float:
        """
        获取当前时间戳
        """
        return self._last_timestamp 