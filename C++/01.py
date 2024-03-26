import tushare as ts

ts.set_token("f9d25f4ab3f0abe5e04fdf76c32e8c8a5cc94e384774da025098ec6e")
pro = ts.pro_api()
data = pro.stock_basic(exchange='', list_status='L', fields='ts_code,symbol,name,area,industry,list_date')
data.to_csv("01.csv")