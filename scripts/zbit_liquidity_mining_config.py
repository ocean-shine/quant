#!/usr/bin/env python

from decimal import Decimal
from typing import Dict, Any, Union

def get_zbit_liquidity_mining_config() -> Dict[str, Any]:
    """
    获取ZBit流动性挖矿策略的默认配置
    
    :return: 配置字典
    """
    return {
        # 基本策略配置
        "strategy": "zbit_liquidity_mining",
        "version": "1.0.0",
        
        # 交易所配置
        "exchange": "zbit",
        "markets": ["BTC-USDT", "ETH-USDT"],  # 默认交易对
        
        # 代币配置
        "token": "USDT", # 要挖矿的代币，必须是交易对中的基础或报价代币
        
        # 订单配置
        "order_amount": Decimal("0.01"), # 以token为单位的订单大小
        "spread": Decimal("0.01"), # 1% 价差
        "order_refresh_time": 60.0, # 每60秒刷新一次订单
        "order_refresh_tolerance_pct": Decimal("0.2"), # 0.2%刷新容忍度
        "max_order_age": 3600.0, # 订单最大生存时间为1小时
        
        # 库存配置
        "inventory_skew_enabled": True, # 启用库存偏斜
        "target_base_pct": Decimal("0.5"), # 目标是50%的基础资产
        "inventory_range_multiplier": Decimal("1"), # 库存范围乘数
        
        # 波动率配置
        "volatility_interval": 300, # 5分钟波动率间隔
        "avg_volatility_period": 10, # 10个周期的平均波动率
        "volatility_to_spread_multiplier": Decimal("1"), # 波动率到价差的乘数为1
        "max_spread": Decimal("-1"), # 忽略最大价差设置
        
        # 高级配置
        "status_report_interval": 900, # 每15分钟报告一次状态
        "hb_app_notification": False, # 不启用Hummingbot应用通知
    }

def get_zbit_liquidity_mining_config_help() -> Dict[str, str]:
    """
    获取ZBit流动性挖矿策略的配置帮助信息
    
    :return: 配置帮助信息字典
    """
    return {
        "exchange": "交易所名称(zbit)",
        "markets": "要参与流动性挖矿的交易对列表，格式为 BASE-QUOTE (例如 BTC-USDT, ETH-USDT)",
        "token": "要挖矿的代币，必须是交易对中的基础或报价代币。这决定了做市策略将如何分配预算",
        "order_amount": "每个订单的大小，以token为单位",
        "spread": "买卖订单相对于中间价格的价差百分比。例如，输入0.01表示1%的价差",
        "order_refresh_time": "取消和重新创建订单的时间间隔，以秒为单位",
        "order_refresh_tolerance_pct": "每个周期刷新订单所需的价格变化百分比",
        "max_order_age": "订单的最长生命周期，以秒为单位。超过此时间的订单将被取消",
        "inventory_skew_enabled": "是否启用库存偏斜功能，用于根据当前持仓调整买卖订单量",
        "target_base_pct": "目标基础资产百分比。例如，0.5表示目标是50%的基础资产和50%的报价资产",
        "inventory_range_multiplier": "库存管理的范围乘数，影响买卖订单的偏斜程度",
        "volatility_interval": "计算市场波动率的时间间隔，以秒为单位",
        "avg_volatility_period": "计算平均波动率的周期数",
        "volatility_to_spread_multiplier": "将波动率转换为价差的乘数",
        "max_spread": "最大允许的价差百分比。-1表示忽略此设置",
        "status_report_interval": "状态报告的时间间隔，以秒为单位",
        "hb_app_notification": "是否启用Hummingbot应用通知",
    }

def get_default_params() -> Dict[str, Any]:
    """
    获取用于UI显示的默认参数
    
    :return: 默认参数字典
    """
    return {
        "markets": ["BTC-USDT", "ETH-USDT"],
        "token": "USDT",
        "order_amount": 0.01,
        "spread": 0.01,
        "order_refresh_time": 60.0,
        "target_base_pct": 0.5,
    }

def check_config(config: Dict[str, Any]) -> Union[Dict[str, Any], str]:
    """
    检查配置参数的有效性
    
    :param config: 配置字典
    :return: 如果配置有效，返回配置字典；否则返回错误信息
    """
    # 检查必需参数
    required_params = ["exchange", "markets", "token", "order_amount", "spread"]
    for param in required_params:
        if param not in config:
            return f"缺少必需参数: {param}"
    
    # 检查token是否在交易对中
    token = config["token"]
    markets = config["markets"]
    token_found = False
    for market in markets:
        if "-" not in market:
            return f"无效的市场格式: {market}，正确格式应为 BASE-QUOTE (例如 BTC-USDT)"
        base, quote = market.split("-")
        if token == base or token == quote:
            token_found = True
            break
    
    if not token_found:
        return f"代币 {token} 不在任何指定的交易对中"
    
    # 检查数值参数
    numeric_params = [
        "order_amount", "spread", "order_refresh_time", "order_refresh_tolerance_pct",
        "target_base_pct", "inventory_range_multiplier", "volatility_interval",
        "avg_volatility_period", "volatility_to_spread_multiplier", "max_spread",
        "max_order_age", "status_report_interval"
    ]
    
    for param in numeric_params:
        if param in config and not isinstance(config[param], (int, float, Decimal)):
            return f"参数 {param} 必须是数字"
    
    # 检查范围值
    if "spread" in config and config["spread"] <= 0:
        return "价差必须大于0"
    
    if "order_refresh_time" in config and config["order_refresh_time"] <= 0:
        return "订单刷新时间必须大于0"
    
    if "target_base_pct" in config and (config["target_base_pct"] < 0 or config["target_base_pct"] > 1):
        return "目标基础资产百分比必须在0到1之间"
    
    return config