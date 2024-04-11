import matplotlib.pyplot as plt
import pandas as pd
from mpl_finance import candlestick2_ochl
import mplfinance as mpf
from unittest import TestCase

class TestPandasKline(TestCase):
    #读取股票数据，画出K线图
    def testKLineChart(self):
        file_name = "./demo.csv"
        df = pd.read_csv(file_name)
        df.columns = ["stock_id","date","close","open","high","low","volume"]

        fig = plt.figure()
        axes = fig.add_subplot(111)
        candlestick2_ochl(ax=axes,opens=df["open"].values,closes=df["close"].values,highs=df["high"].values,
                          lows=df["low"].values,width=0.75,colorup='red',colordown='green')
        plt.xticks(range(len(df.index.values)),df.index.values,rotation=30)
        axes.grid(True)
        plt.title("K-Line")
        plt.show()



    #K线图带交易量
    def testKLineByVolume(self):
        file_name = "./demo.csv"
        df = pd.read_csv(file_name)
        df.columns = ["stock_id","date","close","open","high","low","volume"]
        df = df[["date","close","open","high","low","volume"]]
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index('date')

        my_color = mpf.make_marketcolors(
            up = 'red',
            down = 'green',
            wick = 'i',
            volume = {'up':'red','down':'green'},
            ohlc = 'i'
        )

        my_style  = mpf.make_mpf_style(
            marketcolors = my_color,
            gridaxis = 'both',
            gridstyle = '-.',
            rc = {'font.family':'STSong'}
        )

        mpf.plot(
            df,
            type = 'candle',
            title = 'K-LineByVolume',
            ylabel = 'price',
            style = my_style,
            show_nontrading = False,
            volume = True,
            ylabel_lower = 'volume',
            datetime_format = '%Y-%m-%d',
            xrotation = 45,
            linecolor = '#00ff00',
            tight_layout = False
        )




    # K线图带交易量及均线
    def testKLineByMA(self):
        file_name = "./demo.csv"
        df = pd.read_csv(file_name)
        df.columns = ["stock_id","date","close","open","high","low","volume"]
        df = df[["date","close","open","high","low","volume"]]
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index('date')

        my_color = mpf.make_marketcolors(
            up = 'red',
            down = 'green',
            wick = 'i',
            volume = {'up':'red','down':'green'},
            ohlc = 'i'
        )

        my_style  = mpf.make_mpf_style(
            marketcolors = my_color,
            gridaxis = 'both',
            gridstyle = '-.',
            rc = {'font.family':'STSong'}
        )

        mpf.plot(
            df,
            type = 'candle',
            mav = [5,10],
            title='K-LineByVolume',
            ylabel='price',
            style=my_style,
            show_nontrading=False,
            volume=True,
            ylabel_lower='volume',
            datetime_format='%Y-%m-%d',
            xrotation=45,
            linecolor='#00ff00',
            tight_layout=False
        )
