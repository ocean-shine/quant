from PySide6 import QtCore, QtGui, QtWidgets

from vnpy.event.engine import Event, EventEngine
from vnpy.trader.engine import MainEngine
from vnpy.trader.object import (
    SubscribeRequest, 
    ContractData, 
    TickData
)
from vnpy.trader.event import (
    EVENT_LOG,
)

from vnpy.trader.constant import Exchange
from vnpy_chartwizard.ui import ChartWizardWidget

from monitor import (
    TickMonitor,
    MarketMonitor,
    OrderMonitor,
    TradeMonitor,
    PositionMonitor,
    AccountMonitor,
    LogMonitor,
)
from widget import TradingWidget, FlashWidget, LoginDialog
from chart import TickChartWidget

         
class MainWindow(QtWidgets.QMainWindow):
    """市场行情组件"""

    # 在类中直接定义signal成员变量，而非__init__构造函数中
    signal_log = QtCore.Signal(Event)

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
        # 设置窗口标题
        self.setWindowTitle("量化交易平台")
         
        # 顶部菜单栏
        menubar = self.menuBar()
        sys_menu = menubar.addMenu("系统")
        sys_menu.addAction("登陆", self.show_login_dialog)
        sys_menu.addAction("测试", self.run_test)
                           
        # 底部状态栏
        self.statusBar().showMessage("程序启动")
        
        # 创建控件
        self.edit = QtWidgets.QTextEdit()
        self.line = QtWidgets.QLineEdit()
        self.button = QtWidgets.QPushButton("订阅")
        
        self.button.setStyleSheet("background-color:orange")
        self.tick_monitor = TickMonitor(self.event_engine)
        
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

        # 绑定触发
        self.button.clicked.connect(self.subscribe)

        # 交易控件
        self.trading_widget = TradingWidget(self.main_engine)
        self.flash_widget = FlashWidget(self.main_engine, self.event_engine)
        
        #监控表格
        self.order_moniter = OrderMonitor(self.main_engine, self.event_engine)
        self.trade_moniter = TradeMonitor(self.event_engine)
        self.position_moniter = PositionMonitor(self.event_engine)
        self.account_moniter = AccountMonitor(self.event_engine)
        self.market_moniter = MarketMonitor(self.event_engine)
        self.log_moniter = LogMonitor(self.event_engine)
        # self.tick_chart = TickChartWidget(self.event_engine)
        
        # 监控K线图
        self.candle_chart = ChartWizardWidget(self.main_engine, self.event_engine)
        self.candle_chart.setMinimumHeight(400)
        
        # 网格布局
        grid = QtWidgets.QGridLayout()
        grid.addWidget(label, 0, 0, 1, 2)
        grid.addWidget(self.line, 2, 0)
        grid.addWidget(self.combo, 2, 1)
        grid.addWidget(self.button, 2, 2)
        grid.addWidget(self.edit, 3, 0, 1, 3)
        
        # 垂直布局
        vbox = QtWidgets.QVBoxLayout()
        vbox.addLayout(grid)
        vbox.addWidget(self.trading_widget)
        vbox.addWidget(self.flash_widget)
        
        # 垂直布局2
        tab1 = QtWidgets.QTabWidget()
        tab1.addTab(self.market_moniter, "行情")
        
        tab2 = QtWidgets.QTabWidget()
        tab2.addTab(self.order_moniter, "委托")
        tab2.addTab(self.trade_moniter, "成交")
        tab2.addTab(self.position_moniter, "持仓")
        
        tab3 = QtWidgets.QTabWidget()
        tab3.addTab(self.account_moniter, "资金")
        tab3.setMaximumHeight(100)
        
        tab4 = QtWidgets.QTabWidget()
        tab4.addTab(self.log_moniter, "日志")
        
        vbox2 = QtWidgets.QVBoxLayout()
        vbox2.addWidget(self.candle_chart)
        vbox2.addWidget(tab1)
        vbox2.addWidget(tab2)
        vbox2.addWidget(tab3)
        vbox2.addWidget(tab4)
        
        # 水平布局
        hbox = QtWidgets.QHBoxLayout()
        hbox.addLayout(vbox)
        hbox.addLayout(vbox2)
        hbox.addWidget(self.tick_monitor)

        widget = QtWidgets.QWidget()
        widget.setLayout(hbox)
        self.setCentralWidget(widget)

    def register_event(self) -> None:
        """注册事件监听"""
        
        self.signal_log.connect(self.process_log_event)
        self.event_engine.register(EVENT_LOG, self.signal_log.emit)

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
    
    def show_login_dialog(self) -> None:
        """显示连接登陆控件"""
        # 如果没有则创建
        login_dialog = LoginDialog(self.main_engine)
        n = login_dialog.exec()

        # 检查执行返回值
        if n == login_dialog.Accepted:
            print("发起登陆操作")
        
    def process_log_event(self, event: Event) -> None:
        """处理日志事件"""
        log = event.data
        self.statusBar().showMessage(log.msg)

    def run_test(self) -> None:
        """运行功能测试"""
        # 尝试question/informatiom/waring/critical
        n = QtWidgets.QMessageBox.information(
            self,
            "信息提示框测试",
            "我们正在运行测试！",
            QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Close,
            QtWidgets.QMessageBox.Ok
        )
        print("信息提示框运行结果", n)
        
    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        """运行功能测试"""
        # 弹出信息框
        n = QtWidgets.QMessageBox.question(
            self,
            "关闭确认",
            "是否确认关闭交易系统?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )
        
        # 判断选择结果
        if n != QtWidgets.QMessageBox.Yes:
            event.ignore()
            return
        
        # 关闭核心引擎
        self.main_engine.close()
        
        #接受关闭事件
        event.accept()
    