from decimal import Decimal
from typing import Optional

from hummingbot.client.config.config_data_types import BaseClientModel, ClientFieldData
from hummingbot.client.config.config_validators import (
    validate_decimal,
    validate_exchange,
    validate_market_trading_pair,
    validate_time_delta,
)
from hummingbot.client.settings import AllConnectorSettings, required_exchanges


def trading_pair_prompt():
    exchange = "zbit"
    example = AllConnectorSettings.get_example_pairs().get(exchange)
    return "Enter the trading pair to trade on Zbit (e.g. %s) >>> " % example


def str2bool(value: str):
    return str(value).lower() in ("yes", "true", "t", "1")


class ZbitTwapConfigMap(BaseClientModel):
    connector: str = ClientFieldData(
        prompt=lambda: "Enter the name of the exchange >>> ",
        prompt_on_new=True,
        validator=lambda x: validate_exchange(x),
    )
    trading_pair: str = ClientFieldData(
        prompt=trading_pair_prompt,
        prompt_on_new=True,
        validator=lambda x: validate_market_trading_pair(x),
    )
    trade_side: str = ClientFieldData(
        prompt=lambda: "Enter the trade side (buy/sell) >>> ",
        prompt_on_new=True,
        validator=lambda x: x in ["buy", "sell"],
    )
    target_asset_amount: Decimal = ClientFieldData(
        prompt=lambda: "Enter the total amount of base asset to trade >>> ",
        prompt_on_new=True,
        validator=lambda v: validate_decimal(v, min_value=Decimal("0")),
    )
    order_step_size: Decimal = ClientFieldData(
        prompt=lambda: "Enter the amount to be traded in each order >>> ",
        prompt_on_new=True,
        validator=lambda v: validate_decimal(v, min_value=Decimal("0")),
    )
    order_price: Decimal = ClientFieldData(
        prompt=lambda: "Enter the price for the orders >>> ",
        prompt_on_new=True,
        validator=lambda v: validate_decimal(v, min_value=Decimal("0")),
    )
    order_delay_time: float = ClientFieldData(
        prompt=lambda: "Enter the delay between orders in seconds >>> ",
        prompt_on_new=True,
        validator=lambda v: validate_time_delta(v),
    )
    cancel_order_wait_time: float = ClientFieldData(
        prompt=lambda: "Enter the time to wait before canceling orders in seconds >>> ",
        prompt_on_new=True,
        validator=lambda v: validate_time_delta(v),
    )
    is_time_span_execution: bool = ClientFieldData(
        prompt=lambda: "Do you want to specify a time span for the execution? (Yes/No) >>> ",
        prompt_on_new=True,
        validator=lambda v: str2bool(v),
    )
    start_datetime: Optional[str] = ClientFieldData(
        prompt=lambda: "Enter the start date and time (YYYY-MM-DD HH:MM:SS) >>> ",
        prompt_on_new=True,
        validator=lambda v: validate_time_delta(v),
    )
    end_datetime: Optional[str] = ClientFieldData(
        prompt=lambda: "Enter the end date and time (YYYY-MM-DD HH:MM:SS) >>> ",
        prompt_on_new=True,
        validator=lambda v: validate_time_delta(v),
    )
    is_delayed_start_execution: bool = ClientFieldData(
        prompt=lambda: "Do you want to specify a delayed start time? (Yes/No) >>> ",
        prompt_on_new=True,
        validator=lambda v: str2bool(v),
    )

    class Config:
        title = "zbit_twap"

    def validate_start_end_datetime(self) -> Optional[str]:
        if self.is_time_span_execution:
            if not self.start_datetime or not self.end_datetime:
                return "Start and end datetime must be specified for time span execution"
            if self.start_datetime >= self.end_datetime:
                return "Start datetime must be before end datetime"
        return None

    def validate_delayed_start(self) -> Optional[str]:
        if self.is_delayed_start_execution and not self.start_datetime:
            return "Start datetime must be specified for delayed start execution"
        return None

    def validate(self) -> Optional[str]:
        error = self.validate_start_end_datetime()
        if error:
            return error
        error = self.validate_delayed_start()
        if error:
            return error
        return None


zbit_twap_config_map = ZbitTwapConfigMap.construct() 