from vnpy_ctp.api import MdApi
from vnpy_ctp import CtpGateway
# from vnpy_tts.api import MdApi
from PySide6 import QtWidgets, QtCore
from vnpy.event import Event, EventEngine
from threading import Thread 
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.common import TickAttrib, TickerId
from ibapi.ticktype import TickType 
from ibapi.contract import Contract 



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
        symbol, exchange_str = vt_symbol.split(".")

        req = SubscribeRequest(
            symbol = symbol,
            exchange = Exchange(exchange_str)
        )
        self.gateway.subscribe(req)
        
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



class IbApi(EWrapper):
    """IB的API接口"""


    def __init__(self, event_engine: EventEngine) -> None:
        """构造函数"""
        super().__init__()

        self.event_engine: EventEngine = event_engine
    

        self.reqid: int = 0
        self.client: EClient = EClient(self)
        self.close = self.client.disconnect

    def connectAck(self) -> None:
        """连接成功回报"""
        self.write_log("IB TWS连接成功")

    def connectionClosed(self) -> None:
        """连接断开回报"""
        self.write_log("IB TWS连接断开")

    def tickPrice(self, reqId: TickerId, tickType: TickType, price: float, attrib: TickAttrib) -> None:
        """tick价格更新回报"""
        super().tickPrice(reqId, tickType, price, attrib)
        self.write_log(f"tickPrice函数收到未订阅的推送，reqId：{reqId}")

    def tickSize(self, reqId: TickerId, tickType: TickType, size: int) -> None:
        """tick数量更新回报"""
        super().tickSize(reqId, tickType, size)
        self.write_log(f"tickSize函数收到未订阅的推送，reqId：{reqId}")

    def tickString(self, reqId: TickerId, tickType: TickType, value: str) -> None:
        """tick字符串更新回报"""
        super().tickString(reqId, tickType, value)
        self.write_log(f"tickString函数收到未订阅的推送，reqId：{reqId}")

    def connect(
        self,
        host: str,
        port: int,
        clientid: int
    ) -> None:
        """连接TWS"""
        self.host = host
        self.port = port
        self.clientid = clientid

        self.client.connect(host, port, clientid)
        self.thread = Thread(target=self.client.run)
        self.thread.start()

    def subscribe(self, symbol: str) -> None:
        """订阅tick数据更新"""
        ib_contract: Contract = Contract()
        ib_contract.exchange = "SMART"
        ib_contract.secType = "CMDTY"
        ib_contract.currency = "USD"
        ib_contract.symbol = symbol
        self.reqid += 1
        self.client.reqMktData(self.reqid, ib_contract, "", False, False, [])

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
    
    # CPT APi
    ctp_setting = {
        "用户名": "222772",
        "密码": "Cc@18800159600",
        # "用户名": "8505",
        # "密码": "123456",
        "经纪商代码": "9999",
        "交易服务器": "180.168.146.187:10130",
        "行情服务器": "180.168.146.187:10131",
        "产品名称": "simnow_client_test",
        "授权编码": "0000000000000000",
    }

    ctp_gateway = CtpGateway(event_engine, "CTP")
    ctp_gateway.connect(ctp_setting)
    widget.gateway = gateway = ctp_gateway

    # ctp_api = CtpMdApi(event_engine)
    # ctp_api.createFtdcMdApi(".")
    # ctp_api.registerFront("tcp://180.168.146.187:10131")
    # ctp_api.init()
    # widget.api = ctp_api
    
    # # IB API 
    # ib_api : IbApi = IbApi(event_engine)
    # ib_api.connect("localhost", 7497, 1)
    # widget.api = ib_api

    app.exec()
    
if __name__ == "__main__":
    main()