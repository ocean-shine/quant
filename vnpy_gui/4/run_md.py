from pathlib import Path
from PySide6 import QtWidgets, QtCore, QtGui

from vnpy.event import EventEngine, Event
from vnpy.trader.engine import MainEngine
from vnpy.trader.object import TickData, SubscribeRequest, ContractData
from vnpy.trader.event import EVENT_TICK
from vnpy.trader.utility import load_json

from vnpy_tts import TtsGateway as Gateway
#  from vnpy_ctp import CtpGateway as Gateway


gateway_name: str = Gateway.default_name

setting: dict = load_json("connect_ctp.json")

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

        # 标签控件
        label = QtWidgets.QLabel()

        # label.setText("市场行情监控"*20)  # 文本
        # label.setNum(123) # 数字

        # png_path = Path(__file__).parent.joinpath("capital.png") # 图片
        # pixmap = QtGui.QPixmap(str(png_path))
        # label.setPixmap(pixmap.scaled(100,100))

        # label.setAlignment(QtCore.Qt.AlignCenter) # 对齐
        # label.setAlignment(QtCore.Qt.AlignRight)
        # label.setAlignment(QtCore.Qt.AlignLeft)

        # label.setWordWrap(True)  # 长文本环行

        # html = "<b>行情监控</b>"                       #加粗
        # html = '<a style="color:red;">市场监控</a>'   #红色
        html = '<a href="https://www.bing.com">必应首页</a>'  #链接
        label.setText(html)
        label.setOpenExternalLinks(True)

        # 绑定触发
        self.button.clicked.connect(self.subscribe)

        # 网格布局
        layout = QtWidgets.QGridLayout()
        layout.addWidget(label, 0, 0, 1, 2)
        layout.addWidget(self.line, 1, 0)
        layout.addWidget(self.button, 1, 1)
        layout.addWidget(self.edit, 2, 0, 1, 2)
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
