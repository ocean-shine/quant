from decimal import Decimal
from typing import cast

from hummingbot.client.settings import AllConnectorSettings
from hummingbot.connector.gateway.amm.gateway_ethereum_amm import GatewayEthereumAMM
from hummingbot.connector.gateway.amm.gateway_solana_amm import GatewaySolanaAMM
from hummingbot.connector.gateway.common_types import Chain
from hummingbot.connector.gateway.gateway_price_shim import GatewayPriceShim
from hummingbot.core.rate_oracle.rate_oracle import RateOracle
from hummingbot.core.utils.fixed_rate_source import FixedRateSource
from hummingbot.strategy.amm_arb.zbit_amm_arb import ZbitAmmArbStrategy
from hummingbot.strategy.amm_arb.zbit_amm_arb_config_map import zbit_amm_arb_config_map
from hummingbot.strategy.market_trading_pair_tuple import MarketTradingPairTuple


def start(self):
    connector_1 = zbit_amm_arb_config_map.get("connector_1").value.lower()
    market_1 = zbit_amm_arb_config_map.get("market_1").value
    connector_2 = zbit_amm_arb_config_map.get("connector_2").value.lower()
    market_2 = zbit_amm_arb_config_map.get("market_2").value
    pool_id = "_" + zbit_amm_arb_config_map.get("pool_id").value
    order_amount = zbit_amm_arb_config_map.get("order_amount").value
    min_profitability = zbit_amm_arb_config_map.get("min_profitability").value / Decimal("100")
    market_1_slippage_buffer = zbit_amm_arb_config_map.get("market_1_slippage_buffer").value / Decimal("100")
    market_2_slippage_buffer = zbit_amm_arb_config_map.get("market_2_slippage_buffer").value / Decimal("100")
    concurrent_orders_submission = zbit_amm_arb_config_map.get("concurrent_orders_submission").value
    gateway_transaction_cancel_interval = zbit_amm_arb_config_map.get("gateway_transaction_cancel_interval").value
    rate_oracle_enabled = zbit_amm_arb_config_map.get("rate_oracle_enabled").value
    quote_conversion_rate = zbit_amm_arb_config_map.get("quote_conversion_rate").value
    order_refresh_time = zbit_amm_arb_config_map.get("order_refresh_time").value
    retry_interval = zbit_amm_arb_config_map.get("retry_interval").value
    max_retries = zbit_amm_arb_config_map.get("max_retries").value
    debug_mode = zbit_amm_arb_config_map.get("debug_mode").value
    
    # 配置Zbit API密钥（如果有的话）
    zbit_api_key = zbit_amm_arb_config_map.get("zbit_api_key").value
    zbit_secret_key = zbit_amm_arb_config_map.get("zbit_secret_key").value
    
    if "zbit" in connector_1 and (not zbit_api_key or not zbit_secret_key):
        self.notify("Zbit API密钥未设置，可能无法正常交易。请确保你已设置API密钥。")
    
    if "zbit" in connector_2 and (not zbit_api_key or not zbit_secret_key):
        self.notify("Zbit API密钥未设置，可能无法正常交易。请确保你已设置API密钥。")

    self._initialize_markets([(connector_1, [market_1]), (connector_2, [market_2])])
    base_1, quote_1 = market_1.split("-")
    base_2, quote_2 = market_2.split("-")

    is_connector_1_gateway = connector_1 in sorted(AllConnectorSettings.get_gateway_amm_connector_names())

    is_connector_2_gateway = connector_2 in sorted(AllConnectorSettings.get_gateway_amm_connector_names())

    market_info_1 = MarketTradingPairTuple(
        self.markets[connector_1], market_1 if not is_connector_1_gateway else market_1 + pool_id, base_1, quote_1
    )
    market_info_2 = MarketTradingPairTuple(
        self.markets[connector_2], market_2 if not is_connector_2_gateway else market_2 + pool_id, base_2, quote_2
    )
    self.market_trading_pair_tuples = [market_info_1, market_info_2]

    if debug_mode:
        amm_market_info: MarketTradingPairTuple = market_info_1
        other_market_info: MarketTradingPairTuple = market_info_2
        other_market_name: str = connector_2
        if ZbitAmmArbStrategy.is_gateway_market(other_market_info):
            amm_market_info = market_info_2
            other_market_info = market_info_1
            other_market_name = connector_1
        if Chain.ETHEREUM.chain == amm_market_info.market.chain:
            amm_connector: GatewayEthereumAMM = cast(GatewayEthereumAMM, amm_market_info.market)
        elif Chain.SOLANA.chain == amm_market_info.market.chain:
            amm_connector: GatewaySolanaAMM = cast(GatewaySolanaAMM, amm_market_info.market)
        else:
            raise ValueError(f"不支持的链: {amm_market_info.market.chain}")
        GatewayPriceShim.get_instance().patch_prices(
            other_market_name,
            other_market_info.trading_pair,
            amm_connector.connector_name,
            amm_connector.chain,
            amm_connector.network,
            amm_market_info.trading_pair
        )

    if rate_oracle_enabled:
        rate_source = RateOracle.get_instance()
    else:
        rate_source = FixedRateSource()
        rate_source.add_rate(f"{quote_2}-{quote_1}", Decimal(str(quote_conversion_rate)))   # 反向汇率已经在FixedRateSource find_rate方法中处理
        rate_source.add_rate(f"{quote_1}-{quote_2}", Decimal(str(1 / quote_conversion_rate)))   # 反向汇率已经在FixedRateSource find_rate方法中处理

    self.strategy = ZbitAmmArbStrategy()
    self.strategy.init_params(market_info_1=market_info_1,
                          market_info_2=market_info_2,
                          min_profitability=min_profitability,
                          order_amount=order_amount,
                          market_1_slippage_buffer=market_1_slippage_buffer,
                          market_2_slippage_buffer=market_2_slippage_buffer,
                          concurrent_orders_submission=concurrent_orders_submission,
                          gateway_transaction_cancel_interval=gateway_transaction_cancel_interval,
                          rate_source=rate_source,
                          order_refresh_time=order_refresh_time,
                          retry_interval=retry_interval,
                          max_retries=max_retries,
                          debug_mode=debug_mode,
                          )
                          
    # 输出启动信息
    self.notify(f"启动Zbit AMM套利策略，交易对：{market_1} 和 {market_2}")
    self.notify(f"最小盈利率：{min_profitability * 100}%，订单金额：{order_amount} {base_1}")
    if "zbit" in connector_1.lower() or "zbit" in connector_2.lower():
        self.notify("检测到Zbit交易所，已应用Zbit优化策略。")
    
    if debug_mode:
        self.notify("调试模式已启用，将记录详细日志。") 