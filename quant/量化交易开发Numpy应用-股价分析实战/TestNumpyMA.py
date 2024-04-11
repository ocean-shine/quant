import numpy as np
import matplotlib.pyplot as plt

from unittest import TestCase
from pathlib import Path
import os


current_file_path = Path(__file__).parent
demo_csv = f"{current_file_path}/demo.csv"

class TestNumpyMA(TestCase):

    def testSMA(self):
        file_name = demo_csv
        end_price = np.loadtxt(
            fname=file_name,
            delimiter=',',
            usecols=(2),
            unpack=True
        )
        print(end_price)
        N = 5
        weights = np.ones(N) / N
        print(weights)
        sma = np.convolve(weights,end_price)[N-1:-N+1]
        print(sma)
        plt.plot(sma,linewidth=5)
        plt.show()


    def testEXP(self):
        x = np.arange(5)
        y = np.arange(10)
        print("x", x)  # exp 函数可以计算出每个数组元素的指数
        print("y", y)
        print("""Exp x : {}""".format(np.exp(x)))
        print("""Exp y : {}""".format(np.exp(y)))
        print("""Linespace : {}""".format(np.linspace(-1,0,5)))



    def testEMA(self):
        file_name = demo_csv
        end_price = np.loadtxt(
            fname=file_name,
            delimiter=',',
            usecols=(2),
            unpack=True
        )
        print(end_price)
        N = 5
        weighs = np.exp(np.linspace(-1,0,N))
        weighs /= weighs.sum()
        print(weighs)
        ema = np.convolve(weighs,end_price)[N-1:-N+1]
        print(ema)

        t = np.arange(N-1,len(end_price))
        plt.plot(t,end_price[N-1:],lw=1.0)
        plt.plot(t,ema,lw=2.0)
        plt.show()


if __name__ == '__main__' :
    test_instance = TestNumpyMA()
    test_instance.testSMA()

