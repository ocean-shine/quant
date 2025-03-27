# 导入哈希库用于签名计算
import hashlib
# 导入hmac用于生成加密签名
import hmac
# 导入时间模块用于获取时间戳
import time
# 从typing导入类型提示所需的Any和Dict
from typing import Any, Dict
# 导入urlencode函数用于URL参数编码
from urllib.parse import urlencode

# 从Zbit常量文件导入API认证相关的常量
from hummingbot.connector.exchange.zbit.zbit_constants import (
    API_KEY_HEADER,     # API密钥请求头名称
    CONTENT_TYPE,       # 内容类型请求头
    SIGNATURE_HEADER,   # 签名请求头名称
    TIMESTAMP_HEADER,   # 时间戳请求头名称
)


class ZbitAuth:
    """Zbit交易所认证类，负责API请求的签名和认证"""
    
    def __init__(self, api_key: str, api_secret: str):
        """
        初始化认证类
        :param api_key: API密钥
        :param api_secret: API密钥对应的秘密
        """
        self.api_key = api_key
        self.api_secret = api_secret

    def generate_auth_dict(self, path_url: str, method: str, params: Dict[str, Any] = None) -> Dict[str, str]:
        """
        生成请求认证参数
        :param path_url: API端点路径
        :param method: HTTP方法（GET/POST等）
        :param params: 请求参数
        :return: 包含认证头的字典
        """
        # 获取当前时间戳(毫秒)
        timestamp = int(time.time() * 1000)
        
        # 准备签名字符串 - 将请求参数转为查询字符串
        query_string = ""
        if params:
            query_string = urlencode(sorted(params.items()))
        
        # 构建签名载荷 - 组合时间戳、方法、路径和查询字符串
        signature_payload = f"{timestamp}{method}{path_url}{query_string}"
        
        # 计算HMAC-SHA256签名
        signature = hmac.new(
            self.api_secret.encode('utf-8'),  # 将API秘钥转为字节
            signature_payload.encode('utf-8'),  # 将签名载荷转为字节
            hashlib.sha256  # 使用SHA256哈希算法
        ).hexdigest()  # 转为十六进制字符串
        
        # 构建认证头
        headers = {
            "X-ZBIT-APIKEY": self.api_key,  # API密钥头
            "X-ZBIT-TIMESTAMP": str(timestamp),  # 时间戳头
            "X-ZBIT-SIGNATURE": signature,  # 签名头
        }
        
        return headers

    def generate_ws_auth_dict(self) -> Dict[str, str]:
        """
        生成WebSocket连接的认证参数
        :return: 包含WebSocket认证参数的字典
        """
        # 获取当前时间戳(毫秒)
        timestamp = int(time.time() * 1000)
        
        # 构建签名载荷 - 仅使用时间戳
        signature_payload = f"{timestamp}"
        
        # 计算HMAC-SHA256签名
        signature = hmac.new(
            self.api_secret.encode('utf-8'),  # 将API秘钥转为字节
            signature_payload.encode('utf-8'),  # 将签名载荷转为字节
            hashlib.sha256  # 使用SHA256哈希算法
        ).hexdigest()  # 转为十六进制字符串
        
        # 构建认证参数
        auth_params = {
            "apiKey": self.api_key,  # API密钥
            "timestamp": str(timestamp),  # 时间戳
            "signature": signature,  # 签名
        }
        
        return auth_params

    def generate_ws_subscription_message(self, channel: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        生成带认证的WebSocket订阅消息
        :param channel: 要订阅的WebSocket通道
        :param params: 订阅的附加参数
        :return: 包含订阅消息的字典
        """
        # 获取认证参数
        auth_params = self.generate_ws_auth_dict()
        
        # 构建订阅消息
        message = {
            "method": "SUBSCRIBE",  # 订阅方法
            "params": [channel],    # 要订阅的通道
            "id": 1,                # 消息ID
            **auth_params           # 展开认证参数
        }
        
        # 添加附加参数（如果有）
        if params:
            message.update(params)
            
        return message

    def generate_signature(self, timestamp: str, method: str, request_path: str, body: str = "") -> str:
        """
        为请求生成认证签名
        :param timestamp: 请求的时间戳
        :param method: HTTP方法（GET/POST）
        :param request_path: 请求路径
        :param body: 请求体（用于POST请求）
        :return: 生成的签名
        """
        # 组合消息字符串
        message = f"{timestamp}{method}{request_path}{body}"
        # 计算HMAC-SHA256签名
        signature = hmac.new(
            self.api_secret.encode("utf-8"),  # 将API秘钥转为字节
            message.encode("utf-8"),          # 将消息转为字节
            hashlib.sha256                    # 使用SHA256哈希算法
        ).hexdigest()  # 转为十六进制字符串
        return signature

    def get_headers(self, method: str, request_path: str, body: str = "") -> Dict[str, Any]:
        """
        生成认证请求的头部
        :param method: HTTP方法（GET/POST）
        :param request_path: 请求路径
        :param body: 请求体（用于POST请求）
        :return: 头部字典
        """
        # 获取当前时间戳(毫秒)
        timestamp = str(int(time.time() * 1000))
        # 生成签名
        signature = self.generate_signature(timestamp, method, request_path, body)
        
        # 构建头部字典
        headers = {
            API_KEY_HEADER: self.api_key,        # API密钥头
            TIMESTAMP_HEADER: timestamp,         # 时间戳头
            SIGNATURE_HEADER: signature,         # 签名头
            CONTENT_TYPE: "application/json"     # 内容类型头
        }
        return headers
