import tushare as ts
# from matplotlib import pylab
import numpy as np
import pandas as pd
# import DataAPI
# import seaborn as sns
from pathlib import Path
import os


current_file_path = Path(__file__).parent
# sns.set_style('white')


ts.set_token("f9d25f4ab3f0abe5e04fdf76c32e8c8a5cc94e384774da025098ec6e")
# ts.set_token("c55a04c68dbee6559ee05aa9efb7812a90aa8ad80cec5e9dbcd06595")
pro = ts.pro_api()
# data = pro.stock_basic(exchange='', list_status='L', fields='ts_code,symbol,name,area,industry,list_date')
# data.to_csv("01.csv")
secID = '510050.XSHG'
start = '20240101'
end = '20240223'

# security = DataAPI.MktFunddGet(secID, beginDate=start, endDate=end, field=['trade_date', 'closePrice'])
# security = pro.stock_basic(exchange='', list_status='L', fields='{secID},symbol,name,area,industry,list_date')
security= pro.daily(ts_code="000001.SZ", start_date=start, end_date=end)
security.head()
# security['trade_date'] = pd.to_datetime(security['trade_date'])
# security = security.set_index('trade_date')
# security.to_csv("{current_file_path}01.csv")
# security.info()


