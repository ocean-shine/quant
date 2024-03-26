from PySide6 import QtWidgets


if __name__ == "__main__":
    # Qt app (even loop)
    qapp = QtWidgets.QApplication([])

    # create control widgets
    line = QtWidgets.QLineEdit()
    line.show()

    # set inition text
    line.setText("genoral input box")

    # text capt
    def print_text():
        content: str = line.text()
        print(f"current box content is :{content}")

    line.returnPressed.connect(print_text)

    # set show mode 
    #line.setEchoMode(line.EchoMode.Normal)
    #line.setEchoMode(line.EchoMode.NoEcho)
    #line.setEchoMode(line.EchoMode.Password)
    #line.setEchoMode(line.EchoMode.PasswordEchoOnEdit)

    # set content complement
    data = ["开仓" ,"平仓", "平今", "平昨"]
    completer = QtWidgets.QCompleter(data)
    line.setCompleter(completer)
    # run app
    qapp.exec()
