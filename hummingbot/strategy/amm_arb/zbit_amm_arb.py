import asyncio
import logging
from decimal import Decimal
from functools import lru_cache
from typing import Callable, Dict, List, Optional, Tuple, cast

import pandas as pd

from hummingbot.client.performance import PerformanceMetrics
from hummingbot.client.settings import AllConnectorSettings, GatewayConnectionSetting
from hummingbot.connector.connector_base import ConnectorBase
from hummingbot.connector.gateway.amm.gateway_ethereum_amm import GatewayEthereumAMM
from hummingbot.connector.gateway.gateway_price_shim import GatewayPriceShim
from hummingbot.core.clock import Clock
from hummingbot.core.data_type.limit_order import LimitOrder
from hummingbot.core.data_type.market_order import MarketOrder
from hummingbot.core.data_type.trade_fee import TokenAmount
from hummingbot.core.event.events import (
    BuyOrderCompletedEvent,
    MarketOrderFailureEvent,
    OrderCancelledEvent,
    OrderExpiredEvent,
    OrderType,
    SellOrderCompletedEvent,
)
from hummingbot.core.rate_oracle.rate_oracle import RateOracle
from hummingbot.core.utils.async_utils import safe_ensure_future
from hummingbot.logger import HummingbotLogger
from hummingbot.strategy.amm_arb.data_types import ArbProposalSide
from hummingbot.strategy.amm_arb.utils import ArbProposal, create_arb_proposals
from hummingbot.strategy.market_trading_pair_tuple import MarketTradingPairTuple
from hummingbot.strategy.strategy_py_base import StrategyPyBase

NaN = float("nan")
s_decimal_zero = Decimal(0)
zbit_amm_logger = None


class ZbitAmmArbStrategy(StrategyPyBase):
    """
    这是一个AMM套利策略，适用于大多数类型的连接器(CEX, DEX或AMM)，并针对Zbit交易所做了特别优化。
    对于给定的订单数量，策略会检查交易双方(市场1和市场2)是否存在套利机会。
    如果存在，策略会向两个市场提交maker订单。
    """

    _market_info_1: MarketTradingPairTuple
    _market_info_2: MarketTradingPairTuple
    _min_profitability: Decimal
    _order_amount: Decimal
    _market_1_slippage_buffer: Decimal
    _market_2_slippage_buffer: Decimal
    _concurrent_orders_submission: bool
    _last_no_arb_reported: float
    _arb_proposals: Optional[List[ArbProposal]]
    _all_markets_ready: bool
    _ev_loop: asyncio.AbstractEventLoop
    _main_task: Optional[asyncio.Task]
    _last_timestamp: float
    _status_report_interval: float
    _rate_source: Optional[RateOracle]
    _cancel_outdated_orders_task: Optional[asyncio.Task]
    _gateway_transaction_cancel_interval: int
    _order_refresh_time: Decimal
    _retry_interval: Decimal
    _max_retries: int
    _retry_count: Dict[str, int]  # 记录每个订单ID的重试次数
    _debug_mode: bool

    @classmethod
    def logger(cls) -> HummingbotLogger:
        global zbit_amm_logger
        if zbit_amm_logger is None:
            zbit_amm_logger = logging.getLogger(__name__)
        return zbit_amm_logger

    def init_params(self,
                    market_info_1: MarketTradingPairTuple,
                    market_info_2: MarketTradingPairTuple,
                    min_profitability: Decimal,
                    order_amount: Decimal,
                    market_1_slippage_buffer: Decimal = Decimal("0"),
                    market_2_slippage_buffer: Decimal = Decimal("0"),
                    concurrent_orders_submission: bool = True,
                    status_report_interval: float = 900,
                    gateway_transaction_cancel_interval: int = 600,
                    rate_source: Optional[RateOracle] = RateOracle.get_instance(),
                    order_refresh_time: Decimal = Decimal("30"),
                    retry_interval: Decimal = Decimal("5"),
                    max_retries: int = 3,
                    debug_mode: bool = False,
                    ):
        """
        初始化策略参数，此函数必须在init之后直接调用。
        这样做的原因是让参数在内省时可发现（在Cython类的init中不可能）。
        :param market_info_1: 第一个市场
        :param market_info_2: 第二个市场
        :param min_profitability: 执行交易的最小盈利能力（例如0.0003表示0.3%）
        :param order_amount: 订单金额
        :param market_1_slippage_buffer: 为了提高订单成交几率而调整订单价格的缓冲区。对于AMM特别重要，
        因为交易需要很长时间，有一定的滑点比订单被拒绝更可接受。提交的订单价格会调高买单价格，调低卖单价格。
        :param market_2_slippage_buffer: 市场2的滑点缓冲区
        :param concurrent_orders_submission: 是否同时提交两个套利挂单（买单和卖单）
        如果为false，机器人将等待第一个交易所订单成交后再提交另一个订单。
        :param status_report_interval: 等待刷新状态报告的秒数
        :param gateway_transaction_cancel_interval: 在尝试取消未包含在区块中的订单前等待的秒数（仍在内存池中）。
        :param rate_source: 用于转换汇率的源 - (RateOracle或FixedRateSource) - 默认是FixedRateSource
        :param order_refresh_time: 刷新订单的时间间隔（秒）
        :param retry_interval: 重试失败订单的时间间隔（秒）
        :param max_retries: 失败订单的最大重试次数
        :param debug_mode: 是否启用调试模式
        """
        self._market_info_1 = market_info_1
        self._market_info_2 = market_info_2
        self._min_profitability = min_profitability
        self._order_amount = order_amount
        self._market_1_slippage_buffer = market_1_slippage_buffer
        self._market_2_slippage_buffer = market_2_slippage_buffer
        self._concurrent_orders_submission = concurrent_orders_submission
        self._last_no_arb_reported = 0
        self._all_arb_proposals = None
        self._all_markets_ready = False

        self._ev_loop = asyncio.get_event_loop()
        self._main_task = None

        self._last_timestamp = 0
        self._status_report_interval = status_report_interval
        self.add_markets([market_info_1.market, market_info_2.market])

        self._rate_source = rate_source

        self._cancel_outdated_orders_task = None
        self._gateway_transaction_cancel_interval = gateway_transaction_cancel_interval
        
        self._order_refresh_time = order_refresh_time
        self._retry_interval = retry_interval
        self._max_retries = max_retries
        self._retry_count = {}  # 初始化重试计数器
        self._debug_mode = debug_mode

        self._order_id_side_map: Dict[str, ArbProposalSide] = {}

    @property
    def all_markets_ready(self) -> bool:
        return self._all_markets_ready

    @all_markets_ready.setter
    def all_markets_ready(self, value: bool):
        self._all_markets_ready = value

    @property
    def min_profitability(self) -> Decimal:
        return self._min_profitability

    @property
    def order_amount(self) -> Decimal:
        return self._order_amount

    @order_amount.setter
    def order_amount(self, value: Decimal):
        self._order_amount = value

    @property
    def rate_source(self) -> Optional[RateOracle]:
        return self._rate_source

    @rate_source.setter
    def rate_source(self, src: Optional[RateOracle]):
        self._rate_source = src

    @property
    def market_info_to_active_orders(self) -> Dict[MarketTradingPairTuple, List[LimitOrder]]:
        return self._sb_order_tracker.market_pair_to_active_orders

    @property
    def order_refresh_time(self) -> Decimal:
        return self._order_refresh_time

    @order_refresh_time.setter
    def order_refresh_time(self, value: Decimal):
        self._order_refresh_time = value

    @property
    def retry_interval(self) -> Decimal:
        return self._retry_interval

    @retry_interval.setter
    def retry_interval(self, value: Decimal):
        self._retry_interval = value

    @property
    def max_retries(self) -> int:
        return self._max_retries

    @max_retries.setter
    def max_retries(self, value: int):
        self._max_retries = value

    @property
    def debug_mode(self) -> bool:
        return self._debug_mode

    @debug_mode.setter
    def debug_mode(self, value: bool):
        self._debug_mode = value

    @staticmethod
    @lru_cache(maxsize=10)
    def is_gateway_market(market_info: MarketTradingPairTuple) -> bool:
        return market_info.market.name in sorted(
            AllConnectorSettings.get_gateway_amm_connector_names()
        )

    @staticmethod
    @lru_cache(maxsize=10)
    def is_gateway_market_evm_compatible(market_info: MarketTradingPairTuple) -> bool:
        connector_spec: Dict[str, str] = GatewayConnectionSetting.get_connector_spec_from_market_name(market_info.market.name)
        return connector_spec["chain"] == "ethereum"
        
    @staticmethod
    @lru_cache(maxsize=10)
    def is_zbit_market(market_info: MarketTradingPairTuple) -> bool:
        """
        检查给定的市场信息是否关联到Zbit交易所
        """
        return "zbit" in market_info.market.name.lower() 

    async def execute_arb_proposals(self, arb_proposals: List[ArbProposal]):
        """
        执行套利提案
        :param arb_proposals: 套利提案列表
        """
        for arb_proposal in arb_proposals:
            first_side: ArbProposalSide = arb_proposal.first_side
            second_side: ArbProposalSide = arb_proposal.second_side
            self.logger().info(f"执行套利提案: {arb_proposal}")

            try:
                # 根据是否并发提交订单执行不同的逻辑
                if self._concurrent_orders_submission:
                    first_order_id = await self.place_arb_order(first_side.market_info,
                                                           first_side.is_buy,
                                                           first_side.amount,
                                                           first_side.order_price)
                    second_order_id = await self.place_arb_order(second_side.market_info,
                                                            second_side.is_buy,
                                                            second_side.amount,
                                                            second_side.order_price)
                    self._order_id_side_map[first_order_id] = first_side
                    self._order_id_side_map[second_order_id] = second_side
                else:
                    self.logger().info("等待第一个套利订单完成...")
                    try:
                        first_order_id = await self.place_arb_order(first_side.market_info,
                                                              first_side.is_buy,
                                                              first_side.amount,
                                                              first_side.order_price)
                        self._order_id_side_map[first_order_id] = first_side
                        await first_side.completed_event.wait()
                        if first_side.is_failed:
                            self.logger().info("第一个套利订单失败. 放弃第二个套利订单.")
                            continue
                        else:
                            self.logger().info("第一个套利订单已完成. 提交第二个订单...")
                    except Exception as e:
                        self.logger().error(f"在执行第一个套利订单时出错: {str(e)}")
                        continue

                    try:
                        second_order_id = await self.place_arb_order(second_side.market_info,
                                                                second_side.is_buy,
                                                                second_side.amount,
                                                                second_side.order_price)
                        self._order_id_side_map[second_order_id] = second_side
                    except Exception as e:
                        self.logger().error(f"在执行第二个套利订单时出错: {str(e)}")
                        continue

                if self._debug_mode:
                    await arb_proposal.wait()
                    self.logger().info(f"套利已完成: {arb_proposal}")
                    
            except Exception as e:
                self.logger().error(f"执行套利提案时出错: {str(e)}")

    async def place_arb_order(self,
                         market_info: MarketTradingPairTuple,
                         is_buy: bool,
                         amount: Decimal,
                         order_price: Decimal) -> str:
        """
        下一个套利订单
        :param market_info: 市场交易对信息
        :param is_buy: 是否为买单
        :param amount: 订单金额
        :param order_price: 订单价格
        :return: 订单ID
        """
        self.logger().info(f"在 {market_info.market.name} 上{'买入' if is_buy else '卖出'} "
                          f"{amount} {market_info.base_asset} at {order_price} {market_info.quote_asset}.")
                          
        # 如果是Zbit市场，使用特定的Zbit交易所订单类型和功能
        if self.is_zbit_market(market_info):
            self.logger().info(f"使用Zbit优化的订单方式: {'买入' if is_buy else '卖出'}")
            
        # 下单操作
        if is_buy:
            order_id = self.buy_with_specific_market(
                market_trading_pair_tuple=market_info,
                amount=amount,
                order_type=OrderType.LIMIT,
                price=order_price,
            )
        else:
            order_id = self.sell_with_specific_market(
                market_trading_pair_tuple=market_info,
                amount=amount,
                order_type=OrderType.LIMIT,
                price=order_price,
            )
        return order_id

    def ready_for_new_arb_trades(self) -> bool:
        """
        检查策略是否已经准备好执行新的套利交易
        :return: 如果策略已经准备好，则返回True
        """
        market_infos_to_active_orders = self.market_info_to_active_orders
        if (not self._concurrent_orders_submission and
                (len(market_infos_to_active_orders.get(self._market_info_1, [])) > 0 or
                 len(market_infos_to_active_orders.get(self._market_info_2, [])) > 0)):
            return False
        return True

    def short_proposal_msg(self, arb_proposal: List[ArbProposal], indented: bool = True) -> List[str]:
        """
        生成有关套利提案的简短消息
        :param arb_proposal: 套利提案
        :param indented: 是否缩进消息
        :return: 消息列表
        """
        lines = []
        for proposal in arb_proposal:
            profit_pct = proposal.profit_pct(rate_source=self._rate_source, account_for_fee=True)
            lines.append(f"{'    ' if indented else ''}{profit_pct:.2%}: "
                          f"{proposal.first_side}, {proposal.second_side}")
        return lines

    def get_fixed_rates_df(self):
        rates_dict = {}
        for market_info in [self._market_info_1, self._market_info_2]:
            market, trading_pair = market_info.market, market_info.trading_pair
            base, quote = trading_pair.split("-")
            if self._rate_source is not None:
                conversion_rate = self._rate_source.get_pair_rate(f"{base}-{quote}")
                rates_dict.update({market.name: {'base': base, 'quote': quote, 'rate': float(conversion_rate)}})
        return pd.DataFrame(rates_dict).T

    async def format_status(self) -> str:
        """
        返回策略的状态消息
        """
        if not self.all_markets_ready:
            return "正在连接到市场..."
            
        columns = ["Exchange", "Market", "Best Bid", "Best Ask", "Mid Price"]
        data = []
        for market_info in [self._market_info_1, self._market_info_2]:
            market, trading_pair = market_info.market, market_info.trading_pair
            bid_price = await market.get_quote_price(trading_pair, True, self._order_amount)
            ask_price = await market.get_quote_price(trading_pair, False, self._order_amount)
            mid_price = (bid_price + ask_price) / 2
            data.append([
                market.display_name,
                trading_pair,
                float(bid_price),
                float(ask_price),
                float(mid_price)
            ])

        markets_df = pd.DataFrame(data=data, columns=columns)
        lines = []
        lines.extend(["", "  市场状态:"] + ["    " + line for line in markets_df.to_string(index=False).split("\n")])

        # 打印活跃订单
        if len(self.active_orders) > 0:
            df = self.active_orders_df()
            lines.extend(["", "  活跃订单:"] + ["    " + line for line in df.to_string(index=False).split("\n")])
        else:
            lines.extend(["", "  No active maker orders."])

        # 打印活跃的套利提案
        proposals = "  现在没有可行的套利机会."
        if self._all_arb_proposals is not None and len(self._all_arb_proposals) > 0:
            proposals = "最好的套利机会:\n"
            proposals = "\n".join(self.short_proposal_msg(self._all_arb_proposals))
        lines.extend(["", proposals])

        # 添加性能
        try:
            lines.extend(["", "  性能:"] + [f"    {line}" for line in self.performance_metrics_df().to_string(index=False).split("\n")])
        except Exception:
            lines.extend(["", f"  无性能信息可用. {traceback.format_exc()}"])

        if hasattr(self._market_info_1.market, "network_transaction_fee") or hasattr(self._market_info_2.market, "network_transaction_fee"):
            fee_description_str = "交易费用:"
            lines.extend(["", fee_description_str])
            if hasattr(self._market_info_1.market, "network_transaction_fee"):
                fee_dict = getattr(self._market_info_1.market, "network_transaction_fee")
                lines.extend([f"  {self._market_info_1.market.display_name}: "
                              f"{fee_dict.get('gas_price', Decimal('0'))} "
                              f"{fee_dict.get('gas_token', 'n/a')}"])
            if hasattr(self._market_info_2.market, "network_transaction_fee"):
                fee_dict = getattr(self._market_info_2.market, "network_transaction_fee")
                lines.extend([f"  {self._market_info_2.market.display_name}: "
                              f"{fee_dict.get('gas_price', Decimal('0'))} "
                              f"{fee_dict.get('gas_token', 'n/a')}"])

        # 额外信息仅在Zbit交易所时显示
        if self.is_zbit_market(self._market_info_1) or self.is_zbit_market(self._market_info_2):
            lines.extend(["", "  Zbit交易所特定信息:", f"    刷新时间: {float(self._order_refresh_time)}秒", 
                        f"    最大重试次数: {self._max_retries}", f"    重试间隔: {float(self._retry_interval)}秒"])

        if self._debug_mode:
            lines.extend(["", "  配置参数:", 
                         f"    最小盈利率: {float(self._min_profitability):.2%}", 
                         f"    订单金额: {float(self._order_amount)}", 
                         f"    市场1滑点缓冲区: {float(self._market_1_slippage_buffer):.2%}", 
                         f"    市场2滑点缓冲区: {float(self._market_2_slippage_buffer):.2%}", 
                         f"    并发订单提交: {self._concurrent_orders_submission}"])

        return "\n".join(lines)

    def set_order_completed(self, order_id: str):
        """
        将订单标记为已完成
        :param order_id: 订单ID
        """
        if order_id in self._order_id_side_map:
            self._order_id_side_map[order_id].set_completed()

    def set_order_failed(self, order_id: str):
        """
        将订单标记为失败
        :param order_id: 订单ID
        """
        if order_id in self._order_id_side_map:
            self._order_id_side_map[order_id].set_failed()
            
            # 检查是否需要重试失败的订单
            if self._max_retries > 0:
                side = self._order_id_side_map[order_id]
                if order_id not in self._retry_count:
                    self._retry_count[order_id] = 0
                    
                if self._retry_count[order_id] < self._max_retries:
                    self._retry_count[order_id] += 1
                    self.logger().info(f"订单 {order_id} 失败，进行第 {self._retry_count[order_id]} 次重试...")
                    # 安排在稍后重试
                    safe_ensure_future(self.retry_order(side))
                else:
                    self.logger().info(f"订单 {order_id} 已达到最大重试次数 {self._max_retries}，不再重试.")
    
    async def retry_order(self, side: ArbProposalSide):
        """
        重试失败的订单
        :param side: 套利提案的一侧
        """
        # 等待重试间隔
        await asyncio.sleep(float(self._retry_interval))
        
        try:
            # 重新获取市场价格
            is_buy = side.is_buy
            market_info = side.market_info
            amount = side.amount
            
            # 获取最新价格
            if is_buy:
                price = await market_info.market.get_quote_price(market_info.trading_pair, True, amount)
                # 稍微提高买入价格以增加成交可能性
                price = price * (Decimal("1") + self._market_1_slippage_buffer if market_info == self._market_info_1 
                                else self._market_2_slippage_buffer)
            else:
                price = await market_info.market.get_quote_price(market_info.trading_pair, False, amount)
                # 稍微降低卖出价格以增加成交可能性
                price = price * (Decimal("1") - self._market_1_slippage_buffer if market_info == self._market_info_1 
                                else self._market_2_slippage_buffer)
            
            self.logger().info(f"重试订单: {'买入' if is_buy else '卖出'} {amount} {market_info.base_asset} at {price} {market_info.quote_asset}")
            
            # 重新下单
            order_id = await self.place_arb_order(market_info, is_buy, amount, price)
            self._order_id_side_map[order_id] = side
            
        except Exception as e:
            self.logger().error(f"重试订单时出错: {str(e)}")

    def did_complete_buy_order(self, order_completed_event: BuyOrderCompletedEvent):
        """
        订单完成事件回调
        :param order_completed_event: 买单完成事件
        """
        self.log_with_clock(logging.INFO,
                            f"买单 {order_completed_event.order_id} 已完成 - "
                            f"价格: {order_completed_event.price}, "
                            f"数量: {order_completed_event.base_asset_amount}.")
        self.set_order_completed(order_completed_event.order_id)
        
        # 对于Zbit交易所，记录更详细的信息
        if "zbit" in order_completed_event.exchange_id.lower():
            self.logger().info(f"Zbit买单已完成. 时间: {pd.Timestamp.now()}")

    def did_complete_sell_order(self, order_completed_event: SellOrderCompletedEvent):
        """
        订单完成事件回调
        :param order_completed_event: 卖单完成事件
        """
        self.log_with_clock(logging.INFO,
                            f"卖单 {order_completed_event.order_id} 已完成 - "
                            f"价格: {order_completed_event.price}, "
                            f"数量: {order_completed_event.base_asset_amount}.")
        self.set_order_completed(order_completed_event.order_id)
        
        # 对于Zbit交易所，记录更详细的信息
        if "zbit" in order_completed_event.exchange_id.lower():
            self.logger().info(f"Zbit卖单已完成. 时间: {pd.Timestamp.now()}")

    def did_fail_order(self, order_failed_event: MarketOrderFailureEvent):
        """
        订单失败事件回调
        :param order_failed_event: 市场订单失败事件
        """
        self.log_with_clock(logging.INFO,
                            f"订单 {order_failed_event.order_id} 失败.")
        self.set_order_failed(order_failed_event.order_id)

    def did_cancel_order(self, cancelled_event: OrderCancelledEvent):
        """
        订单取消事件回调
        :param cancelled_event: 订单取消事件
        """
        self.logger().info(f"订单 {cancelled_event.order_id} 已取消.")

    def did_expire_order(self, expired_event: OrderExpiredEvent):
        """
        订单过期事件回调
        :param expired_event: 订单过期事件
        """
        self.logger().info(f"订单 {expired_event.order_id} 已过期.")

    @property
    def tracked_limit_orders(self) -> List[Tuple[ConnectorBase, LimitOrder]]:
        return self._sb_order_tracker.tracked_limit_orders

    @property
    def tracked_market_orders(self) -> List[Tuple[ConnectorBase, MarketOrder]]:
        return self._sb_order_tracker.tracked_market_orders

    def start(self, clock: Clock, timestamp: float):
        """
        开始策略
        :param clock: 时钟对象
        :param timestamp: 时间戳
        """
        super().start(clock, timestamp)
        self._last_timestamp = timestamp

    def stop(self, clock: Clock):
        """
        停止策略
        :param clock: 时钟对象
        """
        super().stop(clock)
        if self._main_task is not None:
            self._main_task.cancel()
            self._main_task = None 