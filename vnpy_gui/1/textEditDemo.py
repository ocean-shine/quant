from PySide6 import QtWidgets


TEXT = ""


if __name__ == "__main__":
    # QT应用（创建循环）
    qapp = QtWidgets.QApplication([])

    # 创建控件
    edit = QtWidgets.QTextEdit()
    edit.show()

    # 设置初始文字
    edit.setText("hello, world!")

    # # 全量设置（覆盖）
    edit.setText("Hello, again!")

    # # 尾部追加
    edit.append("hello, again!")

    # # 清空内容
    # edit.clear()

    # # 设置只读
    edit.setReadOnly(True)

    # # 设置颜色
    edit.setTextColor("red")

    # # 设置字体
    edit.setFontFamily("宋体")

    # # 设置字号
    edit.setFontPointSize(20)

    # # 追加内容 
    edit.append("自定义效果")

    # 退出应用
    qapp.exec()

