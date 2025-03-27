#!/usr/bin/env python

import os

doc_content = """# ZBit现货-永续套利策略详细文档

## 一、策略概述

ZBit现货-永续套利策略是基于Hummingbot框架开发的高级交易策略，专为ZBit交易所设计，利用现货市场与永续合约市场之间的价格差异进行套利交易。该策略监控ZBit现货和永续合约市场之间的价格偏离，当价差达到预设阈值时在两个市场执行反向交易，通过锁定价差获取低风险收益。"""

# 确保scripts目录存在
os.makedirs("scripts", exist_ok=True)

# 文件路径
doc_path = "scripts/zbit_spot_perp_arbitrage_doc.md"

# 写入文件
with open(doc_path, "w") as f:
    f.write(doc_content)

print(f"文档已成功写入到 {os.path.abspath(doc_path)}") 