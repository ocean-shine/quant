#!/usr/bin/env python

from decimal import Decimal

def get_zbit_cross_exchange_config():
    """
    返回ZBit跨交易所做市策略的默认配置
    
    配置选项说明:
    - maker_market_trading_pair: ZBit上的交易对，如"BTC-USDT"
    - taker_market_trading_pair: 对手方市场上的交易对，如"BTC-USDT"
    - min_profitability: 最低盈利要求，例如0.01表示1%
    - order_amount: 每个订单的数量
    - min_order_amount: 最小订单数量
    - order_refresh_time: 订单刷新时间（秒）
    - order_refresh_tolerance_pct: 订单刷新容差百分比
    - active_order_canceling: 是否启用主动订单取消
    """
    return {
        # 市场配置
        "maker_market_trading_pair": "BTC-USDT",  # ZBit上的交易对
        "taker_market_trading_pair": "BTC-USDT",  # 对手方市场上的交易对
        
        # 订单参数
        "min_profitability": Decimal("0.01"),  # 最低盈利要求，1%
        "order_amount": Decimal("0.01"),  # 每个订单的BTC数量
        "min_order_amount": Decimal("0.001"),  # 最小订单数量
        
        # 订单管理
        "order_refresh_time": 30.0,  # 每30秒刷新一次订单
        "order_refresh_tolerance_pct": Decimal("0.02"),  # 2%的价格变动才刷新订单
        "active_order_canceling": True,  # 启用主动订单取消
        "cancel_order_threshold": Decimal("0.005"),  # 取消订单阈值，0.5%
        
        # 价格计算
        "top_depth_tolerance": Decimal("0.01"),  # 顶部深度容忍度，1%
        "anti_hysteresis_duration": 60.0,  # 防滞后持续时间，60秒
        "add_transaction_costs_to_orders": True,  # 在订单中添加交易成本
        "slippage_buffer": Decimal("0.05"),  # 滑点缓冲，5%
        
        # 订单优化
        "order_optimization_enabled": True,  # 启用订单优化
        "ask_order_optimization_depth": Decimal("0.1"),  # 卖单优化深度，0.1 BTC
        "bid_order_optimization_depth": Decimal("0.1"),  # 买单优化深度，0.1 BTC
        
        # 填充订单延迟
        "filled_order_delay": 60.0,  # 已成交订单延迟，60秒
        
        # 汇率转换
        "taker_to_maker_base_conversion_rate": Decimal("1.0"),  # 基础资产汇率，默认1:1
        "taker_to_maker_quote_conversion_rate": Decimal("1.0"),  # 报价资产汇率，默认1:1
        
        # 日志和报告
        "logging_options": 0xFF,  # 启用所有日志选项
        "status_report_interval": 900,  # 状态报告间隔，15分钟
    }

def get_taker_market_list():
    """
    返回可用的对手方交易所列表
    """
    return [
        "binance",
        "huobi",
        "okex",
        "kucoin",
        "gate_io",
        "coinbase_pro"
    ]

def get_trading_pair_examples():
    """
    返回常用交易对示例，按交易所分组
    """
    return {
        "zbit": [
            "BTC-USDT",
            "ETH-USDT",
            "BNB-USDT",
            "SOL-USDT",
            "ADA-USDT"
        ],
        "binance": [
            "BTC-USDT",
            "ETH-USDT",
            "BNB-USDT",
            "SOL-USDT",
            "ADA-USDT"
        ],
        "huobi": [
            "btcusdt",
            "ethusdt",
            "htusdt",
            "solusdt",
            "adausdt"
        ],
        "okex": [
            "BTC-USDT",
            "ETH-USDT",
            "OKB-USDT",
            "SOL-USDT",
            "ADA-USDT"
        ]
    } 