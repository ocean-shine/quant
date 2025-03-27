import asyncio  # 用于异步编程
import time     # 用于时间相关操作
from typing import TYPE_CHECKING, Any, Dict, List, Optional  # 类型提示

from hummingbot.connector.exchange.binance import binance_constants as CONSTANTS, binance_web_utils as web_utils
from hummingbot.connector.exchange.binance.binance_order_book import BinanceOrderBook
from hummingbot.core.data_type.order_book_message import OrderBookMessage
from hummingbot.core.data_type.order_book_tracker_data_source import OrderBookTrackerDataSource
from hummingbot.core.web_assistant.connections.data_types import RESTMethod, WSJSONRequest
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
from hummingbot.core.web_assistant.ws_assistant import WSAssistant
from hummingbot.logger import HummingbotLogger

if TYPE_CHECKING:
    from hummingbot.connector.exchange.binance.binance_exchange import BinanceExchange


class BinanceAPIOrderBookDataSource(OrderBookTrackerDataSource):
    """
    Binance 交易所的订单簿数据源类
    负责处理订单簿的实时更新、快照获取和消息处理
    """
    # 心跳间隔时间（秒）
    HEARTBEAT_TIME_INTERVAL = 30.0
    # 交易流ID
    TRADE_STREAM_ID = 1
    # 订单簿差异流ID
    DIFF_STREAM_ID = 2
    # 一小时的时间（秒）
    ONE_HOUR = 60 * 60

    # 日志记录器
    _logger: Optional[HummingbotLogger] = None

    def __init__(self,
                 trading_pairs: List[str],  # 交易对列表
                 connector: 'BinanceExchange',  # Binance交易所连接器
                 api_factory: WebAssistantsFactory,  # Web助手工厂
                 domain: str = CONSTANTS.DEFAULT_DOMAIN):  # 域名
        """
        初始化订单簿数据源
        """
        super().__init__(trading_pairs)
        self._connector = connector
        # 设置消息队列键
        self._trade_messages_queue_key = CONSTANTS.TRADE_EVENT_TYPE
        self._diff_messages_queue_key = CONSTANTS.DIFF_EVENT_TYPE
        self._domain = domain
        self._api_factory = api_factory

    async def get_last_traded_prices(self,
                                     trading_pairs: List[str],
                                     domain: Optional[str] = None) -> Dict[str, float]:
        """
        获取交易对的最新成交价格
        """
        return await self._connector.get_last_traded_prices(trading_pairs=trading_pairs)

    async def _request_order_book_snapshot(self, trading_pair: str) -> Dict[str, Any]:
        """
        从交易所获取完整的订单簿快照
        
        参数:
            trading_pair: 交易对名称
            
        返回:
            交易所返回的JSON数据
        """
        # 设置请求参数
        params = {
            "symbol": await self._connector.exchange_symbol_associated_to_pair(trading_pair=trading_pair),
            "limit": "1000"  # 获取1000个订单
        }

        # 获取REST助手并执行请求
        rest_assistant = await self._api_factory.get_rest_assistant()
        data = await rest_assistant.execute_request(
            url=web_utils.public_rest_url(path_url=CONSTANTS.SNAPSHOT_PATH_URL, domain=self._domain),
            params=params,
            method=RESTMethod.GET,
            throttler_limit_id=CONSTANTS.SNAPSHOT_PATH_URL,
        )

        return data

    async def _subscribe_channels(self, ws: WSAssistant):
        """
        订阅交易和订单簿差异事件的WebSocket频道
        
        参数:
            ws: WebSocket助手实例
        """
        try:
            trade_params = []  # 交易参数列表
            depth_params = []  # 深度参数列表
            
            # 为每个交易对创建订阅参数
            for trading_pair in self._trading_pairs:
                symbol = await self._connector.exchange_symbol_associated_to_pair(trading_pair=trading_pair)
                trade_params.append(f"{symbol.lower()}@trade")  # 订阅交易信息
                depth_params.append(f"{symbol.lower()}@depth@100ms")  # 订阅订单簿深度信息
                
            # 创建交易订阅请求
            payload = {
                "method": "SUBSCRIBE",
                "params": trade_params,
                "id": 1
            }
            subscribe_trade_request: WSJSONRequest = WSJSONRequest(payload=payload)

            # 创建订单簿订阅请求
            payload = {
                "method": "SUBSCRIBE",
                "params": depth_params,
                "id": 2
            }
            subscribe_orderbook_request: WSJSONRequest = WSJSONRequest(payload=payload)

            # 发送订阅请求
            await ws.send(subscribe_trade_request)
            await ws.send(subscribe_orderbook_request)

            self.logger().info("Subscribed to public order book and trade channels...")
        except asyncio.CancelledError:
            raise
        except Exception:
            self.logger().error(
                "Unexpected error occurred subscribing to order book trading and delta streams...",
                exc_info=True
            )
            raise

    async def _connected_websocket_assistant(self) -> WSAssistant:
        """
        创建并连接WebSocket助手
        
        返回:
            已连接的WebSocket助手实例
        """
        ws: WSAssistant = await self._api_factory.get_ws_assistant()
        await ws.connect(ws_url=CONSTANTS.WSS_URL.format(self._domain),
                         ping_timeout=CONSTANTS.WS_HEARTBEAT_TIME_INTERVAL)
        return ws

    async def _order_book_snapshot(self, trading_pair: str) -> OrderBookMessage:
        """
        获取订单簿快照并转换为消息格式
        
        参数:
            trading_pair: 交易对名称
            
        返回:
            订单簿快照消息
        """
        snapshot: Dict[str, Any] = await self._request_order_book_snapshot(trading_pair)
        snapshot_timestamp: float = time.time()
        snapshot_msg: OrderBookMessage = BinanceOrderBook.snapshot_message_from_exchange(
            snapshot,
            snapshot_timestamp,
            metadata={"trading_pair": trading_pair}
        )
        return snapshot_msg

    async def _parse_trade_message(self, raw_message: Dict[str, Any], message_queue: asyncio.Queue):
        """
        解析交易消息并放入消息队列
        
        参数:
            raw_message: 原始消息
            message_queue: 消息队列
        """
        if "result" not in raw_message:
            trading_pair = await self._connector.trading_pair_associated_to_exchange_symbol(symbol=raw_message["s"])
            trade_message = BinanceOrderBook.trade_message_from_exchange(
                raw_message, {"trading_pair": trading_pair})
            message_queue.put_nowait(trade_message)

    async def _parse_order_book_diff_message(self, raw_message: Dict[str, Any], message_queue: asyncio.Queue):
        """
        解析订单簿差异消息并放入消息队列
        
        参数:
            raw_message: 原始消息
            message_queue: 消息队列
        """
        if "result" not in raw_message:
            trading_pair = await self._connector.trading_pair_associated_to_exchange_symbol(symbol=raw_message["s"])
            order_book_message: OrderBookMessage = BinanceOrderBook.diff_message_from_exchange(
                raw_message, time.time(), {"trading_pair": trading_pair})
            message_queue.put_nowait(order_book_message)

    def _channel_originating_message(self, event_message: Dict[str, Any]) -> str:
        """
        确定消息来源的频道
        
        参数:
            event_message: 事件消息
            
        返回:
            频道名称
        """
        channel = ""
        if "result" not in event_message:
            event_type = event_message.get("e")
            channel = (self._diff_messages_queue_key if event_type == CONSTANTS.DIFF_EVENT_TYPE
                       else self._trade_messages_queue_key)
        return channel
