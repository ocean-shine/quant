from PySide6 import QtWidgets, QtCore

from vnpy.event import EventEngine, Event
from vnpy.trader.engine import MainEngine
from vnpy.trader.object import TickData, SubscribeRequest, ContractData, OrderRequest
from vnpy.trader.event import EVENT_TICK
from vnpy.trader.utility import load_json
from vnpy.trader.constant import Exchange, Direction, Offset, OrderType

from vnpy_tts import TtsGateway as Gateway
#  from vnpy_ctp import CtpGateway as Gateway


gateway_name: str = Gateway.default_name

# setting: dict = load_json("connect_tts.json")

setting: dict = {
    #  "用户名": "222772",
    #  "密码": "Cc@18800159600",
    "用户名": "8505",
    "密码": "123456",
    "经纪商代码": "",
    #  "交易服务器": "180.168.146.187:10201",
    #  "行情服务器": "180.168.146.187:10211",
    #  "交易服务器": "180.168.146.187:10130",
    #  "行情服务器": "180.168.146.187:10131",
    #  "交易服务器": "121.37.90.193:20002",
    #  "行情服务器": "218.202.237.33:10213",
    "交易服务器": "121.37.80.177:20002",
    "行情服务器": "121.37.80.177:20004",
    "产品名称": "",
    "授权编码": "",
}


class TradingWidget(QtWidgets.QWidget):
    """交易控件"""

    def __init__(self, main_engine: MainEngine) -> None:
        """构造函数"""
        super().__init__()

        self.main_engine = main_engine
        self.init_ui()

    def init_ui(self) -> None:
        """初始化界面"""
        # 创建控件
        self.symbol_line = QtWidgets.QLineEdit()
        self.exchange_combo = QtWidgets.QComboBox()
        self.exchange_combo.addItems([
            Exchange.CFFEX.value,
            Exchange.SHFE.value,
            Exchange.DCE.value,
            Exchange.CZCE.value,
        ])
        self.direction_combo = QtWidgets.QComboBox()
        self.direction_combo.addItems([
            Direction.LONG.value,
            Direction.SHORT.value, 
        ])
        self.offset_combo = QtWidgets.QComboBox()
        self.offset_combo.addItems([
            Offset.OPEN.value,
            Offset.CLOSE.value,
            Offset.CLOSETODAY.value,
            Offset.CLOSEYESTERDAY.value, 
        ])
        self.price_line = QtWidgets.QLineEdit()
        self.volume_line = QtWidgets.QLineEdit()

        button = QtWidgets.QPushButton("下单")
        button.clicked.connect(self.send_order)

        form = QtWidgets.QFormLayout()
        form.addRow("代码", self.symbol_line)
        form.addRow("交易商", self.exchange_combo) 
        form.addRow("方向", self.direction_combo)
        form.addRow("开平", self.offset_combo)
        form.addRow("价格", self.price_line)
        form.addRow("数量", self.volume_line)
        form.addRow(button)

        self.setLayout(form)

    def send_order(self) -> None:
        """发送委托"""
        symbol = self.symbol_line.text()
        exchange = Exchange(self.exchange_combo.currentText())
        direction = Direction(self.direction_combo.currentText())
        offset = Offset(self.offset_combo.currentText())
        price = float(self.price_line.text())
        volume = int(self.volume_line.text())
        order_type = OrderType.LIMIT

        # 确认合约存在
        vt_symbol = f"{symbol}.{exchange.value}"
        contract_new = self.main_engine.get_contract(vt_symbol)
        if not contract_new:
            return
        
        # 发送委托请求
        req = OrderRequest(
            symbol=symbol,
            exchange=exchange,
            direction=direction,
            type=order_type,
            volume=volume,
            price=price,
            offset=offset, 
        )
        self.main_engine.send_order(req, contract_new.gateway_name)
        

class MainWidget(QtWidgets.QWidget):
    """市场行情组件"""

    # 在类中直接定义signal成员变量，而非__init__构造函数中
    signal = QtCore.Signal(Event)

    def __init__(self, main_engine: MainEngine, event_engine: EventEngine) -> None:
        """构造函数"""
        super().__init__()

        self.main_engine = main_engine
        self.event_engine = event_engine
        self.ticks = {}

        self.init_ui()
        self.register_event()

    def init_ui(self) -> None:
        """初始化界面"""
        # 创建控件
        self.edit = QtWidgets.QTextEdit()
        self.line = QtWidgets.QLineEdit()
        self.button = QtWidgets.QPushButton("订阅")

        # 标签控件
        label = QtWidgets.QLabel()
        label.setText("市场行情监控")  # 文本
        label.setAlignment(QtCore.Qt.AlignCenter) # 对齐

        # 下拉框控件
        self.combo = QtWidgets.QComboBox()

        exchanges = [
            Exchange.CFFEX.value,
            Exchange.SHFE.value,
            Exchange.DCE.value,
            Exchange.CZCE.value,
        ]
        self.combo.addItems(exchanges)

        # ix: int = self.combo.findText("DCE")
        # self.combo.setCurrentIndex(ix)

        # 绑定触发
        self.button.clicked.connect(self.subscribe)

        # 交易控件
        self.trading_widget = TradingWidget(self.main_engine)

        # 网格布局
        grid = QtWidgets.QGridLayout()
        grid.addWidget(label, 0, 0, 1, 2)
        grid.addWidget(self.line, 1, 0)
        grid.addWidget(self.combo, 1, 1)
        grid.addWidget(self.button, 1, 2)
        grid.addWidget(self.edit, 2, 0, 1, 3)
        
        # 垂直布局
        vbox = QtWidgets.QVBoxLayout()
        vbox.addLayout(grid)
        vbox.addWidget(self.trading_widget)

        self.setLayout(vbox)

    def register_event(self) -> None:
        """注册事件监听"""
        # 绑定信号
        self.signal.connect(self.process_tick_event)

        # 注册监听
        self.event_engine.register(EVENT_TICK, self.signal.emit)

    def process_tick_event(self, event: Event) -> None:
        """处理行情数据"""
        tick: TickData = event.data
        self.ticks[tick.vt_symbol] = tick

        # 拼接字符串
        text: str = ""

        for t in self.ticks.values():
            text += f"{t.vt_symbol}\tbid:{t.bid_price_1}\task:{t.ask_price_1}\n"

        # GUI 输出信息
        self.edit.setText(text)

    # 定义行情订阅函数
    def subscribe(self) -> None:
        """订阅合约行情"""
        # 获取本地代码
        symbol: str = self.line.text()
        exchange_str = self.combo.currentText()
        vt_symbol: str = f"{symbol}.{exchange_str}"

        # 查阅合约数据
        contract: ContractData = self.main_engine.get_contract(vt_symbol)
        if not contract:
            self.edit.append(f"找不到合约{vt_symbol}")
            return
        
        req = SubscribeRequest(contract.symbol, contract.exchange)
        self.main_engine.subscribe(req, contract.gateway_name)
      

def run() -> None:
    """主程序入口"""
    #  QT应用（事件循环）
    qapp = QtWidgets.QApplication([])
    
    # 创建主引擎
    event_engine: EventEngine = EventEngine()
    main_engine: MainEngine = MainEngine(event_engine)
    main_engine.add_gateway(Gateway)
   
    # 创建控件
    Widget = MainWidget(main_engine, event_engine)
    Widget.show()

    # 连接交易接口
    main_engine.connect(setting, gateway_name)

    # 运行应用
    qapp.exec()


if __name__ == "__main__":
    run()
