import ctypes
from pathlib import Path

from PySide6 import QtWidgets, QtGui
import qdarkstyle

from vnpy.event.engine import EventEngine
from vnpy.trader.engine import MainEngine
from vnpy.trader.setting import SETTINGS

from mainwindow import MainWindow
# from vnpy_tts import TtsGateway as Gateway
from vnpy_ctp import CtpGateway as Gateway
from vnpy_chartwizard import ChartWizardApp


gateway_name: str = Gateway.default_name

# # 配置RQDATA数据服务
# SETTINGS["datafeed.name"] = "rqdata"
# SETTINGS["datafedd.username"] = "license"

# 配置TuShare数据服务
SETTINGS["datafeed.name"] = "tushare"
SETTINGS["datafedd.username"] = "token"


def run() -> None:
    """主程序入口"""
    #  QT应用（事件循环）
    qapp = QtWidgets.QApplication([])
    
    # 设置全局默认字体
    font = QtGui.QFont("微软雅黑", 12)
    qapp.setFont(font)
    
    # 应用黑色皮肤
    qapp.setStyleSheet(qdarkstyle.load_stylesheet())
    
    # 获取ico文件路径
    icon_path = Path(__file__).parent.joinpath("logo.ico")
    
    # 设置应用图标
    icon = QtGui.QIcon(str(icon_path))
    qapp.setWindowIcon(icon)
    
    # 设置进程ID
    #ctypes.cdll.shell32.SetCurrentProcessExplicitAppUserModelID("gui demo")
    # qte.QtWin.setCurrentProcessExplicitAppUserModelID("gui demo")
    # 创建主引擎
    event_engine: EventEngine = EventEngine()
    main_engine: MainEngine = MainEngine(event_engine)
    
    # 添加交易接口
    main_engine.add_gateway(Gateway)
   
    # 添加功能模块
    main_engine.add_app(ChartWizardApp)
    
    # 创建控件
    main_windows = MainWindow(main_engine, event_engine)
    main_windows.showMaximized()

    # 运行应用
    qapp.exec()
    

if __name__ == "__main__":
    run()
    
    