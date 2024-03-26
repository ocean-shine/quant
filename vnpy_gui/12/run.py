from PySide6 import QtWidgets


def run() -> None:
    """主程序入口"""
    # Qt应用（事件循环）
    qapp = QtWidgets.QApplication([])

    # 创建表格
    table = QtWidgets.QTableWidget()
    table.show()
    # 设置行列
    table.setRowCount(5)
    table.setColumnCount(7)

    # 插入单元格
    cell = QtWidgets.QTableWidgetItem("第一个单元格")
    table.setItem(0, 0, cell)

    # 插入控件
    button = QtWidgets.QPushButton("测试按钮")
    table.setCellWidget(1, 0, button)
    
    # 设置水平表头
    table.setHorizontalHeaderLabels("abcdefg")
    
    # 遍历填充
    for i in range(25):
        row = i//5
        columu = i%5
        table.setItem(row, columu, QtWidgets.QTableWidgetItem(str(i)))
    # 运行应用
    qapp.exec()


if __name__ == "__main__":
    run()
     