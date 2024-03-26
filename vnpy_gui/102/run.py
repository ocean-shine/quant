from vnpy_ctp.api import MdApi
# from vnpy_tts.api import MdApi
from PySide6 import QtWidgets, QtCore
from vnpy.event import Event, EventEngine


class SimpleWidget(QtWidgets.QWidget):
    """"""

    signal = QtCore.Signal(str)
    
    def __init__(self, event_engine: EventEngine) -> None: 
        """"""
        super().__init__()
        
        self.api = None
        #
        self.event_engine: EventEngine = event_engine
        self.event_engine.register("log", self.update_log)
        
        #
        self.log_monitor = QtWidgets.QTextEdit()
        self.log_monitor.setReadOnly(True)
        
        self.subscribe_button = QtWidgets.QPushButton("订阅")
        self.symbol_line = QtWidgets.QLineEdit()
        
        #
        self.subscribe_button.clicked.connect(self.subscribe_symbol)
        self.signal.connect(self.log_monitor.append)
        
        #
        vbox = QtWidgets.QVBoxLayout()
        vbox.addWidget(self.log_monitor)
        vbox.addWidget(self.symbol_line)
        vbox.addWidget(self.subscribe_button)
        
        self.setLayout(vbox)
        
    def subscribe_symbol(self):
        """"""
        symbol = self.symbol_line.text()
        self.api.subscribeMarketData(symbol)
        
    def update_log(self, event: Event) -> None:
        """"""
        msg: str = event.data
        self.signal.emit(msg)
        
        
class CtpMdApi(MdApi):
    """实现行情API"""
    
    def __init__(self, event_engine: EventEngine) -> None:
        """"""
        super().__init__()
        self.event_engine: EventEngine = event_engine
        
    def onFrontConnected(self):
        """服务器连接成功回报"""
        self.write_log("行情服务器连接成功")
        
        #
        ctp_req: dict = {
            "UserID": "222772",
            "Password": "Cc@18800159600",
            "BrokerID": "9999",
        }
        self.reqUserLogin(ctp_req, 1)
        
    def onFrontDisconnected(self, reason):
        """服务器连接断开回报"""
        self.write_log("行情服务器断开成功", reason)
        
    def onRspUserLogin(self, data, error, reqid, last):
        """用户登陆请求回报"""
        if not error["ErrorID"]:
            self.write_log("行情服务器登陆成功")
        else:
            self.write_log("行情服务器登陆失败", error)
            
    def onRtnDepthMarketData(self, data):
        """返回行情市场数据"""
        self.write_log(str(data))
        
    def write_log(self, msg: str) -> None:
        """"""
        event: Event = Event("log", msg)
        self.event_engine.put(event)
        
    
def main():
    
    event_engine: EventEngine = EventEngine()
    event_engine.start()
    
    #
    app: QtWidgets.QApplication = QtWidgets.QApplication()
    
    #
    widget: SimpleWidget = SimpleWidget(event_engine)
    widget.show()
    
    api = CtpMdApi(event_engine)
    
    widget.api = api
    
    api.createFtdcMdApi(".")
    api.registerFront("tcp://180.168.146.187:10131")
    api.init()
    
    app.exec()
    
if __name__ == "__main__":
    main()