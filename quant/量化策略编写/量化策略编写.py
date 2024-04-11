# -*- coding:utf-8 -*-
################################################
# 5-2 代码对比1·左
def initialize(context):
    # 设定基准为“浦发银行”
    set_benchmark('600000.XSHG')

    g.security = "000001.XSHE"

    run_daily(market_open, time='9:30')

def market_open(context):
    # 如果没有持仓
    if g.security not in context.portfolio.positions:
        # 下单1000股
        order(g.security, 1000)
    else:
        # 卖出800股
        order(g.security, -800)


################################################
# 5-2 代码对比1·右
def initialize(context):
    # 设定基准为“沪深300”
    set_benchmark('000300.XSHG')

    g.security = "000001.XSHE"

    run_daily(market_open, time='9:30')

def market_open(context):
    # 如果没有持仓
    if g.security not in context.portfolio.positions:
        # 下单1000股
        order(g.security, 1000)
    else:
        # 卖出800股
        order(g.security, -800)


################################################
# 5-2 代码对比2·左
def initialize(context):
    g.security = "000001.XSHE"

    run_daily(market_open, time='9:30')

def market_open(context):
    # 如果没有持仓
    if g.security not in context.portfolio.positions:
        # 下单1000股
        order(g.security, 1000)
    else:
        # 卖出800股
        order(g.security, -800)


################################################
# 5-2 代码对比2·右
def initialize(context):
    g.security = "000001.XSHE"

    run_daily(market_open, time='9:30')

    # 设定佣金（夸张，从万分之三到百分之三）
    set_order_cost(OrderCost(open_commission=0.03,close_commission = 0.03, close_tax = 0.001, min_commission = 5), type = 'stock')

def market_open(context):
    if g.security not in context.portfolio.positions:
        order(g.security, 1000)
    else:
        order(g.security, -800)


################################################
# 5-3 代码对比·右
def initialize(context):
    # 设定基准为“浦发银行”
    set_benchmark('600000.XSHG')

    g.security = "000001.XSHE"

    # 每天 10:00 运行
    run_daily(market_open, time='10:00')

def market_open(context):
    # 如果没有持仓
    if g.security not in context.portfolio.positions:
        # 下单1000股
        order(g.security, 1000)
    else:
        # 卖出800股
        order(g.security, -800)


################################################
# 5-3 代码对比·右
def initialize(context):
    # 设定基准为“沪深300”
    set_benchmark('000300.XSHG')

    g.security = "000001.XSHE"

    # 每周一 9：30 运行
    run_weekly(market_open,weekday,time='open')

def market_open(context):
    # 如果没有持仓
    if g.security not in context.portfolio.positions:
	# 下单1000股
        order(g.security, 1000)
    else:
	# 卖出800股
        order(g.security, -800)


################################################
# 5-4 代码实现1
def initialize(context):
    set_benchmark('000300.XSHG')

    g.security = "000001.XSHE"

    run_daily(market_open, time='9:30')

def market_open(context):
    cash = context.portfolio.available_cash

    # 如果没有持仓
    if g.security not in context.portfolio.positions:
        # 全仓买入（即花费所有的可用资金）
        order_value(g.security, cash)
    else:
        # 全仓卖出（即卖出至资金为0）
        order_target(g.security, 0)


################################################
# 5-4 代码实现2
def initialize(context):
    set_benchmark('000300.XSHG')
    g.security = "000001.XSHE"
    run_daily(market_open, time='9:30')
    run_daily(after_market_close, time='15:30')

def market_open(context):
    # 向账户增加10000元
    inout_cash(10000, pindex=0)
    # 查询可用资金
    log.info('账户可用资金：', context.portfolio.subportfolios[0].available_cash)
    # 如果没有持仓
    if g.security not in context.portfolio.positions:
        # 下单10000元
        order_value(g.security, 10000)
    else:
        order(g.security, -800)

        # 获取当前订单信息
    orders = get_orders(security='000001.XSHE')
    for _order in orders:
        log.info('成交记录：' + str(_order))

def after_market_close(context):
    # 在每天交易结束之后获取当天所有的未完成订单
    orders = get_open_orders()
    for _order in orders:
        log.info('未完成订单：' + str(_order))
    # 在每天交易结束之后对未完成订单进行撤单
    for _order in orders.values():
        cancel_order(_order)
        log.info('撤单：' + str(_order))


################################################
# 5-5 Order对象代码实现
def initialize(context):
    # 设定基准为“沪深300”
    set_benchmark('000300.XSHG')

    g.security = "000001.XSHE"

    run_weekly(market_open, 1, time='open')

def market_open(context):
    # 如果没有持仓
    if g.security not in context.portfolio.positions:

        orders = order(g.security, 100)
        print(orders)
        if orders is None:
            print("创建订单失败...")

        else:
            print("交易费用单：{0}".format(orders.commission))
            print("是否买单：{0}".format(orders.is_buy))
            print("订单状态：{0}".format(orders.status))
            print("订单平均成交价格：{0}".format(orders.price))
    else:
        order(g.security, -800)


################################################
# 5-5 全局对象代码实现
def initialize(context):
    g.security = "000001.XSHE"
    g.count = 1
    g.flag = 0

def process_initialize(context):
    # 保存不能被序列化的对象, 进程每次重启都初始化
    g.__q = query(valuation)

def handle_data(context, data):
    log.info(g.security)
    log.info(g.count)
    log.info(g.flag)


################################################
# 5-5 Trade对象代码实现
def initialize(context):
    set_benchmark('000300.XSHG')
    # 设定标的股票为深交所的平安银行
    g.security = "000001.XSHE"

    # 周期运行（即每天9:30调用一次）handle_data函数
    run_daily(market_open, time='9:30')
    run_daily(after_market_close, time='15:30')

def market_open(context):
    # 如果没有持仓
    if g.security not in context.portfolio.positions:
        # 下单1000股
        order(g.security, 1000)
    else:
        # 卖出800股
        order(g.security, -800)

def after_market_close(context):
    log.info(str('函数运行时间(after_market_close):' + str(context.current_dt.time())))
    # 得到当天所有成交记录
    trades = get_trades()
    for _trade in trades.values():
        print('成交记录：' + str(_trade))
        print('交易时间：{0}'.format(_trade.time))
        print('对应的订单id：{0}'.format(_trade.order_id))
        log.info('一天结束')


################################################
# 5-6 Context对象代码实现1
def initialize(context):
    g.security = "000001.XSHE"

def handle_data(context, data):
    # 执行下面的语句之后, context.portfolio 变为整数 1
    context.portfolio = 1
    log.info(context.portfolio)
    # 恢复系统的变量
    del context.portfolio
    #  context.portfolio 将变成账户信息.
    log.info(context.portfolio.total_value)


################################################
# 5-6 Context对象代码实现2
def initialize(context):
    g.security = "000001.XSHE"

def handle_data(context, data):
    # 输出账户总资产
    log.info(context.portfolio.total_value)

    # 输出持仓额
    log.info(context.portfolio.positions_value)

    # 输出今天日期
    log.info(context.current_dt.day)

    # 总权益的累计收益
    log.info(context.portfolio.returns)

    # 获取仓位subportfolios[0]的可用资金
    log.info(context.subportfolios[0].available_cash)


################################################
# 5-6 Position对象代码实现
def initialize(context):
    g.security = "000001.XSHE"

def handle_data(context, data):
    if g.security not in context.portfolio.positions:
        # 下单1000股
        order(g.security, 1000)
    else:
        # 卖出800股
        order(g.security, -800)

    print(type(context.portfolio.long_positions))
    long_positions_dict = context.portfolio.long_positions
    for position in list(long_positions_dict.values()):
        print("标的:{0},总仓位:{1},标的价值:{2}, 建仓时间:{3}".format(position.security, position.total_amount, position.value,
                                                         position.init_time))


################################################
# 5-6 SubPortfolio对象代码实现
def initialize(context):
    g.security = "000001.XSHE"

def handle_data(context, data):
    if g.security not in context.portfolio.positions:
        order(g.security, 1000)
    else:
        order(g.security, -800)
    print("累计出入金:{0}".format(context.subportfolios[0].inout_cash))
    print("可用资金:{0}".format(context.subportfolios[0].available_cash))
    print("可取资金:{0}".format(context.subportfolios[0].transferable_cash))

    print("挂单锁住资金:{0}".format(context.subportfolios[0].locked_cash))
    print("账户所属类型:{0}".format(context.subportfolios[0].type))

    long_positions_dict = context.subportfolios[0].long_positions
    for position in list(long_positions_dict.values()):
        print("标的:{0},总仓位:{1},标的价值:{2}".format(position.security, position.total_amount, position.value))
        print("持仓价值:{0}".format(context.subportfolios[0].positions_value))
        print("总资产:{0}".format(context.subportfolios[0].total_value))


################################################
# 5-7 Portfolio对象代码实现
def initialize(context):
    g.security = "000001.XSHE"

def handle_data(context, data):
    if g.security not in context.portfolio.positions:
        order(g.security, 1000)
    else:
        order(g.security, -800)
    print("多单的仓位:{0}".format(context.portfolio.long_positions))
    print("空单的仓位:{0}".format(context.portfolio.short_positions))
    print("总权益:{0}".format(context.portfolio.total_value))
    print("总权益的累计收益:{0}".format(context.portfolio.returns))
    print("初始资金:{0}".format(context.portfolio.starting_cash))
    print("持仓价值:{0}".format(context.portfolio.positions_value))


################################################
# 5-7 SecurityUnitData对象代码实现
def initialize(context):
    g.security = "000001.XSHE"

def handle_data(context, data):  #
    open_price = attribute_history(g.security, 5, '1d', ['open'])
    close_price = attribute_history(g.security, 5, '1d', ['close'])
    low_price = attribute_history(g.security, 5, '1d', ['low'])
    high_price = attribute_history(g.security, 5, '1d', ['high'])
    volume = attribute_history(g.security, 5, '1d', ['volume'])
    money = attribute_history(g.security, 5, '1d', ['money'])
    print('open_price',open_price)
    print('close_price',close_price)
    print('low_price',low_price)
    print('high_price',high_price)
    print('volume',volume)
    print('money',money)




