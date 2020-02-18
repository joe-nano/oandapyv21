import pandas as pd
import numpy as np
from oandapyV20 import API
from oandapyV20.exceptions import V20Error
import oandapyV20.endpoints.instruments as instruments
import oandapyV20.endpoints.accounts as accounts
import oandapyV20.endpoints.orders as orders
import oandapyV20.endpoints.positions as positions
import oandapyV20.endpoints.pricing as pricing
from oandapyV20.endpoints.pricing import PricingInfo
from oandapyV20.contrib.requests import (MarketOrderRequest, StopLossDetails)
import oandapyV20.endpoints.forexlabs as labs
import datetime
from statistics import mean
from statistics import median
from statistics import StatisticsError
import calendar
import datetime
from math import floor
import time
import itertools
from decimal import Decimal
from plotly.figure_factory import create_candlestick

# OANDA API v20の口座IDとAPIトークン
accountID = "101-009-12609641-001"
access_token = "11f2a77cf99d3d29afc4c1cb1a0fb36b-e0fc1d1bf476926157f1d5992466fdf4"
# OANDAのデモ口座へのAPI接続
api = API(access_token=access_token, environment="practice")

# APIから取得したレートをPandasのDataFrameへ
def to_dataframe(r):
    data = []
    for raw in r.response['candles']:
        data.append([raw['time'], raw['volume'], raw['mid']['o'], raw['mid']['h'], raw['mid']['l'], raw['mid']['c']])

    # リストからPandas DataFrameへ変換
    df = pd.DataFrame(data)
    df.columns = ['Time', 'Volume', 'Open', 'High', 'Low', 'Close']
    df['Time'] = pd.to_datetime(df['Time'])
    for col in ['Open', 'High', 'Low', 'Close']:
        df[col] = df[col].apply(float)
    return df

# 第何何曜日（第nX曜日）の日付を返す関数
def get_day_of_nth_dow(year, month, nth, dow):
    '''dow: Monday(0) - Sunday(6)'''
    if nth < 1 or dow < 0 or dow > 6:
        return None

    first_dow, n = calendar.monthrange(year, month)
    day = 7 * (nth - 1) + (dow - first_dow) % 7 + 1

    return day if day <= n else None

def get_data_super(start, end, gran, inst='USD_JPY'):
    f = True
    f_count = 0
    while f:
        try:
            api = API(access_token=access_token, environment="practice")
            # xxxx-xx-xx～xxxx-xx-xx の期間のデータを取得してデータフレームを返す
            s_year, s_month, s_day, s_hour, s_minute, s_second = map(int, start.split('-'))
            e_year, e_month, e_day, e_hour, e_minute, e_second = map(int, end.split('-'))
            fmt = '%Y-%m-%dT%H:%M:00.000000Z'
            from_ = datetime.datetime(year=s_year, month=s_month, day=s_day,
                                      hour=s_hour, minute=s_minute, second=s_second).strftime(fmt)
            to_ = datetime.datetime(year=e_year, month=e_month, day=e_day,
                                    hour=e_hour, minute=e_minute, second=e_second).strftime(fmt)
            to_dt = '{}-{}-{} {}:{}:{}'.format(e_year, e_month, e_day, e_hour, e_minute, e_second)
            to_unix = datetime.datetime.strptime(to_dt, '%Y-%m-%d %H:%M:%S').timestamp()
            df = pd.DataFrame()
            # 5000個制限に引っかからなければこっちの処理
            try:
                params = {
                    "granularity": gran,
                    'from': from_,
                    'to': to_
                }
                r = instruments.InstrumentsCandles(instrument=inst, params=params)
                api.request(r)
                df = to_dataframe(r)
                f = False
            # 引っかかればこっちの処理
            except:
                i = True
                while i:
                    df_tmp = get_data(count=5000, gran=gran, year=s_year, month=s_month, day=s_day,
                                     hour=s_hour, minute=s_minute, second=s_second, inst=inst)
                    # ケツが同じなら止める (最新迄用)
                    if df.tail(1).reset_index(drop=True).equals(df_tmp.tail(1).reset_index(drop=True)):
                        i = False
                    else:
                        df = pd.concat([df, df_tmp[:-1]], ignore_index=True)
                        index = df_tmp.tail(1).index[0]
                        s_year = df_tmp.iat[index, 0].year
                        s_month = df_tmp.iat[index, 0].month
                        s_day = df_tmp.iat[index, 0].day
                        s_hour = df_tmp.iat[index, 0].hour
                        s_minute = df_tmp.iat[index, 0].minute
                        s_second = df_tmp.iat[index, 0].second
                        # 5000個ずつ取得してエンドの unix 超えたら止める
                        if to_unix < df.iat[df.tail(1).index[0], 0].timestamp():
                            # はみ出した分をここで切り落とす
                            for i in range(len(df.index) - 5000, len(df.index)):
                                if to_unix <= df.iat[i, 0].timestamp():
                                    df = df[:i]
                                    break
                            i = False
                f = False
        except Exception as e:
            if f_count > 10:
                print(e)
                f = False
            time.sleep(5)
            f_count+=1
            pass
    return df

def get_data(count, gran, year, month, day, hour, minute, second, inst='USD_JPY'):
    fmt = '%Y-%m-%dT%H:%M:00.000000Z'
    _from = datetime.datetime(year=year, month=month, day=day,
                              hour=hour, minute=minute, second=second).strftime(fmt)
    params = {
        "count": count,
        "granularity": gran,
        'from': _from,
    }
    r = instruments.InstrumentsCandles(instrument=inst, params=params)
    api.request(r)
    df = to_dataframe(r)
    return df

def get_evaluation(pos_df, return_=False):
    # 勝率
    win_c = pos_df[pos_df['pips'] >=0].shape[0]
    P = win_c / len(pos_df.index)
    # ペイオフレシオ
    try:
        win_p = mean(pos_df[pos_df['pips'] >=0]['pips'])
    except StatisticsError:
        win_p = 0
    los_p = mean(pos_df[pos_df['pips'] < 0]['pips']) * (-1)
    R = win_p / los_p
    # プロフィットファクター
    pf = pos_df[pos_df['profit']>0]['profit'].sum() / pos_df[pos_df['profit']<=0]['profit'].sum() * (-1)
    # 期待値
    try:
        win_pro = mean(pos_df[pos_df['pips'] >=0]['profit'])
    except StatisticsError:
        win_pro = 0
    los_pro = mean(pos_df[pos_df['pips'] < 0]['profit']) * (-1)
    E = P * win_pro - pos_df[pos_df['pips'] < 0].shape[0] / len(pos_df.index) * los_pro
    # 最大ドローダウン
    dd_l = {}
    max_l = []
    for i in range(1, len(pos_df)):
        assets = pos_df['assets'][:i]
        max_l.append(assets.max())
        dd_l[i] = assets.max() - assets.tail(1).values[0]
    key, max_dd = max(dd_l.items(), key=lambda x: x[1])
    max_dd_p = max_dd / max(max_l[:key]) * 100
    # ケリー基準
    try:
        kly = ((R + 1) * P - 1) / R
    except ZeroDivisionError:
        kly = -0.99999
    if return_:
        # WP, POR, PF, E, DD, KLY
        return round(P*100, 2), round(R, 4), round(pf, 4), round(E, 3), round(max_dd_p, 2), round(kly*100, 2)
    else:
        print('勝率: {:.2f}%'.format(P*100))
        print('ペイオフレシオ: {:.4f}'.format(R))
        print('プロフィットファクター: {:.4f}'.format(pf))
        print('期待値: {:.3f}円'.format(E))
        print('最大ドローダウン: {:.1f}円, {:.2f}%'.format(max_dd, max_dd_p))
        print('ケリー基準: {:.2f}%'.format(kly*100))

def entry_plot(pos_df, df, type_='head', n=50, m=20, b=3):
    if type_ == 'head':
        indexes = pos_df.head(n).index
    elif type_ == 'lose_head':
        indexes = pos_df[pos_df['pips']<0].head(n).index
    elif type_ == 'win_head':
        indexes = pos_df[pos_df['pips']>=0].head(n).index
    elif type_ == 'sort_t':
        indexes = pos_df.sort_values(by='pips', ascending=True).head(n).index
    elif type_ == 'sort_f':
        indexes = pos_df.sort_values(by='pips', ascending=False).head(n).index
    for idx in indexes:
        entry_date = pos_df[idx:idx+1]['entry_date'].values[0]
        l_or_s = pos_df[idx:idx+1]['l_or_s'].values[0]
        i = df[df['Time']==entry_date].index[0]
        plt.title(entry_date)
        plt.plot(df[i-b:i+m]['Open'], 'C1o', label="Open")
        plt.plot(df[i-b:i+m]['Close'], 'C0o', label="Close")
        plt.vlines(i, df[i-b:i+m]['Close'].max(), df[i-b:i+m]['Close'].min(),
                  "green" if l_or_s =='long' else 'red', linestyles='dashed', label=l_or_s)
        plt.legend()
        plt.show()

# 取引可能ペアを2次元配列で返す
def all_inst():
    api = API(access_token=access_token, environment="practice")
    r = accounts.AccountInstruments(accountID=accountID)
    api.request(r)
    inst_l = [d['name'] for d in r.response['instruments']]
    return inst_l

# スプレッド取得
def pip_spread(instrument, print_=False):
    api = API(access_token=access_token, environment="practice")
    pip = 0
    r = accounts.AccountInstruments(accountID=accountID)
    api.request(r)
    for i in r.response['instruments']:
        if i['name'] == instrument:
            pip = 10**i['pipLocation']
    spread = 0
    r = pricing.PricingInfo(accountID=accountID, params={'instruments': instrument})
    api.request(r)
    response = r.response
    spread = float(response['prices'][0]['asks'][0]['price'])-float(response['prices'][0]['bids'][0]['price'])
    spread = round(spread / pip, 1)
    if print_:
        root = instrument.split('_')[1]
        print('{}{} = 1pips, spread: {}pips, {}{}'.format(pip, root, spread, pip*spread, root))
    else:
        return pip, spread, float(Decimal(str(pip))*Decimal(str(spread)))

def get_price(instrument):
    f = True
    f_count = 0
    while f:
        try:
            r = pricing.PricingInfo(accountID=accountID, params={'instruments': instrument})
            rv = api.request(r)
            f = False
        except Exception as e:
            if f_count > 10:
                print(e)
                f = False
            time.sleep(5)
            f_count+=1
            pass
    return {'buy': float(rv['prices'][0]['asks'][0]['price']),
            'sell': float(rv['prices'][0]['bids'][0]['price'])}

def plot_pos(df, pos_df):
    en_l = list(map(str, pos_df['entry_date'].to_list()))
    ex_l = list(map(str, pos_df['exit_date'].to_list()))
    long_i = []
    long_l = []
    short_i = []
    short_l = []
    for i in range(len(df)):
        time = str(df.iat[i, 0])
        # get entry marker
        if time in en_l:
            j = en_l.index(time)
            if pos_df.iat[j, 1] == 'long':
                long_l.extend([pos_df.iat[j, 3]])
                long_i.extend([i])
            else:
                short_l.extend([pos_df.iat[j, 3]])
                short_i.extend([i])
        # get exit marker
        if time in ex_l:
            j = ex_l.index(time)
            if pos_df.iat[j, 1] == 'long':
                short_l.extend([pos_df.iat[j, 5]])
                short_i.extend([i])
            else:
                long_l.extend([pos_df.iat[j, 5]])
                long_i.extend([i])
    fig = create_candlestick(open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'])
    fig.add_scatter(x=long_i, y=long_l, name='long', mode='markers', marker={
        "size": 10,
        "symbol": 'triangle-up',
        'color': '#00e1ff'
    })
    fig.add_scatter(x=short_i, y=short_l, name='short', mode='markers', marker={
        "size": 10,
        "symbol": 'triangle-down',
        'color': '#ffee00'
    })
    fig.show()