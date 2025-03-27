import asyncio
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict
from datetime import datetime

from bidict import bidict

from hummingbot.connector.derivative.zbit_perpetual import zbit_perpetual_constants as CONSTANTS
from hummingbot.connector.derivative.zbit_perpetual import zbit_perpetual_utils as utils
from hummingbot.connector.derivative.zbit_perpetual import zbit_perpetual_web_utils as web_utils
from hummingbot.connector.derivative.zbit_perpetual.zbit_perpetual_api_order_book_data_source import ZbitPerpetualAPIOrderBookDataSource
from hummingbot.connector.derivative.zbit_perpetual.zbit_perpetual_auth import ZbitPerpetualAuth
from hummingbot.connector.perpetual_derivative_py_base import PerpetualDerivativePyBase
from hummingbot.connector.trading_rule import TradingRule
from hummingbot.connector.utils import combine_to_hb_trading_pair
from hummingbot.core.api_throttler.async_throttler import AsyncThrottler
from hummingbot.core.data_type.common import OrderType, PositionAction, PositionMode, PositionSide, TradeType
from hummingbot.core.data_type.funding_info import FundingInfo
from hummingbot.core.data_type.in_flight_order import InFlightOrder, OrderState, OrderUpdate, TradeUpdate
from hummingbot.core.data_type.perpetual_api_order_book_data_source import PerpetualAPIOrderBookDataSource
from hummingbot.core.data_type.trade_fee import AddedToCostTradeFee, TokenAmount, TradeFeeBase
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.core.utils.async_utils import safe_gather
from hummingbot.core.utils.estimate_fee import build_perpetual_trade_fee
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
from hummingbot.connector.derivative.position import Position
from hummingbot.core.data_type.cancellation_result import CancellationResult
from hummingbot.core.data_type.order_book_tracker_data_source import OrderBookTrackerDataSource
from hummingbot.core.data_type.limit_order import LimitOrder
from hummingbot.core.event.events import (
    MarketEvent,
    BuyOrderCompletedEvent,
    SellOrderCompletedEvent,
    OrderCancelledEvent,
    OrderFilledEvent,
    FundingPaymentCompletedEvent,
    MarketOrderFailureEvent,
    PositionModeChangeEvent,
)
from hummingbot.core.network_iterator import NetworkStatus
from hummingbot.core.utils.async_utils import safe_ensure_future
from hummingbot.core.utils.tracking_nonce import get_tracking_nonce
from hummingbot.connector.derivative_base import DerivativeBase


class ZbitPerpetualDerivative(PerpetualDerivativePyBase):
    """
    ZBit永续合约衍生品交易所连接器
    """
    
    web_utils = web_utils
    
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        trading_pairs: List[str] = None,
        trading_required: bool = True,
        domain: str = CONSTANTS.DEFAULT_DOMAIN,
    ):
        """
        初始化ZBit永续合约连接器
        :param api_key: API密钥
        :param api_secret: API密钥密码
        :param trading_pairs: 交易对列表
        :param trading_required: 是否需要交易
        :param domain: API域
        """
        self._api_key = api_key
        self._api_secret = api_secret
        self._trading_required = trading_required
        self._trading_pairs = trading_pairs or []
        self._domain = domain
        
        # 初始化限流器
        self._throttler = AsyncThrottler(CONSTANTS.RATE_LIMITS)
        
        # 初始化认证
        self._auth = ZbitPerpetualAuth(
            api_key=self._api_key,
            secret_key=self._api_secret,
        )
        
        # 初始化Web助手工厂
        self._web_assistants_factory = WebAssistantsFactory(
            throttler=self._throttler,
            auth=self._auth,
        )
        
        # 初始化交易对符号映射
        self._trading_pair_symbol_map = {}
        self._symbol_trading_pair_map = {}
        
        # 初始化交易规则
        self._trading_rules = {}
        
        # 初始化最后更新时间
        self._last_poll_timestamp = 0
        self._funding_fee_poll_notifier = asyncio.Event()
        self._status_poll_notifier = asyncio.Event()
        self._order_book_poll_notifier = asyncio.Event()
        self._last_timestamp = 0
        
        # 初始化任务
        self._set_trading_pair_symbol_map_task = None
        self._funding_fee_polling_task = None
        self._user_stream_tracker_task = None
        self._user_funding_fee_polling_task = None
        
        # 初始化其他属性
        self._next_funding_fee_timestamp = 0
        
        # 调用父类构造函数
        super().__init__(client_config_map=None) 

    @property
    def name(self) -> str:
        """获取交易所名称"""
        return CONSTANTS.EXCHANGE_NAME

    @property
    def domain(self) -> str:
        """获取交易所域"""
        return self._domain

    @property
    def client_order_id_prefix(self) -> str:
        """获取客户端订单ID前缀"""
        return "hbot"

    @property
    def trading_rules(self) -> Dict[str, TradingRule]:
        """获取交易规则"""
        return self._trading_rules

    @property
    def in_flight_orders(self) -> Dict[str, InFlightOrder]:
        """获取进行中的订单"""
        return self._order_tracker.active_orders

    @property
    def status_dict(self) -> Dict[str, bool]:
        """获取状态字典"""
        status = {
            "order_books_initialized": len(self._order_book_tracker.order_books) > 0,
            "account_balance": len(self._account_balances) > 0 if self._trading_required else True,
            "trading_rule_initialized": len(self._trading_rules) > 0,
            "position_mode_set": self._position_mode_ready,
            "funding_info_available": len(self._funding_info) > 0,
            "user_stream_initialized": self._user_stream_tracker.data_source.last_recv_time > 0 if self._trading_required else True,
        }
        return status

    def supported_position_modes(self) -> List[PositionMode]:
        """获取支持的仓位模式"""
        return [PositionMode.ONEWAY, PositionMode.HEDGE]

    def _is_request_exception_related_to_time_synchronizer(self, request_exception: Exception) -> bool:
        """判断请求异常是否与时间同步器相关"""
        error_description = str(request_exception)
        return "timestamp" in error_description.lower() and "recvWindow" in error_description

    def _create_order_book_data_source(self) -> PerpetualAPIOrderBookDataSource:
        """创建订单簿数据源"""
        return ZbitPerpetualAPIOrderBookDataSource(
            trading_pairs=self._trading_pairs,
            throttler=self._throttler,
            domain=self._domain,
        )

    def _create_user_stream_tracker_data_source(self) -> UserStreamTrackerDataSource:
        """创建用户流数据源"""
        # 如果我们需要实现一个用户流追踪器，我们会在这里创建它
        # 在这个示例中，我们暂时返回None
        return None

    def _get_fee(
        self,
        base_currency: str,
        quote_currency: str,
        order_type: OrderType,
        order_side: TradeType,
        position_action: PositionAction,
        amount: Decimal,
        price: Decimal = Decimal("0"),
        is_maker: Optional[bool] = None,
    ) -> TradeFeeBase:
        """获取交易费用"""
        is_maker = order_type is OrderType.LIMIT_MAKER
        fee = build_perpetual_trade_fee(
            self.name,
            is_maker,
            base_currency=base_currency,
            quote_currency=quote_currency,
            order_type=order_type,
            order_side=order_side,
            position_action=position_action,
            amount=amount,
            price=price,
        )
        return fee

    async def _trading_pair_position_mode_set(self, mode: PositionMode, trading_pair: str) -> Tuple[bool, str]:
        """设置交易对的仓位模式"""
        try:
            pos_mode = CONSTANTS.POSITION_MODE_HEDGE if mode == PositionMode.HEDGE else CONSTANTS.POSITION_MODE_ONEWAY
            data = {
                "symbol": await self.exchange_symbol_associated_to_pair(trading_pair=trading_pair),
                "positionSide": pos_mode,
            }
            
            resp = await self._api_post(
                path_url="positionSide/dual",
                data=data,
                is_auth_required=True,
            )
            
            if resp.get("code") == 200:
                return True, ""
            else:
                return False, resp.get("msg", "Unknown error")
        except Exception as e:
            return False, str(e)

    async def _set_trading_pair_leverage(self, trading_pair: str, leverage: int) -> Tuple[bool, str]:
        """设置交易对的杠杆"""
        try:
            data = {
                "symbol": await self.exchange_symbol_associated_to_pair(trading_pair=trading_pair),
                "leverage": leverage,
            }
            
            resp = await self._api_post(
                path_url="leverage",
                data=data,
                is_auth_required=True,
            )
            
            if resp.get("code") == 200:
                return True, ""
            else:
                return False, resp.get("msg", "Unknown error")
        except Exception as e:
            return False, str(e)

    async def _place_order(
        self,
        order_id: str,
        trading_pair: str,
        amount: Decimal,
        trade_type: TradeType,
        order_type: OrderType,
        price: Decimal,
        position_action: PositionAction = PositionAction.NIL,
        **kwargs,
    ) -> Tuple[str, float]:
        """下单"""
        try:
            symbol = await self.exchange_symbol_associated_to_pair(trading_pair=trading_pair)
            data = {
                "symbol": symbol,
                "side": utils.map_order_side(trade_type, position_action),
                "type": utils.map_order_type(order_type),
                "quantity": str(amount),
                "newClientOrderId": order_id,
            }
            
            if order_type != OrderType.MARKET:
                data["price"] = str(price)
            
            resp = await self._api_post(
                path_url="order",
                data=data,
                is_auth_required=True,
            )
            
            if resp.get("code") == 200:
                exchange_order_id = str(resp.get("orderId", ""))
                return exchange_order_id, self.current_timestamp
            else:
                raise IOError(f"Error submitting order: {resp.get('msg', '')}")
        except Exception as e:
            self.logger().error(f"Error submitting {trade_type.name} {order_type.name} order to ZBit Perpetual for "
                                f"{amount} {trading_pair} at {price}.")
            self.logger().error(str(e))
            raise

    async def _update_trading_rules(self):
        """更新交易规则"""
        exchange_info = await self._api_get(
            path_url="exchangeInfo",
            is_auth_required=False,
        )
        
        trading_rules_list = self._format_trading_rules(exchange_info)
        self._trading_rules.clear()
        for trading_rule in trading_rules_list:
            self._trading_rules[trading_rule.trading_pair] = trading_rule
        
    def _format_trading_rules(self, exchange_info_dict: Dict[str, Any]) -> List[TradingRule]:
        """格式化交易规则"""
        rules = []
        for symbol_data in exchange_info_dict.get("symbols", []):
            if utils.is_exchange_information_valid(symbol_data):
                try:
                    trading_rule = utils.build_trading_rule(symbol_data)
                    if trading_rule is not None:
                        rules.append(trading_rule)
                except Exception:
                    self.logger().error(f"Error parsing trading rule {symbol_data}. Skipping.", exc_info=True)
        return rules 

    async def _api_get(
        self,
        path_url: str,
        params: Optional[Dict[str, Any]] = None,
        is_auth_required: bool = False,
    ) -> Dict[str, Any]:
        """
        发送GET请求到API
        """
        try:
            return await web_utils.api_request(
                path=path_url,
                api_factory=self._web_assistants_factory,
                throttler=self._throttler,
                domain=self._domain,
                params=params,
                method="GET",
                is_auth_required=is_auth_required,
            )
        except Exception as e:
            self.logger().error(f"Error making GET request to {path_url}: {str(e)}")
            raise

    async def _api_post(
        self,
        path_url: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        is_auth_required: bool = False,
    ) -> Dict[str, Any]:
        """
        发送POST请求到API
        """
        try:
            return await web_utils.api_request(
                path=path_url,
                api_factory=self._web_assistants_factory,
                throttler=self._throttler,
                domain=self._domain,
                params=params,
                data=data,
                method="POST",
                is_auth_required=is_auth_required,
            )
        except Exception as e:
            self.logger().error(f"Error making POST request to {path_url}: {str(e)}")
            raise

    async def _update_positions(self):
        """
        更新仓位信息
        """
        if not self._trading_required:
            return

        try:
            positions_response = await self._api_get(
                path_url="positions",
                is_auth_required=True,
            )

            positions = positions_response.get("positions", [])
            for position_data in positions:
                # 解析仓位数据
                position_id = f"{position_data['symbol']}_{position_data['positionSide']}"
                trading_pair = await self.trading_pair_associated_to_exchange_symbol(symbol=position_data["symbol"])
                position_side = position_data["positionSide"]
                amount = Decimal(str(position_data["positionAmt"]))
                entry_price = Decimal(str(position_data["entryPrice"]))
                unrealized_pnl = Decimal(str(position_data["unrealizedProfit"]))
                leverage = Decimal(str(position_data["leverage"]))

                # 更新保存在连接器中的仓位数据
                position = self._account_positions.get(position_id)
                if position is not None:
                    position.update_position(
                        amount=amount,
                        price=entry_price,
                        unrealized_pnl=unrealized_pnl,
                    )
                else:
                    # 创建一个新的仓位对象
                    from hummingbot.connector.derivative.position import Position
                    from hummingbot.core.data_type.common import PositionSide

                    position = Position(
                        trading_pair=trading_pair,
                        position_side=PositionSide.LONG if position_side == "LONG" else PositionSide.SHORT,
                        unrealized_pnl=unrealized_pnl,
                        entry_price=entry_price,
                        amount=amount,
                        leverage=leverage,
                    )
                    self._account_positions[position_id] = position

        except Exception as e:
            self.logger().error(f"Error updating positions: {str(e)}", exc_info=True)

    async def _fetch_last_fee_payment(self, trading_pair: str) -> Tuple[float, Decimal, Decimal]:
        """
        获取最后一次资金费用支付
        :param trading_pair: 交易对
        :return: 最后支付时间戳、费率、支付金额
        """
        try:
            symbol = await self.exchange_symbol_associated_to_pair(trading_pair=trading_pair)
            income_history = await self._api_get(
                path_url="income",
                params={
                    "symbol": symbol,
                    "incomeType": "FUNDING_FEE",
                    "limit": 1,  # 仅获取最后一个
                },
                is_auth_required=True,
            )

            if income_history and len(income_history) > 0:
                last_income = income_history[0]
                timestamp = float(last_income["time"]) / 1000.0  # 转换为秒
                funding_rate = Decimal(str(last_income["rate"]))
                payment_amount = Decimal(str(last_income["income"]))
                return timestamp, funding_rate, payment_amount
            else:
                # 如果没有历史记录，返回默认值
                return 0, Decimal("-1"), Decimal("-1")
        except Exception as e:
            self.logger().error(f"Error fetching last fee payment for {trading_pair}: {str(e)}", exc_info=True)
            return 0, Decimal("-1"), Decimal("-1")

    async def get_funding_info(self, trading_pair: str) -> FundingInfo:
        """
        获取资金费用信息
        :param trading_pair: 交易对
        :return: 资金费用信息
        """
        try:
            exchange_symbol = await self.exchange_symbol_associated_to_pair(trading_pair=trading_pair)
            funding_info_response = await self._api_get(
                path_url="fundingInfo",
                params={"symbol": exchange_symbol},
                is_auth_required=False,
            )

            # 解析响应数据
            funding_rate = Decimal(str(funding_info_response.get("fundingRate", "0")))
            next_funding_time = int(funding_info_response.get("nextFundingTime", 0)) / 1000.0  # 转换为秒
            index_price = Decimal(str(funding_info_response.get("indexPrice", "0")))
            mark_price = Decimal(str(funding_info_response.get("markPrice", "0")))

            return FundingInfo(
                trading_pair=trading_pair,
                index_price=index_price,
                mark_price=mark_price,
                next_funding_utc_timestamp=next_funding_time,
                rate=funding_rate,
            )
        except Exception as e:
            self.logger().error(f"Error getting funding info for {trading_pair}: {str(e)}", exc_info=True)
            raise

    async def exchange_symbol_associated_to_pair(self, trading_pair: str) -> str:
        """
        获取与交易对关联的交易所符号
        :param trading_pair: Hummingbot格式的交易对
        :return: 交易所格式的交易对符号
        """
        if trading_pair not in self._trading_pair_symbol_map:
            symbol_map = await self.trading_pair_symbol_map()
            try:
                symbol = symbol_map.inverse.get(trading_pair)
                if symbol is None:
                    base, quote = trading_pair.split("-")
                    symbol = f"{base}{quote}"
            except KeyError:
                # 如果在映射中未找到，则使用简单的转换（例如BTC-USDT -> BTCUSDT）
                base, quote = trading_pair.split("-")
                symbol = f"{base}{quote}"
            self._trading_pair_symbol_map[trading_pair] = symbol
        return self._trading_pair_symbol_map[trading_pair]

    async def trading_pair_associated_to_exchange_symbol(self, symbol: str) -> str:
        """
        获取与交易所符号关联的交易对
        :param symbol: 交易所格式的交易对符号
        :return: Hummingbot格式的交易对
        """
        symbol_map = await self.trading_pair_symbol_map()
        try:
            trading_pair = symbol_map.get(symbol)
            if trading_pair is None:
                # 尝试自动解析交易对
                base, quote = utils.get_pair_from_exchange_symbol(symbol)
                trading_pair = f"{base}-{quote}"
        except KeyError:
            # 如果在映射中未找到，则使用utils中的函数解析
            base, quote = utils.get_pair_from_exchange_symbol(symbol)
            trading_pair = f"{base}-{quote}"
        return trading_pair

    async def trading_pair_symbol_map(self) -> bidict:
        """
        获取交易对符号映射
        :return: 交易对符号映射的双向字典
        """
        if not self._symbol_trading_pair_map:
            try:
                exchange_info = await self._api_get(
                    path_url="exchangeInfo",
                    is_auth_required=False,
                )
                self._initialize_trading_pair_symbols_from_exchange_info(exchange_info)
            except Exception as e:
                self.logger().error(f"Error getting symbol map: {str(e)}", exc_info=True)
        return bidict(self._symbol_trading_pair_map)

    def _initialize_trading_pair_symbols_from_exchange_info(self, exchange_info: Dict[str, Any]):
        """
        从交易所信息初始化交易对符号映射
        :param exchange_info: 交易所信息
        """
        mapping = bidict()
        try:
            for symbol_data in exchange_info.get("symbols", []):
                if not utils.is_exchange_information_valid(symbol_data):
                    continue
                
                exchange_symbol = symbol_data["symbol"]
                base_asset = symbol_data["baseAsset"]
                quote_asset = symbol_data["quoteAsset"]
                
                # 创建Hummingbot格式的交易对
                trading_pair = combine_to_hb_trading_pair(base=base_asset, quote=quote_asset)
                
                # 添加到映射中
                mapping[exchange_symbol] = trading_pair
        except Exception as e:
            self.logger().error(f"Error initializing trading pair symbols: {str(e)}", exc_info=True)
        
        self._symbol_trading_pair_map = mapping 

    async def _update_balances(self):
        """
        更新账户余额
        """
        if not self._trading_required:
            return

        try:
            account_info = await self._api_get(
                path_url="account",
                is_auth_required=True,
            )

            # 处理账户资产信息
            for asset_balance in account_info.get("assets", []):
                asset_name = asset_balance["asset"]
                free_balance = Decimal(str(asset_balance["availableBalance"]))
                total_balance = Decimal(str(asset_balance["walletBalance"]))
                
                self._account_balances[asset_name] = total_balance
                self._account_available_balances[asset_name] = free_balance
                
            # 处理仓位信息，所需的保证金会影响可用余额
            # 这部分逻辑可能需要根据交易所API的具体返回结构进行调整
            for position in account_info.get("positions", []):
                if float(position.get("positionAmt", "0")) != 0:
                    continue
                position_margin = Decimal(str(position.get("initialMargin", "0")))
                asset = position.get("marginAsset", "")
                if asset in self._account_available_balances:
                    self._account_available_balances[asset] = self._account_available_balances[asset] - position_margin
                    
        except Exception as e:
            self.logger().error(f"Error updating balances: {str(e)}", exc_info=True)
            raise

    async def _user_stream_event_listener(self):
        """
        处理用户WebSocket事件
        """
        async for event_message in self._user_stream_tracker.user_stream:
            try:
                # 根据交易所WebSocket API的响应格式解析事件类型
                event_type = event_message.get("e", "")
                
                # 处理账户更新事件
                if event_type == "ACCOUNT_UPDATE":
                    await self._process_account_update(event_message)
                    
                # 处理订单更新事件
                elif event_type == "ORDER_TRADE_UPDATE":
                    await self._process_order_update(event_message)
                    
                # 处理杠杆更新事件
                elif event_type == "MARGIN_CALL":
                    await self._process_margin_call_update(event_message)
                    
                # 处理资金费率更新事件
                elif event_type == "FUNDING_UPDATE":
                    await self._process_funding_update(event_message)
                    
                # 处理仓位更新事件
                elif event_type == "POSITION_UPDATE":
                    await self._process_position_update(event_message)
                    
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.logger().error(f"Error processing user event: {str(e)}", exc_info=True)

    async def _process_account_update(self, event_message: Dict[str, Any]):
        """
        处理账户更新事件
        """
        account_data = event_message.get("a", {})
        
        # 更新余额
        for balance_data in account_data.get("B", []):
            asset = balance_data.get("a", "")
            free_balance = Decimal(str(balance_data.get("f", "0")))
            total_balance = Decimal(str(balance_data.get("wb", "0")))
            
            self._account_balances[asset] = total_balance
            self._account_available_balances[asset] = free_balance
            
        # 更新仓位
        for position_data in account_data.get("P", []):
            symbol = position_data.get("s", "")
            amount = Decimal(str(position_data.get("pa", "0")))
            entry_price = Decimal(str(position_data.get("ep", "0")))
            unrealized_pnl = Decimal(str(position_data.get("up", "0")))
            margin_type = position_data.get("mt", "")
            position_side = position_data.get("ps", "")
            
            position_id = f"{symbol}_{position_side}"
            trading_pair = await self.trading_pair_associated_to_exchange_symbol(symbol=symbol)
            
            # 如果仓位不存在，创建新的仓位对象
            if position_id not in self._account_positions:
                from hummingbot.connector.derivative.position import Position
                from hummingbot.core.data_type.common import PositionSide
                
                self._account_positions[position_id] = Position(
                    trading_pair=trading_pair,
                    position_side=PositionSide.LONG if position_side == "LONG" else PositionSide.SHORT,
                    unrealized_pnl=unrealized_pnl,
                    entry_price=entry_price,
                    amount=amount,
                    leverage=self._leverages.get(trading_pair, Decimal("1")),
                )
            else:
                # 更新现有仓位
                position = self._account_positions[position_id]
                position.update_position(
                    amount=amount,
                    price=entry_price,
                    unrealized_pnl=unrealized_pnl,
                )
                
            # 更新保证金类型
            self._margin_types[trading_pair] = margin_type
            
            # 如果仓位为0，则从字典中删除
            if amount == Decimal("0"):
                if position_id in self._account_positions:
                    del self._account_positions[position_id]

    async def _process_order_update(self, event_message: Dict[str, Any]):
        """
        处理订单更新事件
        """
        order_data = event_message.get("o", {})
        client_order_id = order_data.get("c", "")
        
        # 检查订单ID是否在跟踪中
        tracked_order = self._order_tracker.all_fillable_orders.get(client_order_id)
        if tracked_order is None:
            self.logger().debug(f"Unrecognized order update received: {event_message}")
            return
            
        # 获取交易对
        exchange_symbol = order_data.get("s", "")
        trading_pair = await self.trading_pair_associated_to_exchange_symbol(exchange_symbol)
        
        # 解析订单状态
        order_status = order_data.get("X", "")
        filled_amount = Decimal(str(order_data.get("z", "0")))
        remaining_amount = Decimal(str(order_data.get("q", "0"))) - filled_amount
        order_price = Decimal(str(order_data.get("p", "0")))
        order_type = order_data.get("o", "")
        
        # 检查订单是否已完成或已取消
        is_completed = order_status in {"FILLED", "CANCELED", "EXPIRED", "REJECTED"}
        is_cancelled = order_status == "CANCELED"
        is_failed = order_status == "REJECTED"
        
        # 更新订单状态
        if is_completed:
            if is_cancelled:
                self._order_tracker.process_order_canceled(client_order_id=client_order_id)
            elif is_failed:
                self._order_tracker.process_order_failure(client_order_id=client_order_id)
            else:  # 订单成功完成
                self._order_tracker.process_order_completed(
                    client_order_id=client_order_id,
                    exchange_order_id=order_data.get("i", ""),
                    trading_pair=trading_pair,
                    trade_type=TradeType.BUY if order_data.get("S", "") == "BUY" else TradeType.SELL,
                    order_type=OrderType.LIMIT if order_type == "LIMIT" else OrderType.MARKET,
                    trade_fee=self._get_fee(
                        trading_pair=trading_pair,
                        order_type=OrderType.LIMIT if order_type == "LIMIT" else OrderType.MARKET,
                        trade_type=TradeType.BUY if order_data.get("S", "") == "BUY" else TradeType.SELL,
                        amount=filled_amount,
                        price=order_price,
                    ),
                )
        # 订单部分成交
        elif "PARTIALLY_FILLED" == order_status:
            # 获取成交信息
            trade_id = f"{client_order_id}_{order_data.get('i', '')}_{order_data.get('t', '')}"
            fee_asset = order_data.get("N", "")  # 手续费资产
            fee_amount = Decimal(str(order_data.get("n", "0")))  # 手续费金额
            trade_price = Decimal(str(order_data.get("L", "0")))  # 成交价格
            trade_amount = Decimal(str(order_data.get("l", "0")))  # 本次成交数量
            order_execute_time = int(order_data.get("T", 0)) / 1000.0  # 成交时间（毫秒转秒）
            
            # 创建成交费用对象
            trade_fee = AddedToCostTradeFee(
                flat_fees=[TokenAmount(token=fee_asset, amount=fee_amount)]
            )
            
            # 处理部分成交
            self._order_tracker.process_trade_update(
                trade_id=trade_id,
                client_order_id=client_order_id,
                exchange_order_id=order_data.get("i", ""),
                trading_pair=trading_pair,
                trade_type=TradeType.BUY if order_data.get("S", "") == "BUY" else TradeType.SELL,
                order_type=OrderType.LIMIT if order_type == "LIMIT" else OrderType.MARKET,
                price=trade_price,
                amount=trade_amount,
                trade_fee=trade_fee,
                exchange_trade_id=order_data.get("t", ""),
                timestamp=order_execute_time,
            )

    async def _process_margin_call_update(self, event_message: Dict[str, Any]):
        """
        处理保证金预警事件
        """
        # 根据交易所API实现保证金预警处理逻辑
        margin_call_data = event_message.get("mc", {})
        
        for position_data in margin_call_data.get("p", []):
            symbol = position_data.get("s", "")
            position_side = position_data.get("ps", "")
            margin_ratio = Decimal(str(position_data.get("mr", "0")))
            
            trading_pair = await self.trading_pair_associated_to_exchange_symbol(symbol=symbol)
            
            # 记录保证金预警日志
            self.logger().warning(
                f"Margin call for {trading_pair} ({position_side}): "
                f"Current margin ratio: {margin_ratio}."
            )
            
            # 这里可以添加其他处理逻辑，如自动减仓等

    async def _process_funding_update(self, event_message: Dict[str, Any]):
        """
        处理资金费率更新事件
        """
        funding_data = event_message.get("f", {})
        
        symbol = funding_data.get("s", "")
        funding_rate = Decimal(str(funding_data.get("r", "0")))
        funding_time = int(funding_data.get("T", 0)) / 1000.0  # 毫秒转秒
        
        trading_pair = await self.trading_pair_associated_to_exchange_symbol(symbol=symbol)
        
        # 更新资金费率信息
        if trading_pair in self._funding_info:
            funding_info = self._funding_info[trading_pair]
            funding_info.rate = funding_rate
            funding_info.next_funding_utc_timestamp = funding_time
        else:
            # 如果没有现有信息，创建新的资金费率信息对象
            self._funding_info[trading_pair] = FundingInfo(
                trading_pair=trading_pair,
                index_price=Decimal("0"),  # 这些值稍后会更新
                mark_price=Decimal("0"),
                next_funding_utc_timestamp=funding_time,
                rate=funding_rate,
            )
            
        # 记录资金费率更新
        self.logger().info(
            f"Funding rate updated for {trading_pair}: "
            f"Rate: {funding_rate}, Next funding time: {datetime.fromtimestamp(funding_time).isoformat()}"
        )

    async def _process_position_update(self, event_message: Dict[str, Any]):
        """
        处理仓位更新事件
        """
        # 如果交易所有专门的仓位更新事件，在这里处理
        # 大多数情况下，仓位更新已经在账户更新中处理
        pass

    async def _status_polling_loop(self):
        """
        执行状态轮询循环
        """
        while True:
            try:
                # 更新订单状态
                await self._update_order_status()
                
                # 更新余额
                await self._update_balances()
                
                # 更新仓位
                await self._update_positions()
                
                # 更新交易规则
                await self._update_trading_rules()
                
                # 可选：更新资金费率
                # await self._update_funding_rates()
                
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.logger().error(f"Error in status polling loop: {str(e)}", exc_info=True)
            finally:
                await asyncio.sleep(self.STATUS_UPDATE_INTERVAL)

    async def _update_order_status(self):
        """
        更新订单状态
        """
        if not self._trading_required:
            return
            
        # 获取未完成订单ID列表
        tracked_orders = self._order_tracker.active_orders
        if not tracked_orders:
            return
            
        # 分批查询订单状态（避免请求过大）
        for batch_orders in self._split_orders_batches(list(tracked_orders.values())):
            order_symbols_map = {}
            exchange_client_order_id_map = {}
            
            for order in batch_orders:
                exchange_client_order_id_map[order.client_order_id] = order
                if order.trading_pair not in order_symbols_map:
                    order_symbols_map[order.trading_pair] = []
                order_symbols_map[order.trading_pair].append(order.client_order_id)
                
            try:
                for trading_pair, order_ids in order_symbols_map.items():
                    exchange_symbol = await self.exchange_symbol_associated_to_pair(trading_pair)
                    
                    # 查询所有未完成订单
                    open_orders = await self._api_get(
                        path_url="openOrders",
                        params={"symbol": exchange_symbol},
                        is_auth_required=True,
                    )
                    
                    # 创建一个客户端订单ID到订单数据的映射
                    client_id_to_order_map = {order.get("clientOrderId"): order for order in open_orders}
                    
                    # 检查每个跟踪的订单
                    for client_order_id in order_ids:
                        if client_order_id not in client_id_to_order_map:
                            # 如果订单不在未完成订单列表中，可能已经完成或被取消
                            # 查询订单详情以确认状态
                            order = exchange_client_order_id_map[client_order_id]
                            
                            try:
                                order_status = await self._api_get(
                                    path_url="order",
                                    params={
                                        "symbol": exchange_symbol,
                                        "origClientOrderId": client_order_id,
                                    },
                                    is_auth_required=True,
                                )
                                
                                # 处理订单状态
                                await self._process_order_status_response(order_status)
                            except Exception as e:
                                # 如果找不到订单，可能已经被取消或已经完成很长时间
                                if "Order does not exist" in str(e):
                                    self._order_tracker.process_order_not_found(client_order_id=client_order_id)
                                else:
                                    raise e
                        else:
                            # 处理未完成订单的状态
                            await self._process_order_status_response(client_id_to_order_map[client_order_id])
                            
            except Exception as e:
                self.logger().error(f"Error updating order status: {str(e)}", exc_info=True)

    def _split_orders_batches(self, orders: List[InFlightOrder]) -> List[List[InFlightOrder]]:
        """
        将订单分批处理
        :param orders: 订单列表
        :return: 分批后的订单列表
        """
        # 将订单分批，每批最多20个订单
        max_batch_size = 20
        return [orders[i:i + max_batch_size] for i in range(0, len(orders), max_batch_size)]

    async def _process_order_status_response(self, order_status: Dict[str, Any]):
        """
        处理订单状态响应
        :param order_status: 订单状态响应
        """
        client_order_id = order_status.get("clientOrderId")
        
        # 检查订单是否在跟踪中
        tracked_order = self._order_tracker.all_updatable_orders.get(client_order_id)
        if tracked_order is None:
            return
            
        # 获取交易对
        exchange_symbol = order_status.get("symbol")
        trading_pair = await self.trading_pair_associated_to_exchange_symbol(exchange_symbol)
        
        # 解析订单状态
        status = order_status.get("status")
        filled_amount = Decimal(str(order_status.get("executedQty", "0")))
        remaining_amount = Decimal(str(order_status.get("origQty", "0"))) - filled_amount
        order_price = Decimal(str(order_status.get("price", "0")))
        order_type = order_status.get("type")
        
        # 检查订单是否已完成
        is_completed = status in {"FILLED", "CANCELED", "EXPIRED", "REJECTED"}
        is_cancelled = status == "CANCELED"
        is_failed = status == "REJECTED"
        
        # 更新订单状态
        if is_completed:
            if is_cancelled:
                self._order_tracker.process_order_canceled(client_order_id=client_order_id)
            elif is_failed:
                self._order_tracker.process_order_failure(client_order_id=client_order_id)
            else:  # 订单成功完成
                self._order_tracker.process_order_completed(
                    client_order_id=client_order_id,
                    exchange_order_id=order_status.get("orderId", ""),
                    trading_pair=trading_pair,
                    trade_type=tracked_order.trade_type,
                    order_type=tracked_order.order_type,
                    trade_fee=self._get_fee(
                        trading_pair=tracked_order.trading_pair,
                        order_type=tracked_order.order_type,
                        trade_type=tracked_order.trade_type,
                        amount=filled_amount,
                        price=order_price,
                    ),
                )
        else:
            # 更新进行中的订单
            self._order_tracker.process_order_update(
                client_order_id=client_order_id,
                exchange_order_id=order_status.get("orderId", ""),
                trading_pair=trading_pair,
                new_state=OrderState.OPEN,
                update_timestamp=time.time(),
                new_executed_amount=filled_amount,
                new_remaining_amount=remaining_amount,
                new_price=order_price
            )

    async def _update_funding_rates(self):
        """
        更新资金费率信息
        """
        if not self._trading_required:
            return
            
        # 获取所有交易对
        trading_pairs = list(self._trading_rules.keys())
        
        for trading_pair in trading_pairs:
            try:
                # 获取资金费率信息
                funding_info = await self.get_funding_info(trading_pair)
                
                # 更新资金费率信息
                self._funding_info[trading_pair] = funding_info
                
            except Exception as e:
                self.logger().error(f"Error updating funding rates for {trading_pair}: {str(e)}", exc_info=True)
                
        self.logger().debug(f"Updated funding rates for {len(trading_pairs)} trading pairs.")

    async def _cancel_order(self, client_order_id: str) -> Dict[str, Any]:
        """
        取消特定的订单
        :param client_order_id: 客户端订单ID
        :return: 取消订单的响应
        """
        order = self._order_tracker.all_updatable_orders.get(client_order_id)
        if order is None:
            self.logger().error(f"Failed to cancel order {client_order_id}: Order not found in tracker.")
            # 传播取消失败的失败事件
            self._order_tracker.process_order_not_found(client_order_id)
            raise ValueError(f"Order {client_order_id} not found in order tracker")

        try:
            # 获取交易对的交易所符号
            exchange_symbol = await self.exchange_symbol_associated_to_pair(order.trading_pair)
            
            # 发送取消订单请求
            cancel_result = await self._api_post(
                path_url="cancel",
                data={
                    "symbol": exchange_symbol,
                    "origClientOrderId": client_order_id,
                },
                is_auth_required=True,
            )
            
            # 验证响应
            if cancel_result:
                # 记录取消订单的信息
                self.logger().info(f"Successfully canceled order {client_order_id}.")
                self._order_tracker.process_order_canceled(client_order_id)
                return cancel_result
            else:
                # 处理取消失败的情况
                self.logger().warning(f"Failed to cancel order {client_order_id}: No response from API.")
                raise Exception(f"Failed to cancel order {client_order_id}: No response from API")
                
        except Exception as e:
            self.logger().error(f"Failed to cancel order {client_order_id}: {str(e)}")
            # 如果API返回订单不存在，则认为订单已被处理
            if "Order does not exist" in str(e):
                self._order_tracker.process_order_not_found(client_order_id)
            raise e

    async def cancel(self, trading_pair: str, client_order_id: str) -> Dict[str, Any]:
        """
        取消订单的公开接口
        :param trading_pair: 交易对
        :param client_order_id: 客户端订单ID
        :return: 取消订单的响应
        """
        try:
            # 调用内部取消订单方法
            return await self._cancel_order(client_order_id)
        except Exception as e:
            # 处理任何错误并确保错误被正确记录和传播
            self.logger().error(f"Failed to cancel order {client_order_id} for {trading_pair}: {str(e)}")
            self._order_tracker.process_order_exception(client_order_id, e)
            raise

    async def cancel_all(self, timeout_seconds: float) -> List[CancellationResult]:
        """
        取消所有活跃订单
        :param timeout_seconds: 超时时间（秒）
        :return: 取消结果列表
        """
        # 设置取消操作的截止时间
        deadline = time.time() + timeout_seconds
        
        # 获取所有活跃订单
        tracked_orders = self._order_tracker.active_orders
        if not tracked_orders:
            return []
            
        # 存储取消结果
        cancellation_results = []
        
        # 按交易对分组订单，以便批量取消
        orders_by_trading_pair = defaultdict(list)
        for order in tracked_orders.values():
            orders_by_trading_pair[order.trading_pair].append(order)
            
        # 对每个交易对的订单进行批量取消
        for trading_pair, orders in orders_by_trading_pair.items():
            try:
                # 获取交易对的交易所符号
                exchange_symbol = await self.exchange_symbol_associated_to_pair(trading_pair)
                
                # 首先尝试批量取消所有订单
                try:
                    await self._api_post(
                        path_url="cancelAllOrders",
                        data={"symbol": exchange_symbol},
                        is_auth_required=True,
                    )
                    
                    # 对每个取消的订单更新状态并添加结果
                    for order in orders:
                        self._order_tracker.process_order_canceled(order.client_order_id)
                        cancellation_results.append(CancellationResult(order.client_order_id, True))
                except Exception as e:
                    self.logger().error(f"Failed to cancel all orders for {trading_pair}: {str(e)}")
                    
                    # 如果批量取消失败，则尝试逐个取消
                    for order in orders:
                        # 检查是否超时
                        if time.time() > deadline:
                            cancellation_results.append(CancellationResult(order.client_order_id, False))
                            continue
                            
                        try:
                            # 尝试取消单个订单
                            await self._cancel_order(order.client_order_id)
                            cancellation_results.append(CancellationResult(order.client_order_id, True))
                        except Exception as cancel_ex:
                            self.logger().error(f"Failed to cancel order {order.client_order_id}: {str(cancel_ex)}")
                            cancellation_results.append(CancellationResult(order.client_order_id, False))
            except Exception as e:
                self.logger().error(f"Error canceling orders for {trading_pair}: {str(e)}")
                # 添加所有未处理订单的失败结果
                for order in orders:
                    if not any(result.client_order_id == order.client_order_id for result in cancellation_results):
                        cancellation_results.append(CancellationResult(order.client_order_id, False))
                
        return cancellation_results
        
    async def cancel_by_exchange_order_id(self, exchange_order_id: str, trading_pair: str) -> Dict[str, Any]:
        """
        通过交易所订单ID取消订单
        :param exchange_order_id: 交易所订单ID
        :param trading_pair: 交易对
        :return: 取消订单的响应
        """
        try:
            # 获取交易对的交易所符号
            exchange_symbol = await self.exchange_symbol_associated_to_pair(trading_pair)
            
            # 发送取消订单请求
            cancel_result = await self._api_post(
                path_url="cancel",
                data={
                    "symbol": exchange_symbol,
                    "orderId": exchange_order_id,
                },
                is_auth_required=True,
            )
            
            # 验证响应
            if cancel_result:
                # 记录取消订单的信息
                self.logger().info(f"Successfully canceled order by exchange ID {exchange_order_id}.")
                
                # 查找并更新对应的客户端订单
                for client_order_id, order in self._order_tracker.all_orders.items():
                    if order.exchange_order_id == exchange_order_id:
                        self._order_tracker.process_order_canceled(client_order_id)
                        break
                        
                return cancel_result
            else:
                # 处理取消失败的情况
                self.logger().warning(f"Failed to cancel order by exchange ID {exchange_order_id}: No response from API.")
                raise Exception(f"Failed to cancel order by exchange ID {exchange_order_id}: No response from API")
                
        except Exception as e:
            self.logger().error(f"Failed to cancel order by exchange ID {exchange_order_id}: {str(e)}")
            raise e 

    async def set_leverage(self, trading_pair: str, leverage: int = 1):
        """
        设置交易对的杠杆
        :param trading_pair: 交易对
        :param leverage: 杠杆倍数
        """
        try:
            # 获取交易所符号
            exchange_symbol = await self.exchange_symbol_associated_to_pair(trading_pair)
            
            # 发送设置杠杆请求
            result = await self._api_post(
                path_url="leverage",
                data={
                    "symbol": exchange_symbol,
                    "leverage": leverage,
                },
                is_auth_required=True,
            )
            
            # 验证结果
            if result and "leverage" in result:
                # 更新杠杆记录
                self._leverages[trading_pair] = Decimal(str(result["leverage"]))
                self.logger().info(f"Leverage for {trading_pair} set to {leverage}x")
                
                # 通知策略杠杆已更改
                # 可以在这里发送事件，如果需要的话
                
                return result
            else:
                self.logger().error(f"Failed to set leverage for {trading_pair}: Unexpected response {result}")
                raise Exception(f"Failed to set leverage for {trading_pair}: Unexpected response {result}")
                
        except Exception as e:
            self.logger().error(f"Error setting leverage for {trading_pair}: {str(e)}", exc_info=True)
            raise

    async def get_account_summary(self) -> Dict[str, Any]:
        """
        获取账户摘要信息
        :return: 账户摘要信息
        """
        if not self._trading_required:
            return {}
            
        try:
            account_info = await self._api_get(
                path_url="account",
                is_auth_required=True,
            )
            
            # 处理返回的数据，提取关键信息
            summary = {
                "total_equity": Decimal(str(account_info.get("totalWalletBalance", "0"))),
                "available_balance": Decimal(str(account_info.get("availableBalance", "0"))),
                "margin_balance": Decimal(str(account_info.get("totalMarginBalance", "0"))),
                "unrealized_pnl": Decimal(str(account_info.get("totalUnrealizedProfit", "0"))),
                "maintenance_margin": Decimal(str(account_info.get("totalMaintMargin", "0"))),
                "initial_margin": Decimal(str(account_info.get("totalInitialMargin", "0"))),
            }
            
            # 计算保证金水平
            if summary["maintenance_margin"] > Decimal("0"):
                summary["margin_ratio"] = summary["margin_balance"] / summary["maintenance_margin"]
            else:
                summary["margin_ratio"] = Decimal("999")
                
            return summary
            
        except Exception as e:
            self.logger().error(f"Error retrieving account summary: {str(e)}", exc_info=True)
            raise

    async def get_position_mode(self) -> PositionMode:
        """
        获取账户的持仓模式
        :return: 持仓模式（单向或对冲）
        """
        try:
            position_mode_info = await self._api_get(
                path_url="positionSide/dual",
                is_auth_required=True,
            )
            
            # ZBit API可能返回不同的结构，需要根据实际情况调整
            is_hedge_mode = position_mode_info.get("dualSidePosition", False)
            
            return PositionMode.HEDGE if is_hedge_mode else PositionMode.ONEWAY
            
        except Exception as e:
            self.logger().error(f"Error retrieving position mode: {str(e)}", exc_info=True)
            # 默认返回单向模式
            return PositionMode.ONEWAY

    async def set_position_mode(self, position_mode: PositionMode):
        """
        设置账户的持仓模式
        :param position_mode: 持仓模式（单向或对冲）
        """
        if position_mode not in [PositionMode.HEDGE, PositionMode.ONEWAY]:
            raise ValueError(f"Invalid position mode: {position_mode}. Must be either HEDGE or ONEWAY.")
            
        try:
            # 确定API需要的值
            mode_value = position_mode == PositionMode.HEDGE
            
            # 发送设置请求
            result = await self._api_post(
                path_url="positionSide/dual",
                data={"dualSidePosition": mode_value},
                is_auth_required=True,
            )
            
            # 验证结果
            if result and result.get("code", -1) == 0:
                self.logger().info(f"Successfully set position mode to {position_mode.name}")
                return True
            else:
                error_msg = result.get("msg", "Unknown error") if result else "No response"
                self.logger().error(f"Failed to set position mode: {error_msg}")
                raise Exception(f"Failed to set position mode: {error_msg}")
                
        except Exception as e:
            self.logger().error(f"Error setting position mode: {str(e)}", exc_info=True)
            raise

    async def set_margin_type(self, trading_pair: str, margin_type: str = "CROSSED"):
        """
        设置交易对的保证金类型
        :param trading_pair: 交易对
        :param margin_type: 保证金类型（CROSSED 或 ISOLATED）
        """
        if margin_type not in ["CROSSED", "ISOLATED"]:
            raise ValueError(f"Invalid margin type: {margin_type}. Must be either CROSSED or ISOLATED.")
            
        try:
            # 获取交易所符号
            exchange_symbol = await self.exchange_symbol_associated_to_pair(trading_pair)
            
            # 发送设置请求
            result = await self._api_post(
                path_url="marginType",
                data={
                    "symbol": exchange_symbol,
                    "marginType": margin_type,
                },
                is_auth_required=True,
            )
            
            # 验证结果
            if result and result.get("code", -1) == 0:
                # 更新保证金类型记录
                self._margin_types[trading_pair] = margin_type
                self.logger().info(f"Margin type for {trading_pair} set to {margin_type}")
                return True
            else:
                error_msg = result.get("msg", "Unknown error") if result else "No response"
                self.logger().error(f"Failed to set margin type for {trading_pair}: {error_msg}")
                raise Exception(f"Failed to set margin type for {trading_pair}: {error_msg}")
                
        except Exception as e:
            self.logger().error(f"Error setting margin type for {trading_pair}: {str(e)}", exc_info=True)
            raise

    async def get_all_positions(self) -> List[Position]:
        """
        获取所有开放的仓位
        :return: 仓位列表
        """
        # 首先更新仓位信息
        await self._update_positions()
        
        # 返回当前仓位列表
        return list(self._account_positions.values())

    async def get_position(self, trading_pair: str, position_side: PositionSide = None) -> Optional[Position]:
        """
        获取特定交易对和方向的仓位
        :param trading_pair: 交易对
        :param position_side: 仓位方向（多头或空头）
        :return: 仓位对象，如果不存在则返回None
        """
        # 首先更新仓位信息
        await self._update_positions()
        
        # 获取交易所符号
        exchange_symbol = await self.exchange_symbol_associated_to_pair(trading_pair)
        
        # 确定仓位ID
        if position_side is None:
            # 如果不指定方向，首先检查当前的持仓模式
            position_mode = await self.get_position_mode()
            if position_mode == PositionMode.ONEWAY:
                # 单向模式，尝试获取默认的BOTH仓位
                position_id = f"{exchange_symbol}_BOTH"
            else:
                # 对冲模式，默认返回多头仓位
                position_id = f"{exchange_symbol}_LONG"
        else:
            # 如果指定了方向，直接使用该方向
            side_str = "LONG" if position_side == PositionSide.LONG else "SHORT"
            position_id = f"{exchange_symbol}_{side_str}"
            
        # 返回匹配的仓位
        return self._account_positions.get(position_id)

    async def get_funding_payment_history(self, trading_pair: str) -> List[Dict[str, Any]]:
        """
        获取资金费用支付历史
        :param trading_pair: 交易对
        :return: 资金费用支付历史列表
        """
        try:
            # 获取交易所符号
            exchange_symbol = await self.exchange_symbol_associated_to_pair(trading_pair)
            
            # 获取资金费用历史
            response = await self._api_get(
                path_url="income",
                params={
                    "symbol": exchange_symbol,
                    "incomeType": "FUNDING_FEE",
                    "limit": 100,  # 限制结果数量
                },
                is_auth_required=True,
            )
            
            # 处理响应数据
            funding_payments = []
            for payment in response:
                # 转换为标准格式
                funding_payments.append({
                    "timestamp": int(payment.get("time", 0)) / 1000.0,  # 毫秒转秒
                    "trading_pair": trading_pair,
                    "funding_rate": Decimal(str(payment.get("rate", "0"))),
                    "payment_amount": Decimal(str(payment.get("income", "0"))),
                    "payment_token": payment.get("asset", ""),
                })
                
            return funding_payments
            
        except Exception as e:
            self.logger().error(f"Error retrieving funding payment history for {trading_pair}: {str(e)}", exc_info=True)
            return []

    async def get_income_history(self, income_types: List[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        获取账户收入历史
        :param income_types: 收入类型列表（可选）
        :param limit: 结果数量限制
        :return: 收入历史列表
        """
        try:
            # 准备请求参数
            params = {"limit": limit}
            if income_types:
                params["incomeType"] = ",".join(income_types)
                
            # 获取收入历史
            response = await self._api_get(
                path_url="income",
                params=params,
                is_auth_required=True,
            )
            
            # 处理响应数据
            income_history = []
            for income in response:
                # 转换为标准格式
                income_history.append({
                    "timestamp": int(income.get("time", 0)) / 1000.0,  # 毫秒转秒
                    "symbol": income.get("symbol", ""),
                    "income_type": income.get("incomeType", ""),
                    "income": Decimal(str(income.get("income", "0"))),
                    "asset": income.get("asset", ""),
                    "info": income.get("info", ""),
                    "transaction_id": income.get("tranId", ""),
                })
                
            return income_history
            
        except Exception as e:
            self.logger().error(f"Error retrieving income history: {str(e)}", exc_info=True)
            return [] 