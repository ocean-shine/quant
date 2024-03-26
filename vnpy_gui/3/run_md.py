from PySide6 import QtWidgets
from PySide6 import QtCore

from vnpy.event import EventEngine, Event
from vnpy.trader.engine import MainEngine
from vnpy.trader.object import TickData, SubscribeRequest
from vnpy.trader.event import EVENT_TICK

from vnpy_tts import TtsGateway as Gateway
#  from vnpy_ctp import CtpGateway as Gateway


gateway_name: str = Gateway.default_name

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


class DataWidget(QtWidgets.QWidget):
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

        # 绑定触发
        self.button.clicked.connect(self.subscribe)

        # 网格布局
        layout = QtWidgets.QGridLayout()
        layout.addWidget(self.line, 0, 0)
        layout.addWidget(self.button, 0, 1)
        layout.addWidget(self.edit, 1, 0, 1, 2)
        self.setLayout(layout)

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
        vt_symbol: str = self.line.text()

        # 查阅合约数据
        contract: ContractData = self.main_engine.get_contract(vt_symbol)
        if not contract:
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
    Widget = DataWidget(main_engine, event_engine)
    Widget.show()

    # 连接交易接口
    main_engine.connect(setting, gateway_name)

    # 运行应用
    qapp.exec()


if __name__ == "__main__":
    run()
