from hummingbot.core.api_throttler.data_types import LinkedLimitWeightPair, RateLimit
from hummingbot.core.data_type.in_flight_order import OrderState

# 基本常量
EXCHANGE_NAME = "zbit_perpetual"
REST_URL = "https://api.zbit.com"
WSS_URL = "wss://stream.zbit.com"
API_VERSION = "v1"

# API URLs
REST_URL_AUTH = f"{REST_URL}/{API_VERSION}/private"
REST_URL_PUBLIC = f"{REST_URL}/{API_VERSION}/public"
WSS_URL_PUBLIC = f"{WSS_URL}/ws/public/v1"
WSS_URL_PRIVATE = f"{WSS_URL}/ws/private/v1"

# 公共API路径
PING_URL = f"{REST_URL_PUBLIC}/ping"
TIME_URL = f"{REST_URL_PUBLIC}/time"
EXCHANGE_INFO_URL = f"{REST_URL_PUBLIC}/exchangeInfo"
ORDER_BOOK_URL = f"{REST_URL_PUBLIC}/depth"
FUNDING_INFO_URL = f"{REST_URL_PUBLIC}/fundingInfo"

# 私有API路径
ACCOUNTS_URL = f"{REST_URL_AUTH}/account"
POSITIONS_URL = f"{REST_URL_AUTH}/positions"
ORDER_URL = f"{REST_URL_AUTH}/order"
ORDERS_URL = f"{REST_URL_AUTH}/orders"
CANCEL_ORDER_URL = f"{REST_URL_AUTH}/cancel"
LEVERAGE_URL = f"{REST_URL_AUTH}/leverage"
POSITION_MODE_URL = f"{REST_URL_AUTH}/positionMode"

# WebSocket频道
WS_PING_REQUEST = "ping"
WS_SUBSCRIPTION_URL = "subscribe"
WS_UNSUBSCRIPTION_URL = "unsubscribe"
WS_AUTHENTICATE_URL = "auth"
WS_TRADE_CHANNEL = "trade"
WS_ORDERBOOK_CHANNEL = "orderBook"
WS_ORDER_CHANNEL = "order"
WS_POSITION_CHANNEL = "position"
WS_ACCOUNT_CHANNEL = "account"
WS_FUNDING_INFO_CHANNEL = "fundingInfo"

# 订单状态映射
ORDER_STATE = {
    "NEW": OrderState.OPEN,
    "PARTIALLY_FILLED": OrderState.PARTIALLY_FILLED,
    "FILLED": OrderState.FILLED,
    "CANCELED": OrderState.CANCELED,
    "PENDING_CANCEL": OrderState.PENDING_CANCEL,
    "REJECTED": OrderState.FAILED,
    "EXPIRED": OrderState.FAILED
}

# 位置模式
POSITION_MODE_HEDGE = "Hedge"
POSITION_MODE_ONEWAY = "OneWay"
DEFAULT_POSITION_MODE = POSITION_MODE_HEDGE

# 时间常量
SECONDS_TO_WAIT_TO_RECEIVE_MESSAGE = 30  # 等待接收消息的秒数
MESSAGE_TIMEOUT = 30.0                   # 消息超时时间（秒）
PING_INTERVAL = 30.0                     # ping间隔时间（秒）
UPDATE_ORDER_STATUS_MIN_INTERVAL = 10.0  # 最小订单状态更新间隔（秒）
FUNDING_SETTLEMENT_DURATION = [30, 30]   # 资金结算持续时间 [开始前，结束后]

# API限流配置
RATE_LIMITS = [
    # 公共接口限流
    RateLimit(limit_id=PING_URL, limit=10, time_interval=1),
    RateLimit(limit_id=TIME_URL, limit=10, time_interval=1),
    RateLimit(limit_id=EXCHANGE_INFO_URL, limit=10, time_interval=1),
    RateLimit(limit_id=ORDER_BOOK_URL, limit=10, time_interval=1),
    RateLimit(limit_id=FUNDING_INFO_URL, limit=10, time_interval=1),
    
    # 私有接口限流
    RateLimit(limit_id=ACCOUNTS_URL, limit=5, time_interval=1),
    RateLimit(limit_id=POSITIONS_URL, limit=5, time_interval=1),
    RateLimit(limit_id=ORDER_URL, limit=10, time_interval=1),
    RateLimit(limit_id=ORDERS_URL, limit=10, time_interval=1),
    RateLimit(limit_id=CANCEL_ORDER_URL, limit=10, time_interval=1),
    RateLimit(limit_id=LEVERAGE_URL, limit=2, time_interval=1),
    RateLimit(limit_id=POSITION_MODE_URL, limit=2, time_interval=1),
]

# 其他常量
MAX_ORDER_ID_LEN = 32                   # 最大订单ID长度
DEFAULT_DOMAIN = "main"                 # 默认域
BROKER_ID = "HBOT"                      # 经纪商ID
DEFAULT_LEVERAGE = 1                    # 默认杠杆
MAX_LEVERAGE = 100                      # 最大杠杆
DEFAULT_FUNDING_SETTLEMENT_TIME = 28800  # 默认资金结算时间（秒） 