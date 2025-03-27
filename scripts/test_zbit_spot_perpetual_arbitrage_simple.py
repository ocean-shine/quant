#!/usr/bin/env python

import logging
import os
import sys
from decimal import Decimal
from datetime import datetime

# 设置Python路径，确保可以导入hummingbot模块
sys.path.insert(0, os.path.realpath(os.path.join(__file__, "../../")))

# 导入策略模块
from hummingbot.strategy.spot_perpetual_arbitrage.zbit_spot_perp_arbitrage import ZbitSpotPerpArbitrageStrategy

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 确保日志目录存在
if not os.path.exists("scripts/logs"):
    os.makedirs("scripts/logs")

# 配置文件日志
file_handler = logging.FileHandler("scripts/logs/zbit_spot_perp_arbitrage_test.log")
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)
logger.info("日志将保存到: %s", os.path.realpath("scripts/logs/zbit_spot_perp_arbitrage_test.log"))

def test_zbit_strategy_initialization():
    """测试ZBit策略初始化"""
    logger.info("测试ZBit现货-永续套利策略初始化...")
    
    try:
        strategy = ZbitSpotPerpArbitrageStrategy()
        logger.info("策略实例创建成功")
        
        # 打印策略说明
        logger.info(f"策略类: {strategy.__class__.__name__}")
        logger.info(f"策略描述: {strategy.__class__.__doc__.strip() if strategy.__class__.__doc__ else '无描述'}")
        
        logger.info("=== ZBit现货-永续套利策略基本参数说明 ===")
        logger.info("1. 套利原理:")
        logger.info("   - 当永续合约价格高于现货价格达到阈值时: 现货买入 + 永续做空")
        logger.info("   - 当永续合约价格低于现货价格达到阈值时: 现货卖出 + 永续做多")
        logger.info("   - 当价差收敛或反向达到阈值时平仓")
        
        logger.info("2. ZBit特有优化:")
        logger.info("   - 订单簿深度分析: 利用ZBit订单簿数据优化套利价格")
        logger.info("   - 资金费率监控: 根据资金费率调整套利策略")
        logger.info("   - 费率层级适配: 根据用户费率层级优化交易决策")
        
        logger.info("3. 风险管理:")
        logger.info("   - 价格风险: 通过设置最小套利阈值控制")
        logger.info("   - 资金费率风险: 通过监控资金费率调整策略")
        logger.info("   - 流动性风险: 通过订单簿分析和滑点缓冲控制")
        
        logger.info("=== 套利参数示例 ===")
        logger.info("  最小开仓套利阈值: 0.2% (可根据市场波动调整)")
        logger.info("  最小平仓套利阈值: 0.1% (可设为负值以保证能平仓)")
        logger.info("  订单数量: 0.01 BTC (根据资金规模调整)")
        logger.info("  杠杆倍数: 10倍 (根据风险偏好调整)")
        logger.info("  滑点缓冲: 0.05% (根据市场流动性调整)")
        
        logger.info("测试ZBit策略初始化成功")
        return True
    except Exception as e:
        logger.error(f"测试ZBit策略初始化失败: {e}", exc_info=True)
        return False

def test_zbit_strategy_config_examples():
    """测试ZBit策略配置示例"""
    logger.info("\n=== ZBit现货-永续套利策略配置示例 ===")
    
    # 低波动市场配置示例
    logger.info("\n低波动市场配置:")
    logger.info("""
spot_connector: zbit
spot_markets: ["BTC-USDT"]
perpetual_connector: zbit_perpetual
perpetual_markets: ["BTC-USDT"]
order_amount: 0.005
perpetual_leverage: 5
min_opening_arbitrage_pct: 0.1
min_closing_arbitrage_pct: 0.05
spot_market_slippage_buffer: 0.02
perpetual_market_slippage_buffer: 0.02
next_arbitrage_opening_delay: 60
    """)
    
    # 中波动市场配置示例
    logger.info("\n中波动市场配置:")
    logger.info("""
spot_connector: zbit
spot_markets: ["BTC-USDT"]
perpetual_connector: zbit_perpetual
perpetual_markets: ["BTC-USDT"]
order_amount: 0.01
perpetual_leverage: 10
min_opening_arbitrage_pct: 0.2
min_closing_arbitrage_pct: 0.1
spot_market_slippage_buffer: 0.05
perpetual_market_slippage_buffer: 0.05
next_arbitrage_opening_delay: 30
    """)
    
    # 高波动市场配置示例
    logger.info("\n高波动市场配置:")
    logger.info("""
spot_connector: zbit
spot_markets: ["BTC-USDT"]
perpetual_connector: zbit_perpetual
perpetual_markets: ["BTC-USDT"]
order_amount: 0.015
perpetual_leverage: 15
min_opening_arbitrage_pct: 0.5
min_closing_arbitrage_pct: 0.2
spot_market_slippage_buffer: 0.1
perpetual_market_slippage_buffer: 0.1
next_arbitrage_opening_delay: 20
    """)
    
    return True

def simulate_zbit_arbitrage_example():
    """模拟ZBit套利示例流程"""
    logger.info("\n=== ZBit套利模拟示例 ===")
    
    # 模拟市场数据
    spot_price = Decimal("50000")
    perp_price = Decimal("50150")  # 永续价格高0.3%
    
    # 计算套利机会
    price_diff_pct = (perp_price - spot_price) / spot_price
    logger.info(f"现货价格: {spot_price} USDT")
    logger.info(f"永续价格: {perp_price} USDT")
    logger.info(f"价差百分比: {price_diff_pct:.4%}")
    
    # 判断套利方向
    if price_diff_pct >= Decimal("0.002"):  # 0.2%的开仓阈值
        logger.info("检测到套利机会: 永续价格高于现货价格")
        logger.info("套利方向: 现货买入 + 永续做空")
        
        # 模拟订单参数
        order_amount = Decimal("0.01")  # BTC
        leverage = 10
        
        # 计算资金需求
        spot_cost = order_amount * spot_price
        perp_margin = (order_amount * perp_price) / leverage
        
        logger.info(f"现货买入数量: {order_amount} BTC @ {spot_price} USDT")
        logger.info(f"现货买入成本: {spot_cost} USDT")
        logger.info(f"永续做空数量: {order_amount} BTC @ {perp_price} USDT")
        logger.info(f"永续保证金需求: {perp_margin} USDT (杠杆: {leverage}倍)")
        
        # 计算预期收益
        expected_profit_pct = price_diff_pct - Decimal("0.001")  # 减去手续费
        expected_profit = spot_cost * expected_profit_pct
        
        logger.info(f"预期收益率: {expected_profit_pct:.4%}")
        logger.info(f"预期收益(不考虑滑点): {expected_profit} USDT")
        
        # 模拟平仓场景
        logger.info("\n平仓场景:")
        convergence_price = Decimal("50030")  # 价格收敛
        
        logger.info(f"假设价格收敛至: {convergence_price} USDT")
        new_price_diff_pct = (convergence_price - spot_price) / spot_price
        logger.info(f"新价差百分比: {new_price_diff_pct:.4%}")
        
        # 平仓收益
        closing_profit = (perp_price - convergence_price) * order_amount + (convergence_price - spot_price) * order_amount
        closing_profit_pct = closing_profit / spot_cost
        
        logger.info(f"平仓收益: {closing_profit} USDT")
        logger.info(f"平仓收益率: {closing_profit_pct:.4%}")
        
    else:
        logger.info("未检测到足够的套利机会")
    
    return True

def main():
    print("运行ZBit现货-永续套利策略测试...")
    
    # 运行测试
    test_zbit_strategy_initialization()
    test_zbit_strategy_config_examples()
    simulate_zbit_arbitrage_example()
    
    print("ZBit现货-永续套利策略测试完成")

if __name__ == "__main__":
    main() 