import logging
import os
from decimal import Decimal
from typing import Dict, List
import yaml
import argparse
import time
import asyncio
import importlib

from pydantic import Field

from hummingbot.client.config.config_data_types import BaseClientModel, ClientFieldData
from hummingbot.connector.connector_base import ConnectorBase
from hummingbot.core.data_type.common import OrderType, PriceType, TradeType
from hummingbot.core.data_type.order_candidate import OrderCandidate
from hummingbot.core.event.events import OrderFilledEvent
from hummingbot.strategy.script_strategy_base import ScriptStrategyBase
from hummingbot.core.clock import Clock, ClockMode
from hummingbot.client.settings import AllConnectorSettings


class SimplePMMConfig(BaseClientModel):
    script_file_name: str = Field(default_factory=lambda: os.path.basename(__file__))
    exchange: str = Field("binance_paper_trade", client_data=ClientFieldData(
        prompt_on_new=True, prompt=lambda mi: "Exchange where the bot will trade"))
    trading_pair: str = Field("ETH-USDT", client_data=ClientFieldData(
        prompt_on_new=True, prompt=lambda mi: "Trading pair in which the bot will place orders"))
    order_amount: Decimal = Field(0.01, client_data=ClientFieldData(
        prompt_on_new=True, prompt=lambda mi: "Order amount (denominated in base asset)"))
    bid_spread: Decimal = Field(0.001, client_data=ClientFieldData(
        prompt_on_new=True, prompt=lambda mi: "Bid order spread (in percent)"))
    ask_spread: Decimal = Field(0.001, client_data=ClientFieldData(
        prompt_on_new=True, prompt=lambda mi: "Ask order spread (in percent)"))
    order_refresh_time: int = Field(15, client_data=ClientFieldData(
        prompt_on_new=True, prompt=lambda mi: "Order refresh time (in seconds)"))
    price_type: str = Field("mid", client_data=ClientFieldData(
        prompt_on_new=True, prompt=lambda mi: "Price type to use (mid or last)"))


class SimplePMM(ScriptStrategyBase):
    """
    BotCamp Cohort: Sept 2022
    Design Template: https://hummingbot-foundation.notion.site/Simple-PMM-63cc765486dd42228d3da0b32537fc92
    Video: -
    Description:
    The bot will place two orders around the price_source (mid price or last traded price) in a trading_pair on
    exchange, with a distance defined by the ask_spread and bid_spread. Every order_refresh_time in seconds,
    the bot will cancel and replace the orders.
    """

    create_timestamp = 0
    price_source = PriceType.MidPrice

    @classmethod
    def init_markets(cls, config: SimplePMMConfig):
        cls.markets = {config.exchange: {config.trading_pair}}
        cls.price_source = PriceType.LastTrade if config.price_type == "last" else PriceType.MidPrice

    def __init__(self, connectors: Dict[str, ConnectorBase], config: SimplePMMConfig):
        super().__init__(connectors)
        self.config = config

    def on_tick(self):
        if self.create_timestamp <= self.current_timestamp:
            self.cancel_all_orders()
            proposal: List[OrderCandidate] = self.create_proposal()
            proposal_adjusted: List[OrderCandidate] = self.adjust_proposal_to_budget(proposal)
            self.place_orders(proposal_adjusted)
            self.create_timestamp = self.config.order_refresh_time + self.current_timestamp

    def create_proposal(self) -> List[OrderCandidate]:
        ref_price = self.connectors[self.config.exchange].get_price_by_type(self.config.trading_pair, self.price_source)
        buy_price = ref_price * Decimal(1 - self.config.bid_spread)
        sell_price = ref_price * Decimal(1 + self.config.ask_spread)

        buy_order = OrderCandidate(trading_pair=self.config.trading_pair, is_maker=True, order_type=OrderType.LIMIT,
                                   order_side=TradeType.BUY, amount=Decimal(self.config.order_amount), price=buy_price)

        sell_order = OrderCandidate(trading_pair=self.config.trading_pair, is_maker=True, order_type=OrderType.LIMIT,
                                    order_side=TradeType.SELL, amount=Decimal(self.config.order_amount), price=sell_price)

        return [buy_order, sell_order]

    def adjust_proposal_to_budget(self, proposal: List[OrderCandidate]) -> List[OrderCandidate]:
        proposal_adjusted = self.connectors[self.config.exchange].budget_checker.adjust_candidates(proposal, all_or_none=True)
        return proposal_adjusted

    def place_orders(self, proposal: List[OrderCandidate]) -> None:
        for order in proposal:
            self.place_order(connector_name=self.config.exchange, order=order)

    def place_order(self, connector_name: str, order: OrderCandidate):
        if order.order_side == TradeType.SELL:
            self.sell(connector_name=connector_name, trading_pair=order.trading_pair, amount=order.amount,
                      order_type=order.order_type, price=order.price)
        elif order.order_side == TradeType.BUY:
            self.buy(connector_name=connector_name, trading_pair=order.trading_pair, amount=order.amount,
                     order_type=order.order_type, price=order.price)

    def cancel_all_orders(self):
        for order in self.get_active_orders(connector_name=self.config.exchange):
            self.cancel(self.config.exchange, order.trading_pair, order.client_order_id)

    def did_fill_order(self, event: OrderFilledEvent):
        msg = (f"{event.trade_type.name} {round(event.amount, 2)} {event.trading_pair} {self.config.exchange} at {round(event.price, 2)}")
        self.log_with_clock(logging.INFO, msg)
        self.notify_hb_app_with_timestamp(msg)


async def main_async():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=str, required=True, help='Path to the config file')
    args = parser.parse_args()

    # Load the configuration
    with open(args.config, 'r') as config_file:
        config = yaml.safe_load(config_file)

    # Create the strategy configuration
    strategy_config = SimplePMMConfig(
        exchange=config['exchange'],
        trading_pair=config['market'],
        order_amount=Decimal(str(config['order_amount'])),
        bid_spread=Decimal(str(config['bid_spread'])) / Decimal('100'),
        ask_spread=Decimal(str(config['ask_spread'])) / Decimal('100'),
        order_refresh_time=int(config['order_refresh_time']),
        price_type=config.get('price_type', 'mid')
    )

    # Initialize the markets and create connectors
    print(f"Initializing {strategy_config.exchange} connector...")
    
    # Get connector settings
    connector_settings = AllConnectorSettings.get_connector_settings()
    exchange_setting = connector_settings[strategy_config.exchange]
    
    # Import connector module
    if exchange_setting.module_path() == "":
        # If module path is empty, it's an internal connector
        connector_module = importlib.import_module(f"hummingbot.connector.exchange.{strategy_config.exchange}.{strategy_config.exchange}_exchange")
    else:
        connector_module = importlib.import_module(exchange_setting.module_path())
    
    # Get connector class and create instance
    connector_class = getattr(connector_module, exchange_setting.class_name())
    
    # Initialize connector with empty settings (or provide API keys if needed)
    init_params = exchange_setting.conn_init_parameters(
        trading_pairs=[strategy_config.trading_pair],
        trading_required=True
    )
    
    # Zbit exchange可能不支持所有Hummingbot标准参数
    if strategy_config.exchange == "zbit":
        # 只保留Zbit支持的参数并添加API密钥
        init_params = {
            "trading_pairs": init_params.get("trading_pairs", []),
            "zbit_api_key": "vmPUZE6mv9SD5V5e14y7Ju91duEh8A",  # 使用提供的API密钥
            "zbit_api_secret": "902ae3cb34ecee2779aa4d3e1d226686"  # 使用提供的API密钥
        }
    
    # Create connector instance
    connector = connector_class(**init_params)
    
    # Create dict of connectors
    connectors = {strategy_config.exchange: connector}
    
    # Initialize and run the strategy
    strategy = SimplePMM(connectors=connectors, config=strategy_config)
    SimplePMM.init_markets(strategy_config)
    
    # Start the connector
    await connector.start_network()
    print(f"Connector {strategy_config.exchange} initialized.")

    clock = Clock(ClockMode.REALTIME)
    clock.add_iterator(strategy)
    clock.add_iterator(connector)  # Add connector to clock

    with clock:
        try:
            await clock.run()
        except KeyboardInterrupt:
            print("Stopping the bot...")
        finally:
            # Stop the connector
            await connector.stop_network()
            print(f"Connector {strategy_config.exchange} stopped.")


def main():
    ev_loop = asyncio.get_event_loop()
    try:
        ev_loop.run_until_complete(main_async())
    except KeyboardInterrupt:
        print("Stopping the bot...")
    finally:
        ev_loop.close()


if __name__ == "__main__":
    main()
