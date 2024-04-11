import matplotlib.pyplot as plt
import pandas as pd
from unittest import TestCase

class TestPandasStock(TestCase):
    #读取文件
    def testReadFile(self):
        file_name = "./demo.csv"
        df = pd.read_csv(file_name)

        print(df.info())
        print("-------------")
        print(df.describe())


    #时间处理
    def testTime(self):
        file_name = "./demo.csv"
        df = pd.read_csv(file_name)
        df.columns = ["stock_id","date","close","open","high","low","volume"]

        df["date"] = pd.to_datetime(df["date"])

        df["year"] = df["date"].dt.year
        df["month"] = df["date"].dt.month

        print(df)





    # 最低收盘价
    def testCloseMin(self):
        file_name = "./demo.csv"
        df = pd.read_csv(file_name)
        df.columns = ["stock_id","date","close","open","high","low","volume"]

        print("""close min : {}""".format(df["close"].min()))
        print("""close min index : {}""".format(df["close"].idxmin()))
        print("""close min frame : {}""".format(df.loc[df["close"].idxmin()]))




    # 每月平均收盘价与开盘价
    def testMean(self):
        file_name = "./demo.csv"
        df = pd.read_csv(file_name)
        df.columns = ["stock_id","date","close","open","high","low","volume"]

        df["date"] = pd.to_datetime(df["date"])
        df["month"] = df["date"].dt.month

        print("""month close mean : {}""".format(df.groupby("month")["close"].mean()))
        print("""month open mean : {}""".format(df.groupby("month")["open"].mean()))



    # 计算涨跌幅
    # 涨跌幅今日收盘价减去昨日收盘价
    def testRipples_ratio(self):
        file_name = "./demo.csv"
        df = pd.read_csv(file_name)
        df.columns = ["stock_id","date","close","open","high","low","volume"]

        df["date"] = pd.to_datetime(df["date"])

        df["rise"] = df["close"].diff()
        df["rise_ratio"] = df["rise"] / df.shift(-1)["close"]

        print(df)

    # 计算股价移动平均
    def testMA(self):
        file_name = "./demo.csv"
        df = pd.read_csv(file_name)
        df.columns = ["stock_id","date","close","open","high","low","volume"]

        df['ma_5'] = df.close.rolling(window=5).mean()
        df['ma_10'] = df.close.rolling(window=10).mean()
        df = df.fillna(0)

        print(df)


