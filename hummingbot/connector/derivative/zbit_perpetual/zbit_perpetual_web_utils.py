import json
import time
import asyncio
from typing import Any, Dict, List, Optional, Tuple, Union

import aiohttp
from aiohttp import ContentTypeError

from hummingbot.connector.derivative.zbit_perpetual import zbit_perpetual_constants as CONSTANTS
from hummingbot.core.api_throttler.async_throttler import AsyncThrottler
from hummingbot.core.web_assistant.auth import AuthBase
from hummingbot.core.web_assistant.connections.data_types import RESTRequest, RESTResponse
from hummingbot.core.web_assistant.rest_assistant import RESTAssistant
from hummingbot.core.web_assistant.rest_pre_processors import RESTPreProcessorBase
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory


class ZbitPerpetualRESTPreProcessor(RESTPreProcessorBase):
    """
    ZBit永续合约REST预处理器，添加请求头和处理时间同步
    """
    
    async def pre_process(self, request: RESTRequest) -> RESTRequest:
        """
        预处理请求，添加通用头部
        :param request: 原始请求
        :return: 处理后的请求
        """
        headers = {}
        if request.headers is not None:
            headers.update(request.headers)
        headers.update({
            "Content-Type": "application/json",
            "User-Agent": "hummingbot",
        })
        request.headers = headers
        return request


def public_rest_url(path_url: str, domain: str = CONSTANTS.DEFAULT_DOMAIN) -> str:
    """
    创建公共REST API URL
    :param path_url: API路径
    :param domain: API域，默认为主域
    :return: 完整URL
    """
    return f"{CONSTANTS.REST_URL_PUBLIC}/{path_url}"


def private_rest_url(path_url: str, domain: str = CONSTANTS.DEFAULT_DOMAIN) -> str:
    """
    创建私有REST API URL
    :param path_url: API路径
    :param domain: API域，默认为主域
    :return: 完整URL
    """
    return f"{CONSTANTS.REST_URL_AUTH}/{path_url}"


def build_api_factory(
    throttler: AsyncThrottler,
    auth: Optional[AuthBase] = None,
) -> WebAssistantsFactory:
    """
    构建Web助手工厂
    :param throttler: API限流器
    :param auth: 认证对象
    :return: Web助手工厂
    """
    api_factory = WebAssistantsFactory(
        throttler=throttler,
        auth=auth,
        rest_pre_processors=[
            ZbitPerpetualRESTPreProcessor(),
        ],
    )
    return api_factory


async def api_request(
    path: str,
    api_factory: Optional[WebAssistantsFactory] = None,
    throttler: Optional[AsyncThrottler] = None,
    time_synchronizer: Optional[Any] = None,
    domain: str = CONSTANTS.DEFAULT_DOMAIN,
    params: Optional[Dict[str, Any]] = None,
    data: Optional[Dict[str, Any]] = None,
    method: str = "GET",
    is_auth_required: bool = False,
    limit_id: Optional[str] = None,
    timeout: float = 10.0,
    **kwargs,
) -> Dict[str, Any]:
    """
    发送API请求
    :param path: API路径
    :param api_factory: Web助手工厂
    :param throttler: API限流器
    :param time_synchronizer: 时间同步器
    :param domain: API域
    :param params: URL参数
    :param data: 请求体数据
    :param method: HTTP方法
    :param is_auth_required: 是否需要认证
    :param limit_id: 限流ID
    :param timeout: 超时时间
    :param kwargs: 其他参数
    :return: API响应
    """
    # 如果未提供limit_id，使用path作为限流ID
    limit_id = limit_id or path
    
    # 重试逻辑
    for retry in range(3):
        try:
            # 创建REST助手
            rest_assistant: RESTAssistant = await api_factory.get_rest_assistant()
            
            # 准备请求参数
            url = private_rest_url(path) if is_auth_required else public_rest_url(path)
            
            # 使用限流器
            if throttler:
                await throttler.execute_task(limit_id=limit_id)
            
            # 发送请求
            response = await rest_assistant.execute_request(
                url=url,
                params=params,
                data=data,
                method=method,
                is_auth_required=is_auth_required,
                return_err=True,
                timeout=timeout,
                **kwargs,
            )
            
            # 解析响应
            response_data = await response.json()
            
            if response.status != 200:
                # 如果是时间同步错误，尝试同步时间
                if response_data.get("code") == -1021:  # 假设-1021是时间同步错误代码
                    if time_synchronizer:
                        await time_synchronizer.sync_time()
                        continue
                error_message = response_data.get("msg", f"Error executing request {method} {path}. HTTP status is {response.status}.")
                raise IOError(f"Error: {error_message}. Response: {response_data}")
            
            # 成功返回数据
            return response_data
        
        except ContentTypeError:
            raise IOError(f"Error parsing response for {method} {path}")
        except Exception as e:
            if retry < 2:  # 如果不是最后一次重试，则继续
                await asyncio.sleep(1)  # 等待1秒后重试
                continue
            else:  # 最后一次尝试失败，抛出异常
                raise IOError(f"Error executing request {method} {path}: {str(e)}")


async def get_current_server_time(
    throttler: Optional[AsyncThrottler] = None,
    domain: str = CONSTANTS.DEFAULT_DOMAIN,
) -> float:
    """
    获取服务器当前时间
    :param throttler: API限流器
    :param domain: API域
    :return: 服务器时间（秒）
    """
    api_factory = build_api_factory(throttler=throttler)
    response = await api_request(
        path="time",
        api_factory=api_factory,
        throttler=throttler,
        domain=domain,
        method="GET",
        limit_id=CONSTANTS.TIME_URL,
    )
    
    # 返回服务器时间（从毫秒转换为秒）
    return float(response.get("serverTime", 0)) / 1000.0 