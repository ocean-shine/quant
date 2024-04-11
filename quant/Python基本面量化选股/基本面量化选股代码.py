# 第7章代码
####################################################
# 7-1（选白马股）
import datetime

## 初始化函数，设定要操作的股票、基准等等
def initialize(context):
    # 设定沪深300作为基准
    set_benchmark('000300.XSHG')
    # True为开启动态复权模式，使用真实价格交易
    set_option('use_real_price', True) 
    # 设定成交量比例
    set_option('order_volume_ratio', 1)
    # 股票类交易手续费是：买入时佣金万分之三，卖出时佣金万分之三加千分之一印花税, 每笔交易佣金最低扣5块钱
    set_order_cost(OrderCost(open_tax=0, close_tax=0.001, \
                             open_commission=0.0003, close_commission=0.0003,\
                             close_today_commission=0, min_commission=5), type='stock')
    # 持仓数量
    g.stocknum = 20 
    # 交易日计时器
    g.days = 0 
    # 调仓频率
    g.refresh_rate = 100
    # 运行函数
    run_daily(trade, 'every_bar')

## 选出逻辑
def check_stocks(context):
    # 设定查询条件
    q = query(
            indicator.code,
            valuation.capitalization,
            indicator.roe,
            indicator.gross_profit_margin,
        ).filter(
            valuation.capitalization > 50,#1.总市值>50亿
            valuation.circulating_market_cap > valuation.market_cap*0.95,#3.流通盘比例>95%
            indicator.gross_profit_margin > 20,#4.销售毛利率>20%    
            indicator.roe > 20,#5.扣非净资产收益率>20%                            
        ).order_by(
            valuation.market_cap.desc()
        ).limit(
            100
        )
    
    df = get_fundamentals(q, statDate=str(context.current_dt)[:4])
    buylist = list(df['code'])
    #上市天数>750(抛开3年以内的次新)
    buylist = delect_stock(buylist, context.current_dt, 750)
    buylist = filter_paused_stock(buylist)[:20]

    return buylist
  
## 交易函数
def trade(context):
    if g.days%g.refresh_rate == 0:
        ## 选股
        stock_list = check_stocks(context)
        ## 获取持仓列表
        sell_list = list(context.portfolio.positions.keys())

        sells = list( set(sell_list).difference(set(stock_list)) )        
        #先卖再买
        for stock in sells:
            order_target_value(stock, 0)

        ## 分配资金
        if len(context.portfolio.positions) < g.stocknum :
            num = g.stocknum - len(context.portfolio.positions)
            cash = context.portfolio.cash/num
        else: 
            cash = 0    
        
        for stock in stock_list:
            if len(context.portfolio.positions) < g.stocknum \
                and stock not in context.portfolio.positions:
                order_value(stock, cash)

        # 天计数加一
        g.days = 1
    else:
        g.days += 1

# 过滤停牌股票
def filter_paused_stock(stock_list):
    current_data = get_current_data()
    return [stock for stock in stock_list if not current_data[stock].paused]
    
#排除次新
def delect_stock(stocks,beginDate,n=180):
    #去除上市距beginDate不足6个月的股票
    stockList = []
    for stock in stocks:
        start_date = get_security_info(stock).start_date
        if start_date < (beginDate-timedelta(days = n)).date():
            stockList.append(stock)
    return stockList
    


####################################################
# 7-2-1
# 打印营业收入同比增长率大于300的股票代码，并降序排列

df=get_fundamentals(
    query(
        indicator.code,
        indicator.inc_revenue_year_on_year
    ).filter(
      indicator.inc_revenue_year_on_year>300
    ).order_by(indicator.inc_revenue_year_on_year.desc())
    ,date='2022-09-01')

print(df)

# 根据以上查询出的股票代码，获取它们近5日的每日最高价
df_new=history(5,unit='1d',field='high_limit',security_list=df['code'],df=True)
print(df_new)


####################################################
# 7-2-2
# 打印营业收入环比增长率大于900的股票代码，并降序排列

df=get_fundamentals(
    query(
        indicator.code,
        indicator.inc_revenue_annual
    ).filter(
      indicator.inc_revenue_annual>900
    ).order_by(indicator.inc_revenue_year_on_year.desc())
    ,date='2022-09-01')

print(df)


####################################################
# 7-2-3
# 营业总收入

df=get_fundamentals(
    query(
        indicator.code,
        indicator.net_profit_to_total_revenue
    ).order_by(
    indicator.net_profit_to_total_revenue.desc())
    ,date='2022-09-01')

print(df)


####################################################
# 7-3-1
# 打印净利润同比增长率大于300的股票代码，并降序排列

df=get_fundamentals(
    query(
        indicator.code,
        indicator.inc_net_profit_year_on_year
    ).filter(
      indicator.inc_net_profit_year_on_year>300
    ).order_by(indicator.inc_net_profit_year_on_year.desc())
    ,date='2022-09-01')

print(df)


####################################################
# 7-3-2
# 打印净利润环比增长率大于500的股票代码，并降序排列

df=get_fundamentals(
    query(
        indicator.code,
        indicator.inc_net_profit_annual
    ).filter(
      indicator.inc_net_profit_annual>500
    ).order_by(indicator.inc_net_profit_annual.desc())
    ,date='2022-09-01')

print(df[:5])


####################################################
# 7-3-3
# 打印营业利润率大于200的股票代码，并降序排列

df=get_fundamentals(
    query(
        indicator.code,
        indicator.operation_profit_to_total_revenue
    ).filter(
      indicator.operation_profit_to_total_revenue>200
    ).order_by(indicator.operation_profit_to_total_revenue.desc())
    ,date='2022-09-01')
print(df[:5])


####################################################
# 7-3-4
# 打印销售净利润最高的五个股票代码

df=get_fundamentals(
    query(
        indicator.code,
        indicator.net_profit_margin
    ).order_by(indicator.net_profit_margin.desc())
    ,date='2022-09-01')
print(df[:5])


####################################################
# 7-3-5
# 打印销售毛利润最高的五个股票代码

df=get_fundamentals(
    query(
        indicator.code,
        indicator.gross_profit_margin
    ).
    order_by(indicator.gross_profit_margin.desc())
    ,date='2022-09-01')
print(df[:5])


####################################################
# 7-4-1
# 打印总市值大于10000亿的股票代码，并降序排列

df=get_fundamentals(
    query(
        valuation.code,
        valuation.market_cap
    ).filter(
      valuation.market_cap>10000)
    .order_by(valuation.market_cap.desc())
    ,date='2022-09-01')

print(df[:5])


####################################################
# 7-4-2
# 打印流通市值大于5000亿的股票代码，并降序排列

df=get_fundamentals(
    query(
        valuation.code,
        valuation.circulating_market_cap
    ).filter(
      valuation.circulating_market_cap>5000)
    .order_by(valuation.circulating_market_cap.desc())
    ,date='2022-09-01')

print(df[:5])


####################################################
# 7-4-3
# 打印总股本大于1000亿股、总市值大于8000亿的股票代码，并降序排列

df=get_fundamentals(
    query(
        valuation.code,
        valuation.market_cap,
         valuation.capitalization
    ).filter(
      valuation.market_cap>8000,
      valuation.capitalization>10000000
)
    .order_by(valuation.capitalization.desc())
    ,date='2022-09-01')
print(df[:5])


####################################################
# 7-4-4
# 打印流通股本大于1000亿股、流通市值大于5000亿的股票代码，并降序排列

df=get_fundamentals(
    query(
        valuation.code,
        valuation.circulating_market_cap,
        valuation.circulating_cap,
    ).filter(
      valuation.circulating_market_cap>5000,
      valuation.circulating_cap>10000000)
    .order_by(valuation.circulating_cap.desc())
    ,date='2022-09-01')

print(df[:5])


####################################################
# 7-5-1
# 打印市净率小于1.5、总市值大于8000亿的股票代码，并升序排列

df=get_fundamentals(
    query(
        valuation.code,
        valuation.pb_ratio,
        valuation.market_cap
    ).filter(
      valuation.market_cap>8000,
      valuation.pb_ratio<1.5)
    .order_by(valuation.pb_ratio.asc())
    ,date='2022-09-01')

print(df[:5])


####################################################
# 7-5-2
# 打印市净率小于1.5、市销率小于0.5的股票代码，并升序排列

df=get_fundamentals(
    query(
        valuation.code,
        valuation.pb_ratio,
        valuation.ps_ratio
    ).filter(
      valuation.pb_ratio<1.5,
      valuation.ps_ratio<0.5)
    .order_by(valuation.ps_ratio.asc())
    ,date='2022-09-01')

print(df[:5])


####################################################
# 7-5-3
# 打印动态市盈率小于6，市销率小于0.5，静态市盈率在3-5之间的股票函数，并按照静态市盈率升序排列

df=get_fundamentals(
    query(
        valuation.code,
        valuation.pcf_ratio,
        valuation.pe_ratio,
        valuation.ps_ratio,
    ).filter(
      valuation.ps_ratio<0.5,
      valuation.pcf_ratio<6,
      valuation.pe_ratio>3,
      valuation.pe_ratio<5,)
    .order_by(valuation.pe_ratio.asc())
    ,date='2022-09-01')

print(df[:5])


####################################################
# 7-6-1
# 打印净资产收益率大于50的股票代码，并降序排列

df=get_fundamentals(
    query(
        indicator.code,
        indicator.roe
    ).filter(
      indicator.roe>50
    ).order_by(indicator.roe.desc())
   )

print(df[:10])


####################################################
# 7-6-2
# 打印总资产净利率大于10的股票代码，并降序排列

df=get_fundamentals(
    query(
        indicator.code,
        indicator.roa
    ).filter(
      indicator.roa> 10
    ).order_by(indicator.roa.desc())
   )

print(df[:10])







