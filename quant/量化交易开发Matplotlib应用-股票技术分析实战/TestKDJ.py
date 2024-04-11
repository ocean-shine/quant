import pandas as pd
import matplotlib.pyplot as plt


from unittest import TestCase

class TestKDJ(TestCase):
    def cal_kdj(self,df):
        low_list = df['low'].rolling(9,min_periods=9).min()
        low_list.fillna(value=df['low'].expanding().min(),inplace=True)
        high_list = df['high'].rolling(9,min_periods=9).max()
        high_list.fillna(value=df['high'].expanding().max(),inplace=True)
        rsv = (df['close'] - low_list) / (high_list - low_list) * 100
        df['k'] = pd.DataFrame(rsv).ewm(com=2).mean()
        df['d'] = df['k'].ewm(com=2).mean()
        df['j'] = 3 * df['k'] - 2 * df['d']
        return df

    def test_KDJ(self):
        file_name = "./demo.csv"
        df = pd.read_csv(file_name)
        df.columns = ["stock_id","date","close","open","high","low","volume"]
        df = df[["date","close","open","high","low","volume"]]
        df["date"] = pd.to_datetime(df["date"])

        df_kdj = self.cal_kdj(df)
        print(df_kdj)

        plt.figure()
        df_kdj['k'].plot(color="red",label='k')
        df_kdj['d'].plot(color="yellow",label='d')
        df_kdj['j'].plot(color="blue",label='j')
        plt.legend(loc='best')

        major_index = df_kdj.index[df_kdj.index]
        major_xtics = df_kdj['date'][df_kdj.index]
        plt.xticks(major_index,major_xtics)
        plt.setp(plt.gca().get_xticklabels(),rotation=30)

        plt.grid(linestyle='-.')
        plt.title('000001平安银行KDJ图')
        plt.rcParams['axes.unicode_minus'] = False
        plt.rcParams['font.sans-serif'] = ['SimHei']
        plt.show()

    def testBoll(self):
        import numpy as np
        from matplotlib.pyplot import plot
        from matplotlib.pyplot import show
        # 绘制布林带
        N = 5

        weights = np.ones(N) / N
        print("Weights", weights)

        c = np.loadtxt('demo.csv', delimiter=',', usecols=(2,), unpack=True)
        sma = np.convolve(weights, c)[N - 1:-N + 1]
        deviation = []
        C = len(c)

        for i in range(N - 1, C):
            if i + N < C:
                dev = c[i: i + N]
            else:
                dev = c[-N:]

            averages = np.zeros(N)
            averages.fill(sma[i - N - 1])
            dev = dev - averages
            dev = dev ** 2
            dev = np.sqrt(np.mean(dev))
            deviation.append(dev)

        deviation = 2 * np.array(deviation)
        print(len(deviation), len(sma))
        upperBB = sma + deviation
        lowerBB = sma - deviation

        c_slice = c[N - 1:]
        between_bands = np.where((c_slice < upperBB) & (c_slice > lowerBB))

        print(lowerBB[between_bands])
        print(c[between_bands])
        print(upperBB[between_bands])
        between_bands = len(np.ravel(between_bands))
        print("Ratio between bands", float(between_bands) / len(c_slice))

        t = np.arange(N - 1, C)
        plot(t, c_slice, lw=1.0)
        plot(t, sma, lw=2.0)
        plot(t, upperBB, lw=3.0)
        plot(t, lowerBB, lw=4.0)
        show()