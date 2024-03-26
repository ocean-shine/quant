from PySide6 import QtCore, QtGui, QtWidgets

from vnpy.event.engine import EventEngine, Event
from vnpy.trader.engine import MainEngine
from vnpy.trader.object import (
    TickData, 
    SubscribeRequest, 
    ContractData, 
    OrderRequest,
    OrderData
)
from vnpy.trader.event import (
    EVENT_TICK,
    EVENT_LOG,
    EVENT_ORDER,
    EVENT_TRADE,
    EVENT_POSITION,
    EVENT_ACCOUNT
)
from vnpy.trader.utility import save_json, load_json
from vnpy.trader.constant import Exchange, Offset, Direction, OrderType

class LoginDialog(QtWidgets.QDialog): 
    """接口登陆控件"""

    def __init__(self, main_engine: MainEngine) -> None:
        """构造函数"""

        super().__init__()

        self.main_engine: MainEngine = main_engine

        self.init_ui()
        self.load_setting()

    def init_ui(self) -> None:
        """初始化界面"""
        self.setWindowTitle("连接登陆")

        self.username_line = QtWidgets.QLineEdit()
        self.password_line = QtWidgets.QLineEdit()
        self.password_line.setEchoMode(self.password_line.EchoMode.Password)

        self.broker_line = QtWidgets.QLineEdit()
        self.td_address_line = QtWidgets.QLineEdit()
        self.md_saddress_line = QtWidgets.QLineEdit()
        self.appid_line = QtWidgets.QLineEdit()
        self.auth_code_line = QtWidgets.QLineEdit()

        self.save_check = QtWidgets.QCheckBox("保存")

        button = QtWidgets.QPushButton("登陆")
        button.clicked.connect(self.login)

        form = QtWidgets.QFormLayout()
        form.addRow("用户名", self.username_line)
        form.addRow("密码", self.password_line)
        form.addRow("经纪商代码", self.broker_line)
        form.addRow("交易服务器", self.td_address_line)
        form.addRow("行情服务器", self.md_saddress_line)
        form.addRow("产品名称", self.appid_line)
        form.addRow("授权编码", self.auth_code_line)
        form.addRow(self.save_check)
        form.addRow(button)  

        self.setLayout(form)

    def login(self) -> None:
        """连接登陆"""
        setting = {
            "用户名": self.username_line.text(),
            "密码": self.password_line.text(),
            "经纪商代码": self.broker_line.text(),
            "交易服务器": self.td_address_line.text(),
            "行情服务器": self.md_saddress_line.text(),
            "产品名称": self.appid_line.text(),
            "授权编码": self.auth_code_line.text(),
        }
        
        #
        gateway_name: list[str] = self.main_engine.get_all_gateway_names()
        gateway_name: str = gateway_name[0]
        self.main_engine.connect(setting, gateway_name)

        if self.save_check.isChecked():
            save_json("tts_connect_data.json", setting)
        
        # 用accept表示对话执行完毕
        self.accept()

    def load_setting(self) -> None:
        """加载配置"""
        setting = load_json("tts_connect_data.json")

        if setting:
            self.username_line.setText(setting["用户名"])    
            self.password_line.setText(setting["密码"])      
            self.broker_line.setText(setting["经纪商代码"])
            self.td_address_line.setText(setting["交易服务器"])
            self.md_saddress_line.setText(setting["行情服务器"])
            self.appid_line.setText(setting["产品名称"])  
            self.auth_code_line.setText(setting["授权编码"])  

            self.save_check.setChecked(True)


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
        self.symbol_line.returnPressed.connect(self.update_symbol)
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
        self.price_spin = QtWidgets.QDoubleSpinBox()
        self.price_spin.setDecimals(3)
        self.price_spin.setMinimum(1)
        self.price_spin.setMaximum(1_000_000)

        self.volume_spin = QtWidgets.QSpinBox()
        self.volume_spin.setSuffix("手")
        self.volume_spin.setRange(1, 1000)

        button = QtWidgets.QPushButton("下单")
        button.clicked.connect(self.send_order)

        form = QtWidgets.QFormLayout()
        form.addRow("代码", self.symbol_line)
        form.addRow("交易商", self.exchange_combo) 
        form.addRow("方向", self.direction_combo)
        form.addRow("开平", self.offset_combo)
        form.addRow("价格", self.price_spin)
        form.addRow("数量", self.volume_spin)
        form.addRow(button)

        self.setLayout(form)

    def send_order(self) -> None:
        """发送委托"""
        symbol = self.symbol_line.text()
        exchange = Exchange(self.exchange_combo.currentText())
        direction = Direction(self.direction_combo.currentText())
        offset = Offset(self.offset_combo.currentText())
        price = self.price_spin.value()
        volume = self.volume_spin.value()
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

    def update_symbol(self) -> None:
        """更新交易代码"""
        symbol = self.symbol_line.text()
        exchange_str = self.exchange_combo.currentText()
        vt_symbol = f"{symbol}.{exchange_str}"

        contract = self.main_engine.get_contract(vt_symbol)
        if contract:
            self.price_spin.setSingleStep(contract.pricetick)
            self.volume_spin.setSingleStep(contract.min_volume) 


class FlashWidget(QtWidgets.QWidget):
    """闪电交易组件"""

    signal = QtCore.Signal(Event)

    def __init__(self, main_engine: MainEngine, event_engine: EventEngine) -> None:
        """构造函数"""
        super().__init__()

        self.main_engine = main_engine
        self.event_engine = event_engine

        self.vt_symbol = ""

        self.init_ui()
        self.init_shortcut()
        self.register_event()

    def init_ui(self) -> None:
        """初始化界面"""
        self.symbol_line = QtWidgets.QLineEdit()
        self.symbol_line.setPlaceholderText("输入闪电交易码， 如ag2403.SHFE")
        self.symbol_line.returnPressed.connect(self.update_symbol)

        self.volume_spin = QtWidgets.QSpinBox()
        self.volume_spin.setPrefix("数量")
        self.volume_spin.setSuffix("手")
        self.volume_spin.setRange(0, 100)

        self.add_spin = QtWidgets.QSpinBox()
        self.add_spin.setPrefix("超价")
        self.add_spin.setSuffix("跳")
        self.add_spin.setRange(1, 100)

        self.offset_combo = QtWidgets.QComboBox()
        self.offset_combo.addItems([o.value for o in Offset if o.value])

        height = 100
        self.bid_button = QtWidgets.QPushButton()
        self.bid_button.setFixedHeight(height)
        self.bid_button.clicked.connect(self.sell)

        self.ask_button = QtWidgets.QPushButton()
        self.ask_button.setFixedHeight(height)
        self.ask_button.clicked.connect(self.buy)

        grid = QtWidgets.QGridLayout()
        grid.addWidget(self.symbol_line, 0, 0, 1, 2)
        grid.addWidget(self.offset_combo, 1, 0, 1, 2)
        grid.addWidget(self.volume_spin, 2, 0)
        grid.addWidget(self.add_spin, 2, 1)
        grid.addWidget(self.bid_button, 3, 0)
        grid.addWidget(self.ask_button, 3, 1)

        self.setLayout(grid)

    def init_shortcut(self) -> None:
        """初始化快捷键"""
        self.buy_shortcut = QtGui.QShortcut(
            QtGui.QKeySequence("Ctrl+B"),
            self
        )
        self.buy_shortcut.activated.connect(self.buy)

        self.sell_shortcut = QtGui.QShortcut(
            QtGui.QKeySequence("Ctrl+S"),
            self
        )
        self.sell_shortcut.activated.connect(self.sell)

    def register_event(self) -> None:
        """注册事件监听"""
        self.signal.connect(self.process_tick_event)
        self.event_engine.register(EVENT_TICK, self.signal.emit)

    def update_symbol(self) -> None:
        """更新当前交易代码"""
        # 获取代码
        vt_symbol = self.symbol_line.text()

        # 查询合约
        contract = self.main_engine.get_contract(vt_symbol)
        if not contract:
            return
    
        # 订阅行情
        req = SubscribeRequest(contract.symbol, contract.exchange)
        self.main_engine.subscribe(req, contract.gateway_name)

        # 绑定代码
        self.vt_symbol = vt_symbol

    def process_tick_event(self, event: Event) -> None:
        """处理行情事件"""
        tick: TickData = event.data
        if tick.vt_symbol != self.vt_symbol:
            return
        
        self.bid_button.setText(f"{tick.bid_price_1}\n\n{tick.bid_volume_1}")
        self.ask_button.setText(f"{tick.ask_price_1}\n\n{tick.ask_volume_1}")

    def buy(self) -> None:
        """买入"""
        # 查询最新行情
        tick: TickData = self.main_engine.get_tick(self.vt_symbol)
        if not tick:
            return
        
        # 计算委托价格
        contract: ContractData = self.main_engine.get_contract(self.vt_symbol)
        price = tick.ask_price_1 + contract.pricetick * self.add_spin.value()
        # 发出交易委托
        req = OrderRequest(
            symbol=tick.symbol,
            exchange=tick.exchange,
            direction=Direction.LONG,
            type=OrderType.LIMIT,
            offset=Offset(self.offset_combo.currentText()),
            volume=self.volume_spin.value(),
            price=price,
        )
        self.main_engine.send_order(req, tick.gateway_name)

    def sell(self) -> None:
        """卖出"""
        # 查询最新行情
        tick: TickData = self.main_engine.get_tick(self.vt_symbol)
        if not tick:
            return
        
        # 计算委托价格
        contract: ContractData = self.main_engine.get_contract(self.vt_symbol)
        price = tick.bid_price_1 - contract.pricetick * self.add_spin.value()
        # 发出交易委托
        req = OrderRequest(
            symbol=tick.symbol,
            exchange=tick.exchange,
            direction=Direction.SHORT,
            type=OrderType.LIMIT,
            offset=Offset(self.offset_combo.currentText()),
            volume=self.volume_spin.value(),
            price=price,
        )
        self.main_engine.send_order(req, tick.gateway_name)

