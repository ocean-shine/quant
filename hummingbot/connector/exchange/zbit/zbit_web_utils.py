# 导入异步IO库
import asyncio
# 导入JSON处理库
import json
# 导入类型提示所需的类型
from typing import Any, Dict, Optional

# 导入aiohttp库用于HTTP请求
import aiohttp
# 导入客户端超时设置类
from aiohttp import ClientTimeout

# 导入Zbit认证类
from hummingbot.connector.exchange.zbit.zbit_auth import ZbitAuth
# 导入Zbit REST API URL常量
from hummingbot.connector.exchange.zbit.zbit_constants import REST_URL


class ZbitWebUtils:
    """Zbit Web工具类，提供API请求和WebSocket通信功能"""

    @staticmethod
    async def api_request(
        method: str,
        path_url: str,
        auth: Optional[ZbitAuth] = None,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        is_auth_required: bool = False,
        timeout: float = 10,
    ) -> Dict[str, Any]:
        """
        发送异步HTTP请求并等待响应
        :param method: HTTP方法(GET/POST)
        :param path_url: API路径
        :param auth: 认证对象
        :param params: 查询参数
        :param data: 请求体数据
        :param is_auth_required: 是否需要认证
        :param timeout: 请求超时时间(秒)
        :return: 响应数据
        """
        # 构建完整URL
        url = f"{REST_URL}{path_url}"
        
        # 检查认证要求
        if is_auth_required and auth is None:
            raise ValueError("Authentication is required for this request")

        # 准备请求头
        headers = {}
        if auth is not None:
            # 如果有数据，将其转为JSON字符串，否则使用空字符串
            body = json.dumps(data) if data else ""
            # 获取认证头
            headers = auth.get_headers(method, path_url, body)

        # 创建客户端会话并发送请求
        async with aiohttp.ClientSession() as client:
            async with client.request(
                method=method,     # HTTP方法
                url=url,           # 请求URL
                headers=headers,   # 请求头
                params=params,     # URL参数
                data=data,         # 请求体数据
                timeout=ClientTimeout(total=timeout),  # 设置超时时间
            ) as response:
                # 检查响应状态码
                if response.status != 200:
                    raise Exception(f"Error calling {url}. Response: {await response.text()}")
                # 解析并返回JSON响应
                return await response.json()

    @staticmethod
    async def get_current_server_time() -> float:
        """
        获取当前服务器时间
        :return: 服务器时间(毫秒)
        """
        # 发送API请求获取服务器时间
        response = await ZbitWebUtils.api_request("GET", "/sapi/v1/time")
        # 返回服务器时间
        return float(response["serverTime"])

    @staticmethod
    def public_rest_url(path_url: str) -> str:
        """
        创建公开REST端点的完整URL
        :param path_url: 公开REST端点路径
        :return: 完整URL
        """
        # 组合基础URL和路径
        return f"{REST_URL}{path_url}"

    @staticmethod
    def private_rest_url(path_url: str) -> str:
        """
        创建私有REST端点的完整URL
        :param path_url: 私有REST端点路径
        :return: 完整URL
        """
        # 组合基础URL和路径（与公开URL相同，但语义上区分）
        return f"{REST_URL}{path_url}"

    @staticmethod
    def build_url_with_params(url: str, params: Dict[str, Any]) -> str:
        """
        构建带查询参数的URL
        :param url: 基础URL
        :param params: 查询参数
        :return: 带查询参数的完整URL
        """
        # 构建查询字符串
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        # 返回带查询参数的URL
        return f"{url}?{query_string}"

    @staticmethod
    def build_ws_url(path_url: str) -> str:
        """
        创建WebSocket URL
        :param path_url: WebSocket端点路径
        :return: 完整WebSocket URL
        """
        # 构建WebSocket安全连接URL
        return f"wss://{path_url}"

    @staticmethod
    def build_ws_message(channel: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        构建WebSocket消息
        :param channel: WebSocket通道
        :param params: 消息的额外参数
        :return: 完整WebSocket消息
        """
        # 创建基本订阅消息
        message = {
            "method": "SUBSCRIBE",  # 订阅方法
            "params": [channel],    # 订阅的通道
            "id": 1                 # 消息ID
        }
        # 如果有额外参数，更新消息
        if params:
            message.update(params)
        return message

    @staticmethod
    def build_ws_ping_message() -> Dict[str, Any]:
        """
        构建WebSocket ping消息
        :return: ping消息
        """
        # 创建ping消息结构
        return {
            "method": "PING",  # ping方法
            "id": 1            # 消息ID
        }

    @staticmethod
    def build_ws_pong_message() -> Dict[str, Any]:
        """
        构建WebSocket pong消息
        :return: pong消息
        """
        # 创建pong消息结构
        return {
            "method": "PONG",  # pong方法
            "id": 1            # 消息ID
        }
