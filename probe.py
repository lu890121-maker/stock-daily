#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""端点探测脚本：测试 GitHub Actions 海外 runner 对各数据源的访问情况"""
import json
import sys
import traceback
import xml.etree.ElementTree as ET

import requests

UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 'Referer': 'https://finance.sina.com.cn'}


def hr(title):
    print('\n' + '=' * 12 + ' ' + title + ' ' + '=' * 12)


# ---------- 1. akshare ----------
hr('akshare')
import akshare as ak

ak_tests = [
    ('stock_zh_index_daily', lambda: ak.stock_zh_index_daily(symbol='sh000001')),
    ('stock_hk_index_daily_sina', lambda: ak.stock_hk_index_daily_sina(symbol='HSI')),
    ('stock_board_industry_name_em', lambda: ak.stock_board_industry_name_em()),
    ('stock_zt_pool_em', lambda: ak.stock_zt_pool_em(date='20261014')),
    ('index_global_spot_em', lambda: ak.index_global_spot_em()),
    ('futures_global_spot_em', lambda: ak.futures_global_spot_em()),
    ('fx_spot_quote', lambda: ak.fx_spot_quote()),
    ('stock_zh_a_hist', lambda: ak.stock_zh_a_hist(symbol='600519', period='daily', start_date='20260930', end_date='20261014', adjust='qfq')),
    ('stock_zh_a_spot_em', lambda: ak.stock_zh_a_spot_em()),
]
for name, fn in ak_tests:
    try:
        df = fn()
        if df is None or len(df) == 0:
            print(f'[FAIL-EMPTY] {name}')
            continue
        cols = list(df.columns)
        print(f'[OK] {name}: rows={len(df)} cols={cols[:10]}')
        if '涨跌幅' in cols:
            print('   sample:', df.iloc[0][df.columns[:4]].to_dict())
    except Exception as e:
        print(f'[FAIL] {name}: {type(e).__name__}: {str(e)[:120]}')

# ---------- 2. yfinance ----------
hr('yfinance')
import yfinance as yf

yf_syms = ['000001.SS', '399001.SZ', '399006.SZ', '000688.SS',
           '^HSI', '^HSTECH', '^N225', '^KS11', '^TWII', '^AXJO', '^STI',
           '^GSPC', '^IXIC', '^DJI', '^STOXX50E', '^STOXX', '^GDAXI', '^FCHI', '^FTSE',
           'GC=F', 'SI=F', 'CL=F', 'BZ=F', 'HG=F', 'NG=F',
           'CNY=X', 'EURUSD=X', 'GBPUSD=X', 'USDJPY=X', 'DX-Y.NYB',
           '^TNX', '^TYX', '^VIX', 'BTC-USD', 'ETH-USD']
if len(sys.argv) > 1 and sys.argv[1] == 'yf-only':
    yf_syms = yf_syms[:10]
for sym in yf_syms:
    try:
        h = yf.Ticker(sym).history(period='7d').dropna()
        if len(h) >= 2:
            last, prev = float(h.iloc[-1]['Close']), float(h.iloc[-2]['Close'])
            c = (last - prev) / prev * 100 if prev else 0
            print(f'[OK] {sym}: {last:.4f} ({c:+.2f}%) n={len(h)} last_date={h.index[-1].date()}')
        else:
            print(f'[FAIL-EMPTY] {sym}: n={len(h)}')
    except Exception as e:
        print(f'[FAIL] {sym}: {type(e).__name__}: {str(e)[:100]}')

# ---------- 3. 直连 HTTP ----------
hr('http direct')

# 3.1 腾讯行情
for url in ['http://qt.gtimg.cn/q=sh000001,s_sh000001,s_sz399001,s_sh000300']:
    try:
        r = requests.get(url, headers=UA, timeout=10)
        print(f'[OK] tencent {url} -> {r.text[:400]}')
    except Exception as e:
        print(f'[FAIL] tencent {url}: {type(e).__name__}: {str(e)[:100]}')

# 3.2 新浪行情
for url in ['https://hq.sinajs.cn/list=s_sh000001,s_sz399001,s_sh000300']:
    try:
        r = requests.get(url, headers=UA, timeout=10)
        print(f'[OK] sina {url} -> {r.text[:400]}')
    except Exception as e:
        print(f'[FAIL] sina {url}: {type(e).__name__}: {str(e)[:100]}')

# 3.3 新浪排行（涨幅榜 -> 涨停池/上涨家数近似）
for url in [
    'https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?node=hs_a&num=10&sort=changepercent&asc=0&page=1',
    'https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeStockCount?node=hs_a',
]:
    try:
        r = requests.get(url, headers=UA, timeout=10)
        print(f'[OK] sina-rank -> {r.text[:600]}')
    except Exception as e:
        print(f'[FAIL] sina-rank {url[:60]}: {type(e).__name__}: {str(e)[:100]}')

# 3.4 新浪行业板块
for url in ['https://vip.stock.finance.sina.com.cn/q/view/newSinaHy.php']:
    try:
        r = requests.get(url, headers=UA, timeout=10)
        txt = r.text
        print(f'[OK] sina-hy len={len(txt)} -> {txt[:300]}')
    except Exception as e:
        print(f'[FAIL] sina-hy: {type(e).__name__}: {str(e)[:100]}')

# 3.5 东财直连（push2his 已知可用，push2/push2delay 探测）
for name, url in [
    ('push2his', 'https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=1.000001&fields1=f1,f2&fields2=f51,f53&klt=101&fqt=0&end=20500101&lmt=5'),
    ('push2', 'https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&secids=1.000001,0.399001&fields=f12,f14,f2,f3'),
    ('push2delay', 'https://push2delay.eastmoney.com/api/qt/ulist.np/get?fltt=2&secids=1.000001,0.399001&fields=f12,f14,f2,f3'),
]:
    try:
        r = requests.get(url, headers={'User-Agent': UA['User-Agent']}, timeout=10)
        print(f'[OK] {name} -> {r.text[:200]}')
    except Exception as e:
        print(f'[FAIL] {name}: {type(e).__name__}: {str(e)[:100]}')

# 3.6 RSS 新闻源
for name, url in [
    ('Reuters', 'https://feeds.reuters.com/reuters/businessNews'),
    ('YahooFinance', 'https://finance.yahoo.com/news/rssindex'),
    ('CNBC', 'https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114'),
    ('MarketWatch', 'https://feeds.content.dowjones.io/public/rss/mw_topstories'),
]:
    try:
        r = requests.get(url, headers=UA, timeout=15)
        root = ET.fromstring(r.content)
        items = root.findall('.//item')
        print(f'[OK] RSS {name}: {len(items)} items, first={items[0].findtext("title")[:60] if items else "-"}')
    except Exception as e:
        print(f'[FAIL] RSS {name}: {type(e).__name__}: {str(e)[:100]}')

hr('DONE')
