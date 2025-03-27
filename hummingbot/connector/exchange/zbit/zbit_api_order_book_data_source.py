import asyncio
import logging
from typing import Any, Dict, List, Optional

from hummingbot.connector.exchange.zbit.zbit_constants import (
    DIFF_EVENT_TYPE,
    ORDER_BOOK_CHANNEL,
    TRADE_CHANNEL,
    TRADE_EVENT_TYPE,
    WSS_URL,
    WS_HEARTBEAT_TIME_INTERVAL,
)
from hummingbot.connector.exchange.zbit.zbit_order_book import ZbitOrderBook
from hummingbot.core.data_type.order_book_message import OrderBookMessage, OrderBookMessageType
from hummingbot.core.data_type.order_book_tracker_data_source import OrderBookTrackerDataSource
from hummingbot.core.web_assistant.ws_assistant import WSAssistant
from hummingbot.core.web_assistant.connections.data_types import WSRequest, WSResponse
from hummingbot.logger import HummingbotLogger


class ZbitAPIOrderBookDataSource(OrderBookTrackerDataSource):
    """Zbit交易所订单簿数据源，负责WebSocket连接和订单簿数据处理"""
    
    # 类级别的日志记录器
    _logger: Optional[HummingbotLogger] = None

    def __init__(self, trading_pairs: List[str], connector: 'ZbitExchange'):
        """
        初始化订单簿数据源
        :param trading_pairs: 交易对列表
        :param connector: Zbit交易所连接器实例
        """
        super().__init__(trading_pairs)
        self._connector = connector  # 保存交易所连接器引用
        self._trading_pairs: List[str] = trading_pairs  # 交易对列表
        self._api_factory = connector._web_assistants_factory  # Web助手工厂

    @classmethod
    def logger(cls) -> HummingbotLogger:
        """
        获取日志记录器
        :return: 日志记录器实例
        """
        if cls._logger is None:
            cls._logger = logging.getLogger(__name__)
        return cls._logger

    async def _connected_websocket_assistant(self) -> WSAssistant:
        """
        创建一个连接到交易所的WebSocket助手实例
        :return: 已连接的WebSocket助手
        """
        # 从API工厂获取WebSocket助手
        ws: WSAssistant = await self._api_factory.get_ws_assistant()
        # 连接到WebSocket服务器
        await ws.connect(ws_url=WSS_URL, ping_timeout=WS_HEARTBEAT_TIME_INTERVAL)
        return ws

    async def _subscribe_channels(self, ws: WSAssistant):
        """
        通过提供的WebSocket连接订阅交易事件和订单簿差异事件
        :param ws: 用于连接到交易所的WebSocket助手
        """
        try:
            # 订阅订单簿更新
            order_book_payload = {
                "event": ORDER_BOOK_CHANNEL,  # 订单簿通道事件
                "exchange": "zbit"           # 交易所名称
            }
            # 创建订阅订单簿的WebSocket请求
            subscribe_orderbook_request: WSRequest = WSRequest(payload=order_book_payload)
            # 发送订阅请求
            await ws.send(subscribe_orderbook_request)

            # 订阅交易更新
            trade_payload = {
                "event": TRADE_CHANNEL,  # 交易通道事件
                "exchange": "zbit"      # 交易所名称
            }
            # 创建订阅交易的WebSocket请求
            subscribe_trade_request: WSRequest = WSRequest(payload=trade_payload)
            # 发送订阅请求
            await ws.send(subscribe_trade_request)

            # 记录订阅成功的日志
            self.logger().info("Subscribed to public order book and trade channels...")
        except asyncio.CancelledError:
            # 传递取消异常
            raise
        except Exception:
            # 记录订阅时发生的错误
            self.logger().error(
                "Unexpected error occurred subscribing to order book trading and delta streams...",
                exc_info=True
            )
            # 向上传递异常
            raise

    async def _process_websocket_messages(self, websocket_assistant: WSAssistant):
        """
        处理WebSocket消息
        :param websocket_assistant: WebSocket助手
        """
        # 迭代处理所有接收到的WebSocket消息
        async for ws_response in websocket_assistant.iter_messages():
            # 获取响应数据
            data: Dict[str, Any] = ws_response.data
            # 当WebSocket断开连接时，数据将为None
            if data is not None:
                # 确定消息所属的通道
                channel: str = self._channel_originating_message(event_message=data)
                # 获取有效的消息队列键
                valid_channels = self._get_messages_queue_keys()
                # 如果是已知通道，将消息添加到相应队列
                if channel in valid_channels:
                    self._message_queue[channel].put_nowait(data)
                else:
                    # 处理未知通道的消息
                    await self._process_message_for_unknown_channel(
                        event_message=data, websocket_assistant=websocket_assistant
                    )

    def _channel_originating_message(self, event_message: Dict[str, Any]) -> str:
        """
        识别特定事件消息所属的通道
        :param event_message: 事件消息
        :return: 通道标识符
        """
        channel = ""
        # 检查消息中的event字段
        if "event" in event_message:
            # 如果是交易通道事件
            if event_message["event"] == TRADE_CHANNEL:
                channel = self._trade_messages_queue_key
            # 如果是订单簿通道事件
            elif event_message["event"] == ORDER_BOOK_CHANNEL:
                channel = self._diff_messages_queue_key
        # 检查消息中的exchange字段
        elif "exchange" in event_message and event_message.get("exchange") == "zbit":
            # 如果包含trade字段，是交易消息
            if "trade" in event_message:
                channel = self._trade_messages_queue_key
            # 如果包含asks或bids字段，是订单簿消息
            elif "asks" in event_message or "bids" in event_message:
                channel = self._diff_messages_queue_key
        return channel

    async def _process_message_for_unknown_channel(self, event_message: Dict[str, Any], websocket_assistant: WSAssistant):
        """
        处理不属于任何处理程序的消息
        :param event_message: 事件消息
        :param websocket_assistant: WebSocket助手
        """
        # 检查是否是Zbit交易所的消息
        if "exchange" in event_message and event_message.get("exchange") == "zbit":
            # 如果包含订单簿数据
            if "asks" in event_message or "bids" in event_message:
                # 这是一个订单簿更新消息
                await self._parse_order_book_diff_message(event_message, self._message_queue[self._diff_messages_queue_key])
            # 如果包含交易数据
            elif "trade" in event_message:
                # 这是一个交易消息
                await self._parse_trade_message(event_message, self._message_queue[self._trade_messages_queue_key])

    async def _parse_order_book_diff_message(self, raw_message: Dict[str, Any], message_queue: asyncio.Queue):
        """
        创建OrderBookMessageType.DIFF类型的OrderBookMessage实例
        :param raw_message: 原始消息
        :param message_queue: 消息队列
        """
        # 从消息中获取交易对
        trading_pair = raw_message.get("symbol")
        # 获取时间戳，如果没有则使用当前时间
        timestamp = raw_message.get("timestamp", self._time())
        # 使用ZbitOrderBook创建差异消息
        order_book_message: OrderBookMessage = ZbitOrderBook.diff_message_from_exchange(
            raw_message,
            timestamp,
            metadata={"trading_pair": trading_pair}
        )
        # 将消息放入队列
        message_queue.put_nowait(order_book_message)

    async def _parse_trade_message(self, raw_message: Dict[str, Any], message_queue: asyncio.Queue):
        """
        创建OrderBookMessageType.TRADE类型的OrderBookMessage实例
        :param raw_message: 原始消息
        :param message_queue: 消息队列
        """
        # 从消息中获取交易对
        trading_pair = raw_message.get("symbol")
        # 获取时间戳，如果没有则使用当前时间
        timestamp = raw_message.get("timestamp", self._time())
        # 使用ZbitOrderBook创建交易消息
        trade_message: OrderBookMessage = ZbitOrderBook.trade_message_from_exchange(
            raw_message,
            timestamp,
            metadata={"trading_pair": trading_pair}
        )
        # 将消息放入队列
        message_queue.put_nowait(trade_message)

    async def _order_book_snapshot(self, trading_pair: str) -> OrderBookMessage:
        """
        创建包含订单簿快照消息的快照消息
        :param trading_pair: 交易对
        :return: 订单簿快照消息
        """
        # 请求订单簿快照
        snapshot: Dict[str, Any] = await self._request_order_book_snapshot(trading_pair)
        # 获取当前时间作为快照时间戳
        snapshot_timestamp: float = self._time()
        # 使用ZbitOrderBook创建快照消息
        snapshot_msg: OrderBookMessage = ZbitOrderBook.snapshot_message_from_exchange(
            snapshot,
            snapshot_timestamp,
            metadata={"trading_pair": trading_pair}
        )
        return snapshot_msg

    async def get_last_traded_prices(self, trading_pairs: List[str]) -> Dict[str, float]:
        """
        获取指定交易对的最后成交价格
        :param trading_pairs: 交易对列表
        :return: 交易对到最后成交价格的映射字典
        """
        result = {}
        # 遍历每个交易对
        for trading_pair in trading_pairs:
            try:
                # 这里应该使用交易所提供的API来获取最新成交价
                # 由于这是一个简单实现，我们将返回一个虚拟价格
                # 在实际实现中，应该使用self._connector._api_request或类似方法获取真实数据
                result[trading_pair] = 50000.0  # 模拟BTC价格约为50000 USDT
            except Exception as e:
                # 记录获取价格时的错误
                self.logger().error(f"Error getting last traded price for {trading_pair}: {e}", exc_info=True)
                # 出错时设置为0
                result[trading_pair] = 0.0
        return result
