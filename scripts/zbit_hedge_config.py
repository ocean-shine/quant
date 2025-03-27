#!/usr/bin/env python

from decimal import Decimal
from typing import Dict, List

def get_zbit_hedge_config() -> Dict:
    """
    获取ZBit对冲策略的默认配置

    此配置用于ZBit交易所的对冲策略，可以通过基于价值或基于数量的方式
    实现资产在ZBit交易所和其他交易所之间的风险对冲。

    返回:
        Dict: 包含ZBit对冲策略配置的字典
    """
    return {
        # 基本策略配置
        "strategy": "hedge",
        "value_mode": True,                 # True表示基于价值对冲，False表示基于数量对冲
        "hedge_ratio": Decimal("1.0"),      # 对冲比率，1.0表示100%对冲
        "hedge_interval": 60,               # 对冲检查间隔（秒）
        "min_trade_size": Decimal("0.001"), # 最小交易规模（以基础资产计）
        "slippage": Decimal("0.005"),       # 滑点容忍度（0.5%）
        
        # ZBit对冲市场配置
        "hedge_connector": "zbit",          # 对冲交易所连接器名称
        "hedge_markets": ["BTC-USDT"],      # 对冲交易对
        "hedge_offsets": [Decimal("0.0")],  # 对冲偏移量
        "hedge_leverage": 1,                # 对冲杠杆（如果使用衍生品）
        "hedge_position_mode": "ONEWAY",    # 持仓模式：ONEWAY或HEDGE
        
        # 监控交易所配置
        "connector_0": {
            "connector": "binance",     # 监控交易所连接器名称
            "markets": ["BTC-USDT"],    # 监控交易对
            "offsets": [Decimal("0.0")] # 监控偏移量
        },
        "connector_1": "n",             # 不使用第二个监控交易所
        "connector_2": "n",             # 不使用第三个监控交易所
        "connector_3": "n",             # 不使用第四个监控交易所
        "connector_4": "n",             # 不使用第五个监控交易所
        
        # 高级设置
        "enable_auto_set_position_mode": False,  # 是否自动设置持仓模式
    }

def get_zbit_hedge_help() -> Dict:
    """
    获取ZBit对冲策略参数的帮助信息
    
    返回：
        Dict: 参数名称到帮助描述的映射
    """
    return {
        "strategy": "策略名称，固定为hedge",
        "value_mode": "对冲模式：True表示基于价值对冲，False表示基于数量对冲",
        "hedge_ratio": "对冲比率，表示对冲的百分比，1.0表示100%对冲",
        "hedge_interval": "对冲检查间隔，以秒为单位",
        "min_trade_size": "最小交易规模，以基础资产计",
        "slippage": "滑点容忍度，以小数表示，如0.005表示0.5%",
        
        "hedge_connector": "对冲交易所连接器名称，固定为zbit",
        "hedge_markets": "对冲交易对列表",
        "hedge_offsets": "对冲偏移量列表，与hedge_markets一一对应",
        "hedge_leverage": "对冲杠杆数值，如果使用衍生品",
        "hedge_position_mode": "持仓模式：ONEWAY或HEDGE",
        
        "connector_0": "第一个监控交易所的配置",
        "connector_0.connector": "监控交易所连接器名称",
        "connector_0.markets": "监控交易所的交易对列表",
        "connector_0.offsets": "监控交易所的偏移量列表",
        
        "connector_1": "第二个监控交易所的配置，'n'表示不使用",
        "connector_2": "第三个监控交易所的配置，'n'表示不使用",
        "connector_3": "第四个监控交易所的配置，'n'表示不使用",
        "connector_4": "第五个监控交易所的配置，'n'表示不使用",
        
        "enable_auto_set_position_mode": "是否自动设置持仓模式"
    }

def get_default_params() -> Dict:
    """
    获取用于UI显示的默认参数
    
    返回：
        Dict: 默认参数字典
    """
    return {
        "exchange": "zbit",
        "trading_pair": "BTC-USDT",
        "monitor_exchange": "binance",
        "monitor_trading_pair": "BTC-USDT",
        "hedge_ratio": Decimal("1.0"),
        "hedge_interval": 60,
        "min_trade_size": Decimal("0.001"),
        "slippage": Decimal("0.005"),
        "value_mode": True
    } 