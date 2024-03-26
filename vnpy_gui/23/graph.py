import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore


# 准备数据
data: list = list(np.random.normal(size=100))

# 创建绘图控件
w: pg.GraphicsLayoutWidget = pg.GraphicsLayoutWidget(
    show=True,
    title="绘图控件" 
)

# 添加图标
p: pg.PlotItem = w.addPlot(title="Line chart")

# 绘制数据
# p.plot(data)

# 调整绘笔效果
pen: pg.QtGui.QPen = pg.mkPen(
    color="g",
    width=3
)
curve: pg.PlotDataItem = p.plot(
    data,
    pen=pen,
    symbol="+"
)


# 更新数据
def update_data():
    global curve
    data.append(np.random.normal())
    curve.setData(data)
    
    
timer: QtCore.QTimer = QtCore.QTimer()
timer.timeout.connect(update_data)
timer.start(100)

if __name__ =="__main__":
    pg.exec()