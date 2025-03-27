from typing import Dict

# Zbit交易所REST API基础URL
REST_URL = "https://api.zbit.com"
# Zbit交易所期货API基础URL
FUTURES_URL = "https://futuresopenapi.91fafafa.com"

# API端点定义
PING_URL = "/api/v1/ping"              # 服务器连接测试端点
TIME_URL = "/api/v1/time"              # 服务器时间端点
EXCHANGE_INFO_URL = "/api/v1/exchangeInfo"  # 交易所信息端点
ORDER_BOOK_URL = "/api/v1/depth"       # 订单簿深度数据端点
RECENT_TRADES_URL = "/api/v1/trades"   # 最近成交记录端点
TICKER_PRICE_URL = "/api/v1/ticker/price"  # 价格行情端点
TICKER_BOOK_URL = "/api/v1/ticker/bookTicker"  # 最优买卖价端点
ORDER_URL = "/api/v1/order"            # 订单操作端点
ORDER_STATUS_URL = "/api/v1/order"     # 订单状态查询端点
OPEN_ORDERS_URL = "/api/v1/openOrders" # 当前挂单查询端点
ACCOUNT_URL = "/api/v1/account"        # 账户信息端点
MY_TRADES_URL = "/api/v1/myTrades"     # 用户交易记录端点

# API请求头
CONTENT_TYPE = "application/json"       # 内容类型
API_KEY_HEADER = "X-API-KEY"           # API密钥请求头
TIMESTAMP_HEADER = "X-TIMESTAMP"       # 时间戳请求头
SIGNATURE_HEADER = "X-SIGNATURE"       # 签名请求头

# 订单类型
ORDER_TYPE_LIMIT = "LIMIT"              # 限价单类型
ORDER_TYPE_MARKET = "MARKET"            # 市价单类型
ORDER_TYPE_LIMIT_MAKER = "LIMIT_MAKER"  # 限价只挂单类型
ORDER_TYPE_STOP_LOSS = "STOP_LOSS"      # 止损单类型
ORDER_TYPE_STOP_LOSS_LIMIT = "STOP_LOSS_LIMIT"  # 限价止损单类型
ORDER_TYPE_TAKE_PROFIT = "TAKE_PROFIT"  # 止盈单类型
ORDER_TYPE_TAKE_PROFIT_LIMIT = "TAKE_PROFIT_LIMIT"  # 限价止盈单类型

# 订单方向
ORDER_SIDE_BUY = "BUY"                  # 买单方向
ORDER_SIDE_SELL = "SELL"                # 卖单方向

# 订单状态
ORDER_STATUS_NEW = "NEW"                # 新建订单
ORDER_STATUS_PARTIALLY_FILLED = "PARTIALLY_FILLED"  # 部分成交
ORDER_STATUS_FILLED = "FILLED"          # 全部成交
ORDER_STATUS_CANCELED = "CANCELED"      # 已取消
ORDER_STATUS_PENDING_CANCEL = "PENDING_CANCEL"  # 取消中
ORDER_STATUS_REJECTED = "REJECTED"      # 已拒绝
ORDER_STATUS_EXPIRED = "EXPIRED"        # 已过期

# 订单有效期类型
TIME_IN_FORCE_GTC = "GTC"  # Good till canceled - 成交为止
TIME_IN_FORCE_IOC = "IOC"  # Immediate or cancel - 立即成交或取消
TIME_IN_FORCE_FOK = "FOK"  # Fill or kill - 全部成交或全部取消

# 交易规则默认值
DEFAULT_MIN_ORDER_SIZE = 0.00001        # 默认最小订单数量
DEFAULT_MAX_ORDER_SIZE = 1000           # 默认最大订单数量
DEFAULT_MIN_PRICE_INCREASE = 0.00001    # 默认最小价格增量
DEFAULT_MAX_PRICE_INCREASE = 1000000    # 默认最大价格增量
DEFAULT_MIN_BASE_AMOUNT = 0.00001       # 默认最小基础资产数量
DEFAULT_MAX_BASE_AMOUNT = 1000          # 默认最大基础资产数量
DEFAULT_MIN_QUOTE_AMOUNT = 0.00001      # 默认最小计价资产数量
DEFAULT_MAX_QUOTE_AMOUNT = 1000000      # 默认最大计价资产数量

# WebSocket配置
WSS_URL = "ws://34.124.196.15:8090/spot"  # WebSocket服务器URL
WS_HEARTBEAT_TIME_INTERVAL = 30          # WebSocket心跳间隔(秒)

# WebSocket消息类型
DIFF_EVENT_TYPE = "depthUpdate"          # 深度更新事件类型
TRADE_EVENT_TYPE = "trade"               # 交易事件类型
SNAPSHOT_EVENT_TYPE = "snapshot"         # 快照事件类型

# WebSocket订阅通道
ORDER_BOOK_CHANNEL = "subDepth"          # 订单簿订阅通道
TRADE_CHANNEL = "subTrade"               # 交易订阅通道

# API版本
API_VERSION = "v1"                       # API版本号
