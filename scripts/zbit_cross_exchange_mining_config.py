#!/usr/bin/env python

from decimal import Decimal
from typing import Dict, Any


def get_zbit_cross_exchange_mining_config() -> Dict[str, Any]:
    """
    获取ZBit跨交易所挖矿策略的默认配置。
    
    跨交易所挖矿策略通过在做市商市场(ZBit)和对手方市场之间进行套利交易，
    同时通过维持做市深度获取ZBit交易所的挖矿收益。
    
    返回:
        Dict[str, Any]: 包含策略配置参数的字典
    """
    return {
        # 基础配置
        "strategy": "zbit_cross_exchange_mining",
        "version": "1.0.0",
        
        # 交易对配置
        "maker_market_trading_pair": "BTC-USDT",      # ZBit交易所的交易对
        "taker_market_trading_pair": "BTC-USDT",      # 对手方交易所的交易对
        
        # 订单配置
        "order_amount": Decimal("0.1"),               # 订单量，这里设为0.1 BTC
        "min_order_amount": Decimal("0.01"),          # 最小订单数量，低于此数量不会创建订单
        "order_refresh_time": 30.0,                   # 每30秒刷新订单
        "order_refresh_tolerance_pct": Decimal("0.2"), # 价格波动小于0.2%不更新订单
        
        # 盈利配置
        "min_profitability": Decimal("1.0"),          # 最低盈利要求，1%，小于此值不会执行交易
        "min_prof_tol_high": Decimal("2.0"),          # 最低盈利容忍度上限，盈利超过此值时调整订单
        "min_prof_tol_low": Decimal("0.1"),           # 最低盈利容忍度下限，盈利低于此值时调整订单
        
        # 费率配置
        "rate_curve": Decimal("0.001"),               # 费率曲线，用于调整挖矿收益计算
        "trade_fee": Decimal("0.001"),                # 交易费用，0.1%
        
        # 风险管理配置
        "balance_adjustment_duration": 0,             # 余额调整持续时间，0表示不自动调整
        "volatility_buffer_size": 10,                 # 波动性缓冲区大小，用于计算价格波动
        "slippage_buffer": Decimal("5.0"),            # 滑点缓冲5%，考虑到市场深度和订单执行
        "min_prof_adj_timer": 60.0,                   # 最低盈利调整计时器，60秒，控制调整频率
        
        # 高级配置
        "logging_options": (0x7f),                    # 日志级别，默认记录所有事件
        "status_report_interval": 900,                # 状态报告间隔，每15分钟生成一次
        "hb_app_notification": False,                 # 是否启用Hummingbot应用通知
    }


def get_zbit_cross_exchange_mining_help() -> Dict[str, str]:
    """
    获取ZBit跨交易所挖矿策略配置参数的帮助信息。
    
    返回:
        Dict[str, str]: 配置参数的帮助信息
    """
    return {
        "strategy": "策略名称，固定为zbit_cross_exchange_mining",
        "version": "策略版本号",
        
        "maker_market_trading_pair": "ZBit交易所的交易对，例如：BTC-USDT",
        "taker_market_trading_pair": "对手方交易所的交易对，例如：BTC-USDT",
        
        "order_amount": "每个订单的资产数量，以基础资产计",
        "min_order_amount": "最小订单数量，低于此数量不会创建订单",
        "order_refresh_time": "订单刷新时间，单位为秒",
        "order_refresh_tolerance_pct": "订单刷新容忍度百分比，价格变动小于此值时不更新订单",
        
        "min_profitability": "最低盈利要求百分比，低于此值不执行交易",
        "min_prof_tol_high": "最低盈利容忍度上限，盈利超过此值时调整订单",
        "min_prof_tol_low": "最低盈利容忍度下限，盈利低于此值时调整订单",
        
        "rate_curve": "费率曲线，用于调整挖矿收益计算",
        "trade_fee": "交易费用百分比",
        
        "balance_adjustment_duration": "余额调整持续时间，0表示不自动调整",
        "volatility_buffer_size": "波动性缓冲区大小，用于计算价格波动",
        "slippage_buffer": "滑点缓冲百分比，考虑到市场深度和订单执行",
        "min_prof_adj_timer": "最低盈利调整计时器，控制调整频率",
        
        "logging_options": "日志级别，控制记录哪些事件",
        "status_report_interval": "状态报告间隔，单位为秒",
        "hb_app_notification": "是否启用Hummingbot应用通知",
    }


def get_default_params():
    """
    获取默认参数值，供UI显示使用
    """
    params = get_zbit_cross_exchange_mining_config()
    return {
        "maker_market_trading_pair": params["maker_market_trading_pair"],
        "taker_market_trading_pair": params["taker_market_trading_pair"],
        "order_amount": str(params["order_amount"]),
        "min_profitability": str(params["min_profitability"]),
        "order_refresh_time": str(params["order_refresh_time"]),
        "order_refresh_tolerance_pct": str(params["order_refresh_tolerance_pct"]),
        "min_order_amount": str(params["min_order_amount"]),
    } 