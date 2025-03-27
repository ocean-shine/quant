import asyncio
import logging
import time
from typing import Any, Dict, List, Mapping, Optional

from hummingbot.connector.derivative.zbit_perpetual import zbit_perpetual_constants as CONSTANTS
from hummingbot.connector.derivative.zbit_perpetual import zbit_perpetual_web_utils as web_utils
from hummingbot.core.api_throttler.async_throttler import AsyncThrottler
from hummingbot.core.data_type.common import TradeType
from hummingbot.core.data_type.order_book import OrderBook
from hummingbot.core.data_type.order_book_message import OrderBookMessage, OrderBookMessageType
from hummingbot.core.data_type.perpetual_api_order_book_data_source import PerpetualAPIOrderBookDataSource
from hummingbot.core.web_assistant.connections.data_types import RESTMethod, WSJSONRequest
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
from hummingbot.logger import HummingbotLogger


class ZbitPerpetualAPIOrderBookDataSource(PerpetualAPIOrderBookDataSource):
    """
    ZBit永续合约订单簿数据源
    """
    
    _logger: Optional[HummingbotLogger] = None
    
    def __init__(
        self,
        trading_pairs: List[str],
        throttler: Optional[AsyncThrottler] = None,
        domain: str = CONSTANTS.DEFAULT_DOMAIN,
    ):
        """
        初始化订单簿数据源
        """
        super().__init__(trading_pairs)
        self._trading_pairs: List[str] = trading_pairs
        self._throttler = throttler or AsyncThrottler(CONSTANTS.RATE_LIMITS)
        self._domain = domain
        self._api_factory: Optional[WebAssistantsFactory] = None
        self._last_ws_message_sent_timestamp = 0
        self._ws_connect_lock = asyncio.Lock()
        
    @classmethod
    def logger(cls) -> HummingbotLogger:
        """
        获取日志记录器
        """
        if cls._logger is None:
            cls._logger = logging.getLogger(__name__)
        return cls._logger
    
    @property
    def throttler(self) -> AsyncThrottler:
        """
        获取API限流器
        """
        return self._throttler
    
    @property
    def api_factory(self) -> WebAssistantsFactory:
        """
        获取Web助手工厂
        """
        if self._api_factory is None:
            self._api_factory = web_utils.build_api_factory(throttler=self._throttler)
        return self._api_factory
    
    async def get_last_traded_prices(self, trading_pairs: List[str]) -> Dict[str, float]:
        """
        获取最后交易价格
        :param trading_pairs: 交易对列表
        :return: 交易对与价格的映射
        """
        result = {}
        
        for trading_pair in trading_pairs:
            try:
                # 查询交易对的Ticker信息
                response = await web_utils.api_request(
                    path="ticker/price",
                    api_factory=self.api_factory,
                    throttler=self._throttler,
                    params={"symbol": trading_pair.replace("-", "")},
                    domain=self._domain,
                    method=RESTMethod.GET,
                    limit_id=CONSTANTS.EXCHANGE_INFO_URL,
                )
                
                if "price" in response:
                    result[trading_pair] = float(response["price"])
            except Exception as e:
                self.logger().warning(f"Error fetching last traded price for {trading_pair}: {e}")
        
        return result
    
    async def get_snapshot(self, trading_pair: str) -> OrderBookMessage:
        """
        获取订单簿快照
        :param trading_pair: 交易对
        :return: 订单簿消息
        """
        try:
            # 将Hummingbot格式的交易对转换为交易所格式
            exchange_trading_pair = trading_pair.replace("-", "")
            
            # 获取订单簿快照
            response = await web_utils.api_request(
                path="depth",
                api_factory=self.api_factory,
                throttler=self._throttler,
                params={"symbol": exchange_trading_pair, "limit": 1000},  # 使用最大深度
                domain=self._domain,
                method=RESTMethod.GET,
                limit_id=CONSTANTS.ORDER_BOOK_URL,
            )
            
            # 解析订单簿数据
            timestamp = int(time.time() * 1000)  # 使用本地时间，因为响应中可能没有时间戳
            if "lastUpdateId" in response:
                timestamp = response.get("time", timestamp)  # 如果有时间则使用，否则使用本地时间
            
            # 构建订单簿消息
            snapshot_msg = OrderBookMessage(
                message_type=OrderBookMessageType.SNAPSHOT,
                content={
                    "trading_pair": trading_pair,
                    "update_id": response.get("lastUpdateId", 0),
                    "bids": [
                        [float(price), float(amount)]
                        for price, amount in response.get("bids", [])
                    ],
                    "asks": [
                        [float(price), float(amount)]
                        for price, amount in response.get("asks", [])
                    ],
                },
                timestamp=timestamp / 1000.0,  # 转换为秒
            )
            
            return snapshot_msg
        except Exception as e:
            self.logger().error(f"Error getting order book snapshot for {trading_pair}: {e}", exc_info=True)
            raise
    
    async def listen_for_subscriptions(self):
        """
        监听订阅的交易对数据
        """
        while True:
            try:
                # 为每个交易对创建一个 WebSocket 连接
                for trading_pair in self._trading_pairs:
                    async with self._ws_connect_lock:
                        # 确保连接之间有足够间隔，避免触发限流
                        if time.time() - self._last_ws_message_sent_timestamp < 1:
                            await asyncio.sleep(1)
                        
                        # 获取 WebSocket 助手
                        ws = await self.api_factory.get_ws_assistant()
                        
                        # 连接到 WebSocket
                        await ws.connect(ws_url=CONSTANTS.WSS_URL_PUBLIC)
                        self._last_ws_message_sent_timestamp = time.time()
                        
                        # 订阅订单簿更新
                        exchange_trading_pair = trading_pair.replace("-", "")
                        orderbook_params = {
                            "method": CONSTANTS.WS_SUBSCRIPTION_URL,
                            "params": [f"{CONSTANTS.WS_ORDERBOOK_CHANNEL}@{exchange_trading_pair}"],
                            "id": int(time.time() * 1000),
                        }
                        subscribe_orderbook_request = WSJSONRequest(payload=orderbook_params)
                        await ws.send(subscribe_orderbook_request)
                        
                        # 订阅交易更新
                        trade_params = {
                            "method": CONSTANTS.WS_SUBSCRIPTION_URL,
                            "params": [f"{CONSTANTS.WS_TRADE_CHANNEL}@{exchange_trading_pair}"],
                            "id": int(time.time() * 1000) + 1,
                        }
                        subscribe_trade_request = WSJSONRequest(payload=trade_params)
                        await ws.send(subscribe_trade_request)
                        
                        # 处理消息
                        while True:
                            try:
                                message = await asyncio.wait_for(
                                    ws.receive(), timeout=CONSTANTS.MESSAGE_TIMEOUT
                                )
                                msg_data = message.data
                                
                                # 处理订单簿更新消息
                                if CONSTANTS.WS_ORDERBOOK_CHANNEL in msg_data.get("stream", ""):
                                    order_book_msg = self._parse_order_book_diff_message(msg_data, trading_pair)
                                    await self._order_book_diff_messages[trading_pair].put(order_book_msg)
                                
                                # 处理交易消息
                                elif CONSTANTS.WS_TRADE_CHANNEL in msg_data.get("stream", ""):
                                    trade_msg = self._parse_trade_message(msg_data, trading_pair)
                                    await self._trade_messages[trading_pair].put(trade_msg)
                                
                                # 处理ping消息
                                elif msg_data.get("id") == "ping":
                                    pong_payload = {"id": "pong"}
                                    pong_request = WSJSONRequest(payload=pong_payload)
                                    await ws.send(pong_request)
                                    
                            except asyncio.TimeoutError:
                                # 发送ping保持连接活跃
                                ping_payload = {"id": "ping"}
                                ping_request = WSJSONRequest(payload=ping_payload)
                                await ws.send(ping_request)
                    
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.logger().error(
                    f"Unexpected error while listening to order book streams. Error: {str(e)}",
                    exc_info=True
                )
                await asyncio.sleep(5.0)  # 短暂暂停后重试
    
    def _parse_order_book_diff_message(self, msg_data: Dict[str, Any], trading_pair: str) -> OrderBookMessage:
        """
        解析订单簿差异消息
        :param msg_data: 消息数据
        :param trading_pair: 交易对
        :return: 订单簿差异消息
        """
        data = msg_data.get("data", {})
        timestamp = int(data.get("time", int(time.time() * 1000)))
        
        # 构建订单簿消息
        order_book_message = OrderBookMessage(
            message_type=OrderBookMessageType.DIFF,
            content={
                "trading_pair": trading_pair,
                "update_id": data.get("lastUpdateId", 0),
                "bids": [
                    [float(price), float(amount)]
                    for price, amount in data.get("bids", [])
                ],
                "asks": [
                    [float(price), float(amount)]
                    for price, amount in data.get("asks", [])
                ],
            },
            timestamp=timestamp / 1000.0,  # 转换为秒
        )
        
        return order_book_message
    
    def _parse_trade_message(self, msg_data: Dict[str, Any], trading_pair: str) -> OrderBookMessage:
        """
        解析交易消息
        :param msg_data: 消息数据
        :param trading_pair: 交易对
        :return: 交易消息
        """
        data = msg_data.get("data", {})
        timestamp = int(data.get("time", int(time.time() * 1000)))
        
        # 确定交易方向
        trade_type = TradeType.BUY if data.get("isBuyerMaker", True) else TradeType.SELL
        
        # 构建交易消息
        trade_message = OrderBookMessage(
            message_type=OrderBookMessageType.TRADE,
            content={
                "trading_pair": trading_pair,
                "trade_id": data.get("tradeId", int(timestamp)),
                "trade_type": trade_type,
                "price": float(data.get("price", "0")),
                "amount": float(data.get("quantity", "0")),
            },
            timestamp=timestamp / 1000.0,  # 转换为秒
        )
        
        return trade_message 