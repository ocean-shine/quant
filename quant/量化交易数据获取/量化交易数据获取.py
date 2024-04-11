# 第六章代码
####################################################
# 6-1 history() 函数 代码实现1
from jqdata import *
security_list = ['600000.XSHG', '600006.XSHG']
data = history(count=10, unit='10d',field='open', security_list=security_list,df=True)
print(data)


####################################################
# 6-1 history() 函数 代码实现2
from jqdata import *
security_list = ['600000.XSHG', '600006.XSHG']
data = history(count=3, field='money', security_list=security_list, df=False)
print(data)


####################################################
# 6-1 attribute_history()函数 代码实现1
from jqdata import *
security = '600000.XSHG'
data = attribute_history(security=security,count=3, fields=['open','money','high'])
print(data)


####################################################
# 6-1 attribute_history()函数 代码实现2
print("最近5个交易日最高价的平均价是：")
security = '600000.XSHG'
high_5d = attribute_history(security=security, count=5, fields=['high'])
avg_5d = high_5d.mean()
print(avg_5d)


####################################################
# 6-2 attribute_history()函数 代码实现1
# 查询平安银行2022年9月1日的总市值
q = query(
    valuation
).filter(
    valuation.code == '000001.XSHE'
)
df = get_fundamentals(q, '2022-09-01')
# 打印出总市值
print(df['market_cap'][0])


####################################################
# 6-2 attribute_history()函数 代码实现2
# 查询平安银行2022年第二季度的财务数据
q = query(
        income.statDate,
        income.code,
        income.basic_eps,
        balance.cash_equivalents
    ).filter(
        income.code == '000001.XSHE',
    )

rets = get_fundamentals(q, statDate='2022q2')
print(rets)


####################################################
# 6-3 get_fundamentals_continuously()函数
q = query(valuation.turnover_ratio,
              valuation.market_cap,
              indicator.eps
            ).filter(valuation.code.in_(['000001.XSHE', '600000.XSHG']))
result = get_fundamentals_continuously(q, end_date='2022-01-01', count=5,panel=False)
print(result)


####################################################
# 6-3 get_current_data()函数
def initialize(context):
    g.security = "000001.XSHE"

def handle_data(context, data):
    current_data = get_current_data()
    print(current_data)
    print('最新价：{}'.format(current_data['000001.XSHE'].last_price))
    print('是否停牌：{}'.format(current_data['000001.XSHE'].paused))
    print('开盘价：{}'.format(current_data['000001.XSHE'].day_open))

####################################################
# 6-4 获取指数成分股函数get_index_stocks()
# 返回沪深300的股票（输出100个）
codes= get_index_stocks('000300.XSHG')
print(codes)[0:100}


####################################################
# 6-4 获取行业成分股函数get_industry_stocks()
# 获取计算机/互联网行业的成分股
stocks = get_industry_stocks('I64')
print(stocks)


####################################################
# 6-5 获取概念成本股函数get_concept_stocks()
# 获取风电概念板块的成分股
stocks = get_concept_stocks('SC0084', date='2022-09-01')
print(stocks)


####################################################
# 6-5 获取限售解禁数据函数get_locked_shares()
# 在策略中获取平安银行2016-01-01后1200天的解禁情况
df = get_locked_shares(stock_list=['000001.XSHE'],start_date='2016-01-01',forward_count=1200)
print(df)


####################################################
# 6-6 获取所有数据信息函数get_all_securities() 代码实现1
# 获取平台中所有数据信息，打印前十支
get_all_securities()[:10]


####################################################
# 6-6 获取所有数据信息函数get_all_securities() 代码实现2
# 获取平台中所有ETF的信息，打印前10支
get_all_securities(types=[ 'etf'], date='2022-09-01')[:10]


####################################################
# 6-6 获取一只股票的信息函数get_security_info()
# 获取000001.XSHE的上市日期、名称、类型
start_date = get_security_info('000001.XSHE').start_date
display_name=get_security_info('000001.XSHE').display_name
type=get_security_info('000001.XSHE').type
print('上市日期：',start_date,'\n名称：',display_name,'\n类型：',type)


# 获取一支股票 
# 获取000001.XSHE的2015年的按天数据 
df = get_price('000001.XSHE') 

# 获得000001.XSHG的2015年01月的分钟数据, 只获取open+close字段 df = get_price('000001.XSHE', count = 2, end_date='2015-01-31', frequency='daily', fields=['open', 'close']) 
df = get_price('000001.XSHE', start_date='2015-01-01', end_date='2015-01-31 23:00:00', frequency='1m', fields=['open', 'close'])

# 获取获得000001.XSHG在2015年01月31日前2个交易日的数据 
df = get_price('000001.XSHE', start_date='2015-12-01 14:00:00', end_date='2015-12-02 12:00:00', frequency='1m')

# 获得000001.XSHG的2015年12月1号14:00-2015年12月2日12:00的分钟数据 

# 获取多只股票
# 获取中证100的所有成分股的2015年的天数据 
df = get_price(get_price(get_index_stocks('000903.XSHG'),panel = False)) , 返回一个[pandas.Panel] 
open = df['open'] # 获取开盘价的[pandas.DataFrame], 行索引是[datetime.datetime]对象, 列索引是股票代号 
volume = df['volume']  # 获取交易量的[pandas.DataFrame] 


####################################################
# 6-7 获取龙虎榜数据get_billboard_list() 代码实现1
# 获得 2022-09-01 的龙虎榜数据
get_billboard_list(stock_list=None, end_date = '2022-09-01', count =1)


####################################################
# 6-7 获取龙虎榜数据get_billboard_list() 代码实现2
# 获得2022-09-01前两个交易日内的龙虎榜数据中的股票代码、异常波动名称、营业部名称、出资价格排名，打印前十条
df=get_billboard_list(stock_list=None, end_date = '2022-09-01', count =2)
print(df[['code','abnormal_name','sales_depart_name','rank']][:10])


