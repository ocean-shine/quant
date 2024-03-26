import tushare as ts
import pandas as pd 


data = pd.read_csv("01.csv")
len = len(data)
for i in range(len):
    print