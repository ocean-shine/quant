#!/usr/bin/env python

import logging
import os
import sys
from decimal import Decimal
from datetime import datetime

# 设置Python路径，确保可以导入hummingbot模块
sys.path.insert(0, os.path.realpath(os.path.join(__file__, "../../")))

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 确保日志目录存在
if not os.path.exists("scripts/logs"):
    os.makedirs("scripts/logs")

# 配置文件日志
file_handler = logging.FileHandler("scripts/logs/test_zbit_perpetual_market_making.log")
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)
logger.info("日志将保存到: %s", os.path.realpath("scripts/logs/test_zbit_perpetual_market_making.log"))

def test_perpetual_market_making_config():
    """测试永续市场做市策略配置"""
    logger.info("\n============ ZBit永续市场做市策略配置测试 ============")
    
    logger.info("1. 市场配置:")
    market_config = {
        "交易所": "ZBit Perpetual",
        "交易对": "BTC-USDT",
        "基础资产": "BTC",
        "报价资产": "USDT",
        "杠杆": 10,
        "持仓模式": "Hedge"  # Hedge(对冲模式) 或 ONEWAY(单向模式)
    }
    
    for key, value in market_config.items():
        logger.info(f"  {key}: {value}")
    
    logger.info("\n2. 策略参数:")
    strategy_params = {
        "买单价差": "0.01",  # 1%
        "卖单价差": "0.01",  # 1%
        "订单数量": "0.01",  # BTC
        "多头止盈价差": "0.02",  # 2%
        "空头止盈价差": "0.02",  # 2%
        "止损价差": "0.05",  # 5%
        "止损订单间隔时间": "60秒",
        "止损滑点缓冲": "0.001",  # 0.1%
        "订单层级数": "3",
        "层级价差": "0.005",  # 0.5%
        "层级数量": "0.005",  # BTC
        "订单刷新时间": "30秒",
        "订单刷新容差": "0.01",  # 1%
        "成交订单延迟": "30秒",
        "订单优化": "启用",
        "卖单优化深度": "0.5",  # 50%
        "买单优化深度": "0.5",  # 50%
        "价格类型": "中间价格",
        "价格上限": "55000 USDT",
        "价格下限": "45000 USDT",
        "最小价差": "0.005",  # 0.5%
    }
    
    for key, value in strategy_params.items():
        logger.info(f"  {key}: {value}")
    
    logger.info("\n3. 模拟市场状态:")
    market_status = {
        "BTC价格": "50000 USDT",
        "BTC可用余额": "1 BTC",
        "USDT可用余额": "10000 USDT",
        "当前资金费率": "0.0001",  # 0.01%
        "下次资金费时间": datetime.fromtimestamp(int(datetime.now().timestamp()) + 3600).strftime("%Y-%m-%d %H:%M:%S"),
    }
    
    for key, value in market_status.items():
        logger.info(f"  {key}: {value}")
    
    logger.info("\n4. 预期策略行为:")
    expected_behavior = [
        "在BTC-USDT市场创建买单和卖单，价格分别为中间价格的上下1%",
        "每30秒刷新订单（如果价格变化超过1%）",
        "订单将分为3个层级，每个层级的价差增加0.5%",
        "如果价格超出上限（55000 USDT）或下限（45000 USDT），策略会停止创建新订单",
        "当多头头寸盈利达到2%时，策略会尝试平仓获利",
        "当空头头寸盈利达到2%时，策略会尝试平仓获利",
        "如果任何头寸亏损达到5%，策略会触发止损平仓"
    ]
    
    for idx, behavior in enumerate(expected_behavior, 1):
        logger.info(f"  {idx}. {behavior}")
    
    logger.info("\n5. 风险控制:")
    risk_controls = [
        "使用止损订单保护头寸，亏损达到5%时平仓",
        "使用价格上下限（45000-55000 USDT）防止在极端市场条件下交易",
        "订单优化功能帮助获得更好的成交价格",
        "多层级订单分散风险，避免大量资金集中在单一价格点"
    ]
    
    for idx, control in enumerate(risk_controls, 1):
        logger.info(f"  {idx}. {control}")
    
    logger.info("\n============ 测试完成 ============")

def main():
    """主函数"""
    print("正在运行ZBit永续市场做市策略测试...")
    test_perpetual_market_making_config()
    print("ZBit永续市场做市策略测试完成")

if __name__ == "__main__":
    main() 