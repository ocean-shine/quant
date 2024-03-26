import pyqtgraph as pg 
from PySide6 import QtCore, QtWidgets

from vnpy.event import Event, EventEngine
from vnpy.trader.event import (
    EVENT_TICK,
)
from vnpy.trader.object import TickData


class TickChartWidget(QtWidgets.QTabWidget):
    """"""
    
    signal = QtCore.Signal(Event)
    
    def __init__(self, event_engine: EventEngine) -> None:
        """"""
        super().__init__()
        
        self.event_engine: EventEngine = event_engine
        
        self.curve: dict[str, pg.PlotDataItem] = {}
        self.symbol_data: dict[str, list] = {}
        
        self.register_event()
        
    def register_event(self) -> None:
        """"""
        self.signal.connect(self.process_tick_event)
        self.event_engine.register(EVENT_TICK, self.signal.emit)
        
    def process_tick_event(self, event: Event) -> None:
        """"""
        tick: TickData = event.data
        #
        data: list = self.symbol_data.setdefault(tick.vt_symbol, [])
        
        #
        data.append(tick.last_price)
        
        #
        if len(data) > 500:
            data.pop(0)
        #
        curve: pg.PlotDataItem = self.get_curve(tick.vt_symbol)
        curve.setData(data)
        
    def get_curve(self, vt_symbol: str) -> pg.PlotDataItem:
        """"""
        
        if vt_symbol in self.curve:
            return self.curve[vt_symbol]
        
        plot: pg.PlotWidget = pg.PlotWidget()
        self.addTab(plot, vt_symbol)
        
        curve: pg.PlotDataItem = pg.PlotDataItem()
        plot.addItem(curve)
        
        self.curve[vt_symbol] = curve
        return curve
        
       
        
        
        