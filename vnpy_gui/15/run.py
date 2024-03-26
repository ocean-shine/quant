from PySide6 import QtWidgets, QtCore, QtGui

from vnpy.event import EventEngine, Event
from vnpy.trader.engine import MainEngine
from vnpy.trader.object import (
    TickData, 
    SubscribeRequest, 
    ContractData, 
    OrderRequest
)
from vnpy.trader.event import EVENT_TICK
from vnpy.trader.utility import load_json, save_json
from vnpy.trader.constant import Exchange, Direction, Offset, OrderType

from vnpy_tts import TtsGateway as Gateway
#  from vnpy_ctp import CtpGateway as Gateway


gateway_name: str = Gateway.default_name


class LoginWidget(QtWidgets.QWidget):
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
        self.main_engine.connect(setting, gateway_name)

        if self.save_check.isChecked():
            save_json("tts_connect_data.json", setting)
        
        self.close()

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


class TickCell(QtWidgets.QTableWidgetItem):
    """Tick盘口监表单元格"""
    
    def __init__(self, text: str = "") -> None:
        """构造函数"""
        super().__init__(text)
        
        # 设置字体
        font = QtGui.QFont("微软雅黑", 14)
        
        self.setFont(font)
        
        # 设置对齐
        self.setTextAlignment(QtCore.Qt.AlignCenter)
        
        # 设置背景色
        self.setBackground(QtGui.QColor("yellow"))
        
        # 设置颜色
        if "多" in text:
            self.setForeground(QtGui.QColor("red"))
        elif "空" in text:
            self.setForeground(QtGui.QColor("green"))
        
        
class TickMonitor(QtWidgets.QTableWidget):
    """Tick盘口监控控件"""
    
    signal = QtCore.Signal(Event)
    
    def __init__(self, event_engine: EventEngine) -> None:
        """构造函数"""
        super().__init__()
        
        self.event_engine = event_engine
        
        self.ticks = {}
        
        self.init_ui()
        self.register_event()
            
    def init_ui(self) -> None:
        """初始化界面"""
        # 表头列表
        labels = ["代码", "最新价", "信息"]
        
        # 设置列数
        self.setColumnCount(len(labels))
        
        # 设置水平表头
        self.setHorizontalHeaderLabels(labels)
        self.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        
        # 关闭垂直表头
        self.verticalHeader().setVisible(False)
        
        # 禁用表头编辑
        self.setEditTriggers(self.NoEditTriggers)
        
    def register_event(self) -> None:
        """注册事件监听"""
        self.signal.connect(self.process_tick_event)
        self.event_engine.register(EVENT_TICK, self.signal.emit)
        
    def process_tick_event(self, event: Event   ) -> None:
        """处理Tick事件"""
        tick: TickData = event.data
        last_tick: TickData = self.ticks.get(tick.vt_symbol, None)
        self.ticks[tick.vt_symbol] = tick
        
        # 必须至少有一条缓存才能计算
        if not last_tick:
            return
                
        # 计算持仓变化
        oi_change: int = last_tick.open_interest - tick.open_interest
        if oi_change > 0:
            oi_str = "开"
        elif oi_change < 0:
            oi_str = "平"
        else:
            oi_str = "换"
            
        # 计算变化方向
        if tick.last_price >= last_tick.ask_price_1:
            direction_str = "多"
        elif tick.last_price <= last_tick.bid_price_1:
            direction_str = "空"
        else:
            direction_str = "双"
        
        # 获取当前行数
        row = self.rowCount()
        
        # 在尾部插入行（索引从0开始）
        self.insertRow(row)
        
        #
        symbol_cell = TickCell(tick.vt_symbol)
        price_cell = TickCell(str(tick.last_price))
        info_cell = TickCell(f"{direction_str}{oi_str}")
        
        # 设置单元格
        self.setItem(row, 0, symbol_cell)
        self.setItem(row, 1, price_cell)
        self.setItem(row, 2, info_cell)
        
        # 滚动到底部
        self.scrollToBottom()
        
        
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
        self.login_button = QtWidgets.QPushButton("登陆")
        self.login_button.clicked.connect(self.show_login_widget)

        self.edit = QtWidgets.QTextEdit()
        self.line = QtWidgets.QLineEdit()
        self.button = QtWidgets.QPushButton("订阅")
        
        
        # 标签控件
        label = QtWidgets.QLabel()
        label.setText("市场行情监控")  # 文本
        label.setAlignment(QtCore.Qt.AlignCenter)  # 对齐

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
        self.flash_widget = FlashWidget(self.main_engine, self.event_engine)
        self.tick_monitor = TickMonitor(self.event_engine)
        
        # 网格布局
        grid = QtWidgets.QGridLayout()
        grid.addWidget(label, 0, 0, 1, 2)
        grid.addWidget(self.login_button, 1, 0)
        grid.addWidget(self.line, 2, 0)
        grid.addWidget(self.combo, 2, 1)
        grid.addWidget(self.button, 2, 2)
        grid.addWidget(self.edit, 3, 0, 1, 3)
        
        # 垂直布局
        vbox = QtWidgets.QVBoxLayout()
        vbox.addLayout(grid)
        vbox.addWidget(self.trading_widget)
        vbox.addWidget(self.flash_widget)
        
        # 水平布局
        hbox = QtWidgets.QHBoxLayout()
        hbox.addLayout(vbox)
        hbox.addWidget(self.tick_monitor)

        self.setLayout(hbox)

    def register_event(self) -> None:
        """注册事件监听"""
        # 绑定信号
        self.signal.connect(self.process_tick_event)

        # 注册监听
        self.event_engine.register(EVENT_TICK, self.signal.emit)

    def process_tick_event(self, event: Event) -> None:
        """处理行情数据"""
        tick: TickData = event.data
        last_tick: TickData = self.ticks.get(tick.vt_symbol, None)
        self.ticks[tick.vt_symbol] = tick

        # 必须至少有一条缓存才能计算
        if not last_tick:
            return
        
        # 计算持仓变化
        oi_change: int = tick.open_interest - last_tick.open_interest

        if oi_change > 0:
            oi_str = "开"
        elif oi_change < 0:
            oi_str = "平"
        else:
            oi_str = "换"

        # 计算方向变化
        if tick.last_price >= last_tick.ask_price_1:
            direction_str = "多"
        elif tick.last_price <= last_tick.bid_price_1:
            direction_str = "空"
        else:
            direction_str = "双"

        text = f"{tick.vt_symbol} {tick.last_price} {direction_str} {oi_str}"
        self.edit.append(text) 

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
    
    def show_login_widget(self) -> None:
        """显示连接登陆控件"""
        # 如果没有则创建
        if not hasattr(self, "login_widget"):
            self.login_widget = LoginWidget(self.main_engine)

        # 显示控件
        self.login_widget.show()


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

    # 运行应用
    qapp.exec()


if __name__ == "__main__":
    run()
