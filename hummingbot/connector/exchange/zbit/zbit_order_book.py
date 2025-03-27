from typing import Any, Dict, List, Optional

from hummingbot.core.data_type.order_book import OrderBook
from hummingbot.core.data_type.order_book_message import OrderBookMessage, OrderBookMessageType
from hummingbot.core.data_type.order_book_tracker_entry import OrderBookTrackerEntry
from hummingbot.logger import HummingbotLogger

class ZbitOrderBook(OrderBook):
    """Zbit交易所订单簿实现类，继承自OrderBook基类"""
    
    @classmethod
    def logger(cls) -> HummingbotLogger:
        """
        获取日志记录器实例
        :return: Hummingbot日志记录器实例
        """
        if cls._logger is None:
            cls._logger = HummingbotLogger(__name__)
        return cls._logger

    @classmethod
    def diff_message_from_exchange(
        cls,
        msg: Dict[str, Any],
        timestamp: Optional[float] = None,
        metadata: Optional[Dict] = None
    ) -> OrderBookMessage:
        """
        从交易所WebSocket消息创建差异(增量更新)消息
        :param msg: 来自交易所的订单簿WebSocket消息
        :param timestamp: 差异消息的时间戳
        :param metadata: 关于订单簿消息的可选元数据
        :return: 新的OrderBookMessage实例
        """
        # 初始化元数据
        if metadata is None:
            metadata = {}
        # 获取交易对信息
        trading_pair = metadata.get("trading_pair")
        if trading_pair is None:
            trading_pair = msg.get("symbol")

        # 解析订单簿更新数据
        bids = []
        asks = []
        
        # 处理买单更新
        if "bids" in msg:
            for bid in msg["bids"]:
                price = float(bid[0])  # 获取价格
                amount = float(bid[1])  # 获取数量
                if amount > 0:  # 只处理数量大于0的订单
                    bids.append([price, amount])  # 添加到买单列表
                    
        # 处理卖单更新
        if "asks" in msg:
            for ask in msg["asks"]:
                price = float(ask[0])  # 获取价格
                amount = float(ask[1])  # 获取数量
                if amount > 0:  # 只处理数量大于0的订单
                    asks.append([price, amount])  # 添加到卖单列表

        # 创建并返回订单簿差异消息
        return OrderBookMessage(
            message_type=OrderBookMessageType.DIFF,  # 消息类型：差异更新
            content={
                "trading_pair": trading_pair,  # 交易对
                "update_id": msg.get("lastUpdateId", timestamp),  # 更新ID
                "bids": bids,  # 买单列表
                "asks": asks   # 卖单列表
            },
            timestamp=timestamp  # 时间戳
        )

    @classmethod
    def trade_message_from_exchange(
        cls,
        msg: Dict[str, Any],
        timestamp: Optional[float] = None,
        metadata: Optional[Dict] = None
    ) -> OrderBookMessage:
        """
        从交易所WebSocket消息创建交易消息
        :param msg: 来自交易所的交易WebSocket消息
        :param timestamp: 交易消息的时间戳
        :param metadata: 关于交易消息的可选元数据
        :return: 新的OrderBookMessage实例
        """
        # 初始化元数据
        if metadata is None:
            metadata = {}
        # 获取交易对信息
        trading_pair = metadata.get("trading_pair")
        if trading_pair is None:
            trading_pair = msg.get("symbol")

        # 创建并返回交易消息
        return OrderBookMessage(
            message_type=OrderBookMessageType.TRADE,  # 消息类型：交易
            content={
                "trading_pair": trading_pair,  # 交易对
                "trade_type": float(msg.get("price", 0.0)),  # 交易类型
                "trade_id": msg.get("id", timestamp),  # 交易ID
                "update_id": msg.get("lastUpdateId", timestamp),  # 更新ID
                "price": float(msg.get("price", 0.0)),  # 价格
                "amount": float(msg.get("qty", 0.0))  # 数量
            },
            timestamp=timestamp  # 时间戳
        )

    @classmethod
    def snapshot_message_from_exchange(
        cls,
        msg: Dict[str, Any],
        timestamp: Optional[float] = None,
        metadata: Optional[Dict] = None
    ) -> OrderBookMessage:
        """
        从交易所订单簿快照创建快照消息
        :param msg: 来自交易所的订单簿快照
        :param timestamp: 快照消息的时间戳
        :param metadata: 关于订单簿消息的可选元数据
        :return: 新的OrderBookMessage实例
        """
        # 初始化元数据
        if metadata is None:
            metadata = {}
        # 获取交易对信息
        trading_pair = metadata.get("trading_pair")
        if trading_pair is None:
            trading_pair = msg.get("symbol")

        # 解析订单簿快照数据
        bids = []
        asks = []
        
        # 处理买单数据
        if "bids" in msg:
            for bid in msg["bids"]:
                price = float(bid[0])  # 获取价格
                amount = float(bid[1])  # 获取数量
                if amount > 0:  # 只处理数量大于0的订单
                    bids.append([price, amount])  # 添加到买单列表
                    
        # 处理卖单数据
        if "asks" in msg:
            for ask in msg["asks"]:
                price = float(ask[0])  # 获取价格
                amount = float(ask[1])  # 获取数量
                if amount > 0:  # 只处理数量大于0的订单
                    asks.append([price, amount])  # 添加到卖单列表

        # 创建并返回订单簿快照消息
        return OrderBookMessage(
            message_type=OrderBookMessageType.SNAPSHOT,  # 消息类型：快照
            content={
                "trading_pair": trading_pair,  # 交易对
                "update_id": msg.get("lastUpdateId", timestamp),  # 更新ID
                "bids": bids,  # 买单列表
                "asks": asks   # 卖单列表
            },
            timestamp=timestamp  # 时间戳
        ) 