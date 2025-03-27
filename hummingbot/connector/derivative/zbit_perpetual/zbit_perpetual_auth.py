import hashlib
import hmac
import time
from typing import Any, Dict
from urllib.parse import urlencode

from hummingbot.connector.derivative.zbit_perpetual import zbit_perpetual_constants as CONSTANTS
from hummingbot.core.web_assistant.auth import AuthBase
from hummingbot.core.web_assistant.connections.data_types import RESTMethod, RESTRequest, WSRequest


class ZbitPerpetualAuth(AuthBase):
    """
    ZBit永续合约认证类
    负责处理与ZBit API的认证
    """

    def __init__(self, api_key: str, secret_key: str):
        """
        初始化ZBit认证
        :param api_key: API密钥
        :param secret_key: API密钥秘密
        """
        self._api_key = api_key
        self._secret_key = secret_key

    async def rest_authenticate(self, request: RESTRequest) -> RESTRequest:
        """
        为REST请求添加认证信息
        :param request: 原始REST请求
        :return: 添加了认证信息的REST请求
        """
        # 如果是GET请求，请求数据应该放在URL参数中
        if request.method == RESTMethod.GET:
            params = request.params or {}
        # 如果是POST/PUT/DELETE请求，请求数据应该放在请求体中
        else:
            params = request.data or {}

        # 添加通用参数
        params.update({
            "timestamp": int(time.time() * 1000),  # 时间戳（毫秒）
            "apiKey": self._api_key,
            "recvWindow": 5000,  # 接收窗口（毫秒）
        })

        # 构建签名
        signature = self._generate_signature(params)
        params["signature"] = signature

        # 根据请求方法更新请求
        if request.method == RESTMethod.GET:
            request.params = params
        else:
            request.data = params

        # 添加其他请求头
        headers = request.headers or {}
        headers.update({
            "X-MBX-APIKEY": self._api_key,
            "Content-Type": "application/json",
        })
        request.headers = headers

        return request

    async def ws_authenticate(self, request: WSRequest) -> WSRequest:
        """
        为WebSocket请求添加认证信息
        :param request: 原始WebSocket请求
        :return: 添加了认证信息的WebSocket请求
        """
        # 获取认证数据
        auth_params = {
            "apiKey": self._api_key,
            "timestamp": int(time.time() * 1000),
        }
        
        # 构建签名
        signature = self._generate_signature(auth_params)
        auth_params["signature"] = signature
        
        # 构建认证请求
        auth_request = {
            "method": CONSTANTS.WS_AUTHENTICATE_URL,
            "params": auth_params,
            "id": int(time.time() * 1000),
        }
        
        # 更新WebSocket请求数据
        if not request.payload:
            request.payload = auth_request
        else:
            # 如果已有载荷，则将认证信息添加到现有载荷中
            current_payload = request.payload
            if isinstance(current_payload, Dict):
                current_payload.update({"auth": auth_params})
                request.payload = current_payload

        return request

    def _generate_signature(self, params: Dict[str, Any]) -> str:
        """
        生成请求签名
        :param params: 请求参数
        :return: 生成的签名
        """
        # 将参数转换为查询字符串
        query_string = urlencode(sorted(params.items()))
        # 使用HMAC-SHA256创建签名
        signature = hmac.new(
            self._secret_key.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        
        return signature 