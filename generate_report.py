#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日全球股市报告生成器 v3
- 指数：akshare（A股/港股/板块/涨停 + index_global_spot_em 全球指数）
- 商品/美债/VIX/加密：yfinance（GitHub Actions 环境可用），失败自动回退 akshare
- 新闻源：Reuters / CNBC / Yahoo Finance / MarketWatch RSS
- 结构：固定模板（report_template.html）+ LLM 只生成 JSON 文本内容
"""

import os
import re
import sys
import json
import time
import requests
import xml.etree.ElementTree as ET
import akshare as ak
import yfinance as yf
from datetime import datetime
import pytz

# ============ 配置 ============
# 多模型自动切换：按顺序尝试，任一成功即用
LLM_PROVIDERS = [
    {'name': 'qwen3.7-plus', 'model': 'qwen3.7-plus',
     'url': 'https://coding-intl.dashscope.aliyuncs.com/v1/chat/completions',
     'key': os.environ.get('DASHSCOPE_API_KEY', '')},
    {'name': 'glm-4-flash', 'model': 'glm-4-flash',
     'url': 'https://open.bigmodel.cn/api/paas/v4/chat/completions',
     'key': os.environ.get('ZHIPU_API_KEY', '')},
]
LLM_PROVIDERS = [p for p in LLM_PROVIDERS if p['key']]
if not LLM_PROVIDERS:
    print("错误：未设置任何 LLM API KEY（DASHSCOPE_API_KEY / ZHIPU_API_KEY）")
    sys.exit(1)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# 本地调试开关：跳过被限流的 yfinance（GitHub Actions 上不要设置）
SKIP_YF = os.environ.get('SKIP_YF') == '1'


# ============ 日期与格式化 ============
def _now():
    return datetime.now(pytz.timezone('Asia/Shanghai'))

def today_str():
    return _now().strftime('%Y-%m-%d')

def today_short():
    n = _now()
    return f"{n.month}/{n.day}"

def today_display():
    n = _now()
    wd = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
    return f"{n.year}年{n.month}月{n.day}日 {wd[n.weekday()]}"

def fmt_pct(v):
    try:
        v = float(v)
    except Exception:
        return '—'
    return f"+{v:.2f}%" if v > 0 else f"{v:.2f}%"

def num(v, dec=2):
    try:
        return f"{float(v):,.{dec}f}"
    except Exception:
        return str(v)

def cls_of(v):
    try:
        v = float(v)
    except Exception:
        return 'n0'
    return 'r' if v > 0 else ('g' if v < 0 else 'n0')


# ============ 数据抓取 ============
# GitHub Actions 海外环境说明：
# - 东方财富 push2 系接口间歇性可用（时通时断），所有东财/akshare 调用均带重试
# - 新浪行情/行业板块、腾讯外盘 hf_*、yfinance 稳定可用，作为主源或回退
TENCENT_HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
SINA_HEADERS = {'User-Agent': TENCENT_HEADERS['User-Agent'],
                'Referer': 'https://finance.sina.com.cn'}


def _retry(fn, tries=3, delay=1.5, what=''):
    """带重试的调用（东财接口偶发断连），失败返回 None"""
    last = None
    for i in range(tries):
        try:
            r = fn()
            if r is not None and (not hasattr(r, '__len__') or len(r)):
                return r
            last = 'empty'
        except Exception as e:
            last = f'{type(e).__name__}: {e}'
        if i < tries - 1:
            time.sleep(delay)
    print(f"    ⚠ {what or '接口'} 重试{tries}次后失败: {str(last)[:80]}")
    return None


def yf_quote(sym, period='7d'):
    """通用 yfinance 行情：返回 {'v': float, 'c': pct} 或 None"""
    if SKIP_YF:
        return None
    try:
        h = yf.Ticker(sym).history(period=period)
        h = h.dropna()
        if len(h) >= 2:
            last = float(h.iloc[-1]['Close'])
            prev = float(h.iloc[-2]['Close'])
            if prev:
                return {'v': last, 'c': (last - prev) / prev * 100}
    except Exception as e:
        print(f'    yf {sym} 失败: {type(e).__name__}')
    return None


def _yield_bp(q):
    """收益率报价 -> {'v': 收益率, 'c': bp变化}"""
    if not q:
        return None
    v, c = q['v'], q.get('c')
    prev = v / (1 + c / 100) if c not in (None, 0) else v
    return {'v': v, 'c': (v - prev) * 100}


def _em_index(code):
    """东财指数历史日线（稳定可用）：{'v','c'}"""
    def _f():
        d = ak.stock_zh_index_daily(symbol=code).iloc[-2:]
        return {'v': float(d.iloc[-1]['close']),
                'c': (float(d.iloc[-1]['close']) - float(d.iloc[-2]['close'])) / float(d.iloc[-2]['close']) * 100}
    return _retry(_f, what=f'stock_zh_index_daily {code}')


def _sina_quotes(syms):
    """新浪行情 -> {symbol: fields list}"""
    out = {}
    try:
        r = requests.get('https://hq.sinajs.cn/list=' + ','.join(syms),
                         headers=SINA_HEADERS, timeout=10)
        for line in r.text.splitlines():
            line = line.strip()
            if not line.startswith('var hq_str_'):
                continue
            key = line.split('=', 1)[0].replace('var hq_str_', '').strip()
            m = re.search(r'"([^"]*)"', line)
            out[key] = m.group(1).split(',') if m else []
    except Exception as e:
        print(f'    新浪行情失败: {type(e).__name__}')
    return out


def _tencent_hf(code):
    """腾讯外盘行情（hf_XAU 现货黄金 / hf_OIL 布伦特 / hf_CL WTI）：{'v','c'}"""
    try:
        r = requests.get(f'https://qt.gtimg.cn/q={code}', headers=TENCENT_HEADERS, timeout=10)
        m = re.search(r'="([^"]*)"', r.text)
        if not m or not m.group(1):
            return None
        f = m.group(1).split(',')
        return {'v': float(f[0]), 'c': float(f[1])}
    except Exception as e:
        print(f'    腾讯 {code} 失败: {type(e).__name__}')
    return None


def _em_amount(secid, lmt=3):
    """东财 kline 成交额(元) -> {date: amount}"""
    url = (f'https://push2his.eastmoney.com/api/qt/stock/kline/get?secid={secid}'
           f'&fields1=f1,f2&fields2=f51,f53,f57&klt=101&fqt=0&end=20500101&lmt={lmt}')
    r = requests.get(url, headers=TENCENT_HEADERS, timeout=10)
    kl = r.json()['data']['klines']
    return {k.split(',')[0]: float(k.split(',')[2]) for k in kl if k.count(',') >= 2}


def _sina_rank(num=20):
    """新浪A股涨幅榜 -> [{代码,名称,涨跌幅}]"""
    try:
        r = requests.get(
            'https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/'
            f'Market_Center.getHQNodeData?node=hs_a&num={num}&sort=changepercent&asc=0&page=1',
            headers=SINA_HEADERS, timeout=12)
        arr = json.loads(r.text)
        return [{'代码': x['code'], '名称': x['name'], '涨跌幅': float(x['changepercent'])}
                for x in arr if x.get('code')]
    except Exception as e:
        print(f'    新浪涨幅榜失败: {type(e).__name__}')
    return []


def _sina_sectors():
    """新浪行业板块 -> 按涨跌幅降序 [{板块名称,涨跌幅,领涨股,股票数}]"""
    r = requests.get('https://vip.stock.finance.sina.com.cn/q/view/newSinaHy.php',
                     headers=SINA_HEADERS, timeout=12)
    t = r.text
    js = t[t.find('{'):t.rfind('}') + 1]
    d = json.loads(js)
    rows = []
    for _, v in d.items():
        p = v.split(',')
        if len(p) < 13:
            continue
        try:
            rows.append({'板块名称': p[1], '涨跌幅': float(p[5]),
                         '领涨股': p[12], '股票数': int(p[2])})
        except (ValueError, IndexError):
            continue
    return sorted(rows, key=lambda x: x['涨跌幅'], reverse=True)


def fetch_data():
    data = {'fx': {}}
    today = today_str()

    # ---------- 1. A股指数 ----------
    print('抓取A股指数...')
    a_codes = {'sh': 'sh000001', 'sz': 'sz399001', 'cy': 'sz399006', 'kc': 'sh000688'}
    yf_map = {'sh': '000001.SS', 'sz': '399001.SZ'}
    a = {}
    for k, code in a_codes.items():
        q = _em_index(code)
        if not q and k in yf_map:
            q = yf_quote(yf_map[k])
        a[k] = q
    data['a'] = a
    if a.get('sh'):
        line = f"  A股: 沪指{a['sh']['v']:.2f}({a['sh']['c']:+.2f}%)"
        if a.get('cy'):
            line += f" | 创业板{a['cy']['v']:.2f}({a['cy']['c']:+.2f}%)"
        print(line)

    # ---------- 2. 两市统计（statbar：成交/较昨日/涨停/跌停） ----------
    print('抓取两市成交与涨跌停...')
    a_stats = {}
    q = _sina_quotes(['s_sh000001', 's_sz399001'])
    sh_amt = float(q['s_sh000001'][5]) if q.get('s_sh000001') and len(q['s_sh000001']) > 5 else 0
    sz_amt = float(q['s_sz399001'][5]) if q.get('s_sz399001') and len(q['s_sz399001']) > 5 else 0
    total_wan = sh_amt + sz_amt  # 万元
    if total_wan > 0:
        a_stats['volume'] = f'{total_wan / 100000000:.2f}万亿'  # 万元 -> 万亿
    try:
        sh_k = _em_amount('1.000001')
        sz_k = _em_amount('0.399001')
        ks = sorted(set(sh_k) | set(sz_k))
        if ks:
            prev = ks[-2] if (ks[-1] >= today and len(ks) > 1) else ks[-1]
            prev_wan = (sh_k.get(prev, 0) + sz_k.get(prev, 0)) / 1e4  # 元 -> 万元
            if prev_wan > 0:
                a_stats['vs_yesterday'] = f'{(total_wan - prev_wan) / 10000:+.0f}亿'
    except Exception as e:
        print(f'    较昨日成交额失败: {type(e).__name__}')

    dstr = today.replace('-', '')
    zt = _retry(lambda: ak.stock_zt_pool_em(date=dstr), what='涨停池')
    dt = _retry(lambda: ak.stock_zt_pool_dtgc_em(date=dstr), what='跌停池')
    if zt is not None and len(zt):
        a_stats['zt_count'] = len(zt)
        data['a_stocks'] = {'zt_count': len(zt),
                            'zt_top5': zt.head(8)[['代码', '名称', '涨跌幅']].to_dict('records')}
    else:
        rk = _sina_rank(20)
        data['a_stocks'] = {'zt_count': len(rk), 'zt_top5': rk[:8], '_from_rank': True}
    if dt is not None and len(dt):
        a_stats['dt_count'] = len(dt)
    data['a_stats'] = a_stats or None
    print(f"  两市:{a_stats.get('volume', '—')} 较昨:{a_stats.get('vs_yesterday', '—')}"
          f" 涨停:{a_stats.get('zt_count', '—')} 跌停:{a_stats.get('dt_count', '—')}")

    # ---------- 3. A股板块（新浪行业板块主，东财回退） ----------
    print('抓取A股板块...')
    sec = _retry(_sina_sectors, what='新浪行业板块')
    if sec:
        data['a_sectors'] = {'top5': sec[:5], 'bottom5': sec[-5:]}
        print(f"  板块: 第一 {sec[0]['板块名称']} {sec[0]['涨跌幅']:+.2f}%"
              f" | 末位 {sec[-1]['板块名称']} {sec[-1]['涨跌幅']:+.2f}%")
    else:
        sdf = _retry(lambda: ak.stock_board_industry_name_em(), what='行业板块')
        if sdf is not None and len(sdf):
            sdf = sdf.sort_values('涨跌幅', ascending=False)
            data['a_sectors'] = {
                'top5': sdf.head(5)[['板块名称', '涨跌幅']].to_dict('records'),
                'bottom5': sdf.tail(5)[['板块名称', '涨跌幅']].to_dict('records')}

    # ---------- 4. 港股 ----------
    print('抓取港股...')
    hk = {}
    for k, sym in {'hsi': 'HSI', 'hstech': 'HSTECH', 'hscn': 'HSCEI'}.items():
        def _hk(sym=sym):
            d = ak.stock_hk_index_daily_sina(symbol=sym).iloc[-2:]
            return {'v': float(d.iloc[-1]['close']),
                    'c': (float(d.iloc[-1]['close']) - float(d.iloc[-2]['close'])) / float(d.iloc[-2]['close']) * 100}
        hk[k] = _retry(_hk, what=f'港股 {sym}')
    if not hk.get('hsi'):
        hk['hsi'] = yf_quote('^HSI')
    data['hk'] = hk
    if hk.get('hsi'):
        print(f"  港股: 恒指{hk['hsi']['v']:.2f}({hk['hsi']['c']:+.2f}%)")

    # ---------- 5. 全球指数 ----------
    print('抓取全球指数...')
    g = _retry(lambda: ak.index_global_spot_em(), what='全球指数')

    def _g(code):
        try:
            row = g[g['代码'] == code]
            if len(row):
                r = row.iloc[0]
                return {'v': float(r['最新价']), 'c': float(r['涨跌幅'])}
        except Exception:
            pass
        return None

    data['us'] = {'dj': _g('DJIA') or yf_quote('^DJI'),
                  'sp': _g('SPX') or yf_quote('^GSPC'),
                  'nq': _g('NDX') or yf_quote('^IXIC')}
    data['asia'] = {'kospi': _g('KS11') or yf_quote('^KS11'),
                    'n225': _g('N225') or yf_quote('^N225')}
    data['eu'] = {'stoxx': yf_quote('^STOXX'),  # 欧洲斯托克600（东财无600口径，直接用雅虎）
                  'dax': _g('GDAXI') or yf_quote('^GDAXI'),
                  'cac': _g('FCHI') or yf_quote('^FCHI'),
                  'ftse': _g('FTSE') or yf_quote('^FTSE')}
    data['fx']['dxy'] = _g('UDI') or yf_quote('DX-Y.NYB')
    dj = data['us']['dj']
    dxy = data['fx']['dxy']
    print(f"  道指{dj['v'] if dj else '—'} | 美元指数{dxy['v'] if dxy else '—'}"
          f" | 斯托克600{data['eu']['stoxx']['v'] if data['eu']['stoxx'] else '—'}")

    # ---------- 6. 大宗商品 ----------
    print('抓取大宗商品...')
    fg = [None]

    def _em_fut(code):
        if fg[0] is None:
            fg[0] = _retry(lambda: ak.futures_global_spot_em(), what='全球期货')
        try:
            row = fg[0][fg[0]['代码'] == code]
            if len(row):
                r = row.iloc[0]
                return {'v': float(r['最新价']), 'c': float(r['涨跌幅'])}
        except Exception:
            pass
        return None

    gold_spot = _tencent_hf('hf_XAU') or yf_quote('GC=F')  # 伦敦金现货
    if gold_spot:
        gold_spot['~'] = True
    com = {'gold': gold_spot,
           'gold_fut': yf_quote('GC=F') or _em_fut('GC00Y'),
           'silver': yf_quote('SI=F') or _em_fut('SI00Y'),
           'brent': yf_quote('BZ=F') or _tencent_hf('hf_OIL'),
           'wti': yf_quote('CL=F') or _tencent_hf('hf_CL'),
           'copper': yf_quote('HG=F') or _em_fut('HG00Y')}
    data['com'] = com
    if com.get('gold'):
        print(f"  黄金: 现货{com['gold']['v']:.2f}({com['gold']['c']:+.2f}%)")

    # ---------- 7. 汇率 / 美债 / 加密 ----------
    print('抓取汇率债券加密...')

    def _fx_cny():
        fxq = _retry(lambda: ak.fx_spot_quote(), what='汇率')
        if fxq is None:
            return None
        m = fxq['货币对'].astype(str)
        row = fxq[m.str.contains('CNY', na=False) & m.str.contains('USD', na=False)]
        if len(row):
            return {'v': float(row.iloc[0]['买报价']), 'c': None}
        return None

    cny = _fx_cny() or yf_quote('CNY=X')
    if cny:
        cny['c'] = None  # 汇率行只显示点位+注解（与模板一致）
        data['fx']['usdcny'] = cny
    tnx = _yield_bp(yf_quote('^TNX'))
    if tnx:
        data['bond'] = {'us10y': tnx}
    tyx = _yield_bp(yf_quote('^TYX'))
    if tyx:
        data.setdefault('bond', {})['us30y'] = tyx
    btc, eth = yf_quote('BTC-USD'), yf_quote('ETH-USD')
    if btc or eth:
        if btc:
            btc['~'] = True
        if eth:
            eth['~'] = True
        data['crypto'] = {'btc': btc, 'eth': eth}
        if btc:
            print(f"  加密: BTC{btc['v']:.0f}({btc['c']:+.2f}%)")

    got = sum(1 for k in ['a', 'hk', 'us', 'asia', 'eu', 'com', 'fx', 'bond', 'crypto'] if data.get(k))
    print(f'数据抓取完成: {got}/9 个板块')
    return data


def fetch_news():
    """抓取财经新闻标题（RSS，best-effort）"""
    feeds = [
        ('CNBC', 'https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114'),
        ('MarketWatch', 'https://feeds.content.dowjones.io/public/rss/mw_topstories'),
        ('Google News', 'https://news.google.com/rss/search?q=stock%20market%20OR%20wall%20street%20OR%20federal%20reserve%20when%3A1d&hl=en-US&gl=US&ceid=US:en'),
        ('Financial Times', 'https://www.ft.com/rss/home'),
        ('WSJ', 'https://feeds.a.dj.com/rss/RSSMarketsMain.html'),
        ('Reuters', 'https://feeds.reuters.com/reuters/businessNews'),
    ]
    heads = []
    for name, url in feeds:
        try:
            r = requests.get(url, headers=TENCENT_HEADERS, timeout=15)
            root = ET.fromstring(r.content)
            items = root.findall('.//item')
            for it in items[:6]:
                t = it.findtext('title')
                if t:
                    heads.append(f'[{name}] {t.strip()}')
        except Exception as e:
            print(f'  RSS {name} 失败: {type(e).__name__}')
    print(f'  新闻标题: {len(heads)} 条')
    return heads[:36]


# ============ LLM 生成内容 ============
def gen_content(data, news):
    td, ts = today_display(), today_short()
    data_desc = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    news_desc = "\n".join(news) if news else "（无）"

    prompt = f"""你是专业财经分析师。根据以下市场数据与新闻标题，生成一份每日全球股市观察报告的内容。

日期：{td}（{ts}）

【市场数据】
{data_desc}

【今日新闻标题（来自 Reuters/CNBC/Yahoo/MarketWatch）】
{news_desc}

严格按以下 JSON 格式输出（不要任何额外文字、不要 markdown 代码块）：

{{
  "hero_title": "主标题，20字内，用·分隔两个要点，可用<em>和<i>标签强调",
  "hero_sub": "副标题，一句话概括关键数据，用·分隔",
  "summary": "首页归档列表摘要（200-260字）：开头一句最亮眼事件，然后按'周三A股…：沪指-0.88%报3767…成交1.41万亿缩量2600亿，涨停36家跌停10家'格式浓缩全部核心指数点位涨跌幅、成交额、板块主线、2-3条重要消息、美股/港股/商品关键数据，结尾固定加'含9条环球要闻深度解读+五维度全分析+6大产业高频数据+后市展望'；数字必须来自市场数据，不要分点、不要换行",
  "overview_callout": "A股定性总结（200字，含<b>标签，分析市场特点/资金行为/板块轮动）",
  "global_callout": "全球市场总结（320字，含<b>标签，逐一分析亚太/美股/欧股表现、联动关系、风险点）",
  "index_notes": {{"上证指数":"缩量阴跌","深证成指":"","创业板指":"失守3000","科创50":"","恒生指数":"","恒生科技":"","韩国 KOSPI":"外资砸盘","日经225":"","道琼斯":"","标普500":"逼近新高","纳斯达克":"","欧洲斯托克600":"","德国 DAX":"领涨","法国 CAC40":"","英国 富时100":""}},
  "com_notes": {{"现货黄金":"续创新高","COMEX黄金期货":"","COMEX白银期货":"","布伦特原油":"微跌","WTI原油":"","COMEX铜":"","美元/人民币":"汇率企稳","美元指数":"","10年期美债收益率":"高位","30年期美债收益率":"","比特币":"","以太坊":""}},
  "news": [{{"level":"a","sources":["Reuters","财联社"],"title":"标题30字内，包含关键数据和影响","body":"正文100字，可用<span class=\\"num\\">等标签","impact_title":"说人话：","impact_body":"影响分析80字"}}],
  "five_dims": [{{"name":"消息面","score":"利空主导 ★★☆☆☆","points":["要点1（50字）","要点2","要点3","要点4","结论（50字）"]}}],
  "heat": [{{"name":"板块名","dir":"up","w":95,"label":"说明10字内"}}],
  "heat_callout": "热力图总结（150字，分析板块轮动逻辑）",
  "stocks": [{{"name":"股票名","tag":"lim","tag_text":"标签","desc":"说明","cv_color":"r"}}],
  "stocks_callout": "个股总结（150字，分析资金流向）",
  "commodity_callout": "大宗商品与汇率总结（220字，逐一分析各品种走势和逻辑）",
  "industries": [{{"icon":"🛢","name":"产业名","status":"hot","status_text":"状态4字","points":["要点1（50字）","要点2","要点3","要点4","要点5"],"sources":"信源列表"}}],
  "industry_callout": "产业总结（200字，分析产业链动态）",
  "strategy": ["短期判断（80字）","中期判断（80字）","长期判断（80字）","风险点（80字）"],
  "dirs": [{{"text":"方向名","cool":false}}],
  "risks": ["风险1（50字）","风险2","风险3","风险4","风险5","风险6"]
}}

要求：
1. news: 9条（4条a级极重要 + 3条b级重要 + 2条c级关注），sources 中至少含1个国际源（Reuters/Bloomberg/WSJ/FT/CNBC），基于上面新闻标题，每条都有深度分析
2. five_dims: 5个维度（消息面/情绪面/技术面/政策面/资金面），每个5个points
3. heat: 10个板块（5涨5跌），基于 a_sectors 数据，dir为up或down，w为10-95
4. stocks: 16只个股（A股8 + 港股4 + 美股4），基于 a_stocks 数据，tag为 lim/taga/tagi/limg 之一，cv_color为 r 或 g
5. industries: 6个产业卡片（原油/能源、锂矿/能源金属、半导体/存储、传媒/AI应用、银行/高股息、贵金属），status 为 hot/warm/cool
6. strategy: 4条（短期/中期/长期/风险）；dirs: 10个方向（部分 cool:true 表示回避）；risks: 6条
7. index_notes / com_notes：为每个指数/品种填一句 6字内的定性后缀（无补充则留空字符串）
8. 语言风格：犀利客观、可以带讽刺、不要套话，用"说人话"的方式解读
9. 所有数字必须来自我提供的市场数据，不得编造
10. 直接输出 JSON，不要 ```json 标记

请生成："""

    for prov in LLM_PROVIDERS:
        for attempt in range(3):
            try:
                print(f"调用 LLM 生成报告内容（{prov['name']}，第{attempt + 1}次）...")
                resp = requests.post(
                    prov['url'],
                    headers={'Content-Type': 'application/json', 'Authorization': f"Bearer {prov['key']}"},
                    json={'model': prov['model'], 'messages': [{'role': 'user', 'content': prompt}],
                          'temperature': 0.7, 'max_tokens': 8000},
                    timeout=300)
                resp.raise_for_status()
                raw = resp.json()['choices'][0]['message']['content'].strip()
                if raw.startswith('```'):
                    raw = raw[raw.find('\n') + 1:]
                if raw.endswith('```'):
                    raw = raw[:-3]
                content = json.loads(raw.strip())
                print(f"✅ LLM 生成成功（{prov['name']}）")
                return content
            except Exception as e:
                print(f"  ⚠ {prov['name']} 第{attempt + 1}次失败: {type(e).__name__}: {str(e)[:160]}")
                import time as _t
                _t.sleep(5)
    print("❌ 所有 LLM 均失败")
    return None


# ============ HTML 构建 ============
def _row(label, q, note='', unit='', prefix='', dec=2, mode='pct'):
    """生成一行行情表格"""
    if not q:
        return f'<tr><td class="name">{label}</td><td>—</td><td class="n0">暂无数据</td></tr>\n'
    apref = '~' if (prefix or q.get('~')) else ''
    val = f"{apref}{num(q['v'], dec)}{(' ' + unit) if unit else ''}"
    c = q.get('c')
    if c is None:
        return f'<tr><td class="name">{label}</td><td>{val}</td><td class="n0">{note or "—"}</td></tr>\n'
    if mode == 'bp':  # 收益率：涨跌列显示 bp
        cls = cls_of(c)
        return (f'<tr><td class="name">{label}</td><td>{val}</td>'
                f'<td class="{cls}">{c:+.2f}bp{(" " + note) if note else ""}</td></tr>\n')
    hot = 'hot' if abs(c) >= 1.5 else ''
    cls = cls_of(c)
    tail = f' {note}' if note else ''
    return (f'<tr class="{hot}"><td class="name">{label}</td><td>{val}</td>'
            f'<td class="{cls}">{fmt_pct(c)}{tail}</td></tr>\n')


def build_html(c, data):
    td, ts = today_display(), today_short()
    a = data.get('a') or {}
    hk = data.get('hk') or {}
    us = data.get('us') or {}
    asia = data.get('asia') or {}
    eu = data.get('eu') or {}
    com = data.get('com') or {}
    fx = data.get('fx') or {}
    bond = data.get('bond') or {}
    vix = data.get('vix')
    crypto = data.get('crypto') or {}
    inote = c.get('index_notes', {}) or {}
    cnote = c.get('com_notes', {}) or {}

    hero = f'''  <div class="hero">
    <div class="hero-inner">
      <div class="kicker">DAILY GLOBAL MARKET WATCH</div>
      <h1>{c['hero_title']}</h1>
      <div class="sub">{c['hero_sub']}</div>
      <div class="datebar">
        <span>{td} · 收盘全维度分析</span>
        <span class="pulse"><span class="dot"></span> LIVE</span>
      </div>
    </div>
  </div>'''

    nav = '''  <div class="sec-nav">
    <span class="sec-nav-label">快速跳转：</span>
    <a href="#sec-overview">📈 A股速览</a>
    <a href="#sec-global">🌍 全球市场</a>
    <a href="#sec-news">📰 环球要闻</a>
    <a href="#sec-five">🔍 五维分析</a>
    <a href="#sec-heat">🔥 板块热力</a>
    <a href="#sec-stock">💰 焦点个股</a>
    <a href="#sec-commodity">🛢️ 大宗商品</a>
    <a href="#sec-grassroots">🏭 产业高频</a>
    <a href="#sec-strategy">🎯 策略研判</a>
  </div>'''

    def idx_card(name, q):
        if not q:
            return f'<div class="idx n0"><div class="n">{name}</div><div class="v">—</div><div class="c">暂无数据</div></div>'
        return (f'<div class="idx {cls_of(q["c"])}"><div class="n">{name}</div>'
                f'<div class="v">{num(q["v"])}</div><div class="c">{fmt_pct(q["c"])}</div></div>')

    a_stats = data.get('a_stats') or {}

    # 构建 statbar 统计栏（两市成交 / 较昨日 / 涨停家数 / 跌停家数，与模板一致）
    statbar_html = ''
    if a_stats.get('volume'):
        vs = a_stats.get('vs_yesterday', '—')
        vs_cls = 'g' if vs.startswith('-') else ('r' if vs.startswith('+') else 'n0')
        statbar_html = f'''<div class="statbar">
      <div class="stat"><div class="k">两市成交</div><div class="v n0">{a_stats.get('volume', '-')}</div></div>
      <div class="stat"><div class="k">较昨日</div><div class="v {vs_cls}">{vs}</div></div>
      <div class="stat"><div class="k">涨停家数</div><div class="v r">{a_stats.get('zt_count', '-')}</div></div>
      <div class="stat"><div class="k">跌停家数</div><div class="v g">{a_stats.get('dt_count', '-')}</div></div>
    </div>'''
    
    overview = f'''  <div class="sec" id="sec-overview">
    <div class="sec-head">
      <div class="sec-ico" style="background:#ffe4e6">📈</div>
      <div class="sec-title">A股收盘速览</div>
      <div class="sec-note">{ts} 15:00 收盘</div>
    </div>
    <div class="idx-grid">
      {idx_card('上证指数', a.get('sh'))}
      {idx_card('深证成指', a.get('sz'))}
      {idx_card('创业板指', a.get('cy'))}
      {idx_card('科创50', a.get('kc'))}
    </div>
    {statbar_html}
    <div class="callout">
      {c['overview_callout']}
    </div>
  </div>'''

    apac_rows = (
        _row('上证指数', a.get('sh'), inote.get('上证指数', '')) +
        _row('深证成指', a.get('sz'), inote.get('深证成指', '')) +
        _row('创业板指', a.get('cy'), inote.get('创业板指', '')) +
        _row('科创50', a.get('kc'), inote.get('科创50', '')) +
        _row('恒生指数', hk.get('hsi'), inote.get('恒生指数', '')) +
        _row('恒生科技', hk.get('hstech'), inote.get('恒生科技', '')) +
        _row('韩国 KOSPI', asia.get('kospi'), inote.get('韩国 KOSPI', '')) +
        _row('日经225', asia.get('n225'), inote.get('日经225', ''))
    )
    us_rows = (
        _row('道琼斯', us.get('dj'), inote.get('道琼斯', '')) +
        _row('标普500', us.get('sp'), inote.get('标普500', '')) +
        _row('纳斯达克', us.get('nq'), inote.get('纳斯达克', ''))
    )
    eu_rows = (
        _row('欧洲斯托克600', eu.get('stoxx'), inote.get('欧洲斯托克600', '')) +
        _row('德国 DAX', eu.get('dax'), inote.get('德国 DAX', '')) +
        _row('法国 CAC40', eu.get('cac'), inote.get('法国 CAC40', '')) +
        _row('英国 富时100', eu.get('ftse'), inote.get('英国 富时100', ''))
    )

    global_sec = f'''  <div class="sec" id="sec-global">
    <div class="sec-head">
      <div class="sec-ico" style="background:#e2ecfd">🌏</div>
      <div class="sec-title">全球市场全景</div>
      <div class="sec-note">数据截至 {ts} 15:30</div>
    </div>
    <div class="mkt-legend">
      <span><span class="dot close"></span><b>收盘</b>：A股/港股/亚太 {ts}</span>
      <span><span class="dot ovn"></span><b>昨夜</b>：美股/欧股 最近收盘</span>
    </div>
    <table class="tbl">
      <thead><tr><th>市场 / 指数</th><th>点位</th><th>涨跌</th></tr></thead>
      <tbody>
        <tr class="grp"><td colspan="3">亚太 <span class="st close">{ts} 收盘</span></td></tr>
        {apac_rows}        <tr class="grp"><td colspan="3">美股 <span class="st ovn">最近收盘</span></td></tr>
        {us_rows}        <tr class="grp"><td colspan="3">欧股 <span class="st ovn">最近收盘</span></td></tr>
        {eu_rows}      </tbody>
    </table>
    <div class="callout blue">
      {c['global_callout']}
    </div>
  </div>'''

    news_items = ''
    intl = ["Reuters", "Bloomberg", "WSJ", "FT", "CNBC", "Yahoo Finance", "MarketWatch", "Invezz"]
    for n in c.get('news', []):
        srcs = ''.join(f'<span class="src{" intl" if s in intl else ""}">{s}</span>' for s in n.get('sources', []))
        tag_text = {'a': '🔴 极重要', 'b': '🟠 重要', 'c': '🔵 关注'}.get(n.get('level', 'c'), '🔵 关注')
        news_items += f'''    <div class="news {n.get('level', 'c')}">
      <div class="news-top">
        <span class="tag">{tag_text}</span>
        {srcs}
      </div>
      <h3>{n.get('title', '')}</h3>
      <p>{n.get('body', '')}</p>
      <div class="impact">
        <b>{n.get('impact_title', '说人话：')}</b>{n.get('impact_body', '')}
      </div>
    </div>
'''
    news_sec = f'''  <div class="sec" id="sec-news">
    <div class="sec-head">
      <div class="sec-ico" style="background:#fff0e0">📰</div>
      <div class="sec-title">环球要闻 · 深度解读</div>
      <div class="sec-note">{len(c.get('news', []))}条核心新闻</div>
    </div>
    <div class="news-legend">
      <span class="tag mini a">🔴 极重要</span>
      <span class="tag mini b">🟠 重要</span>
      <span class="tag mini c">🔵 关注</span>
    </div>
{news_items}  </div>'''

    dim_icons = ['📰', '🔥', '📊', '🏛', '💰']
    dim_cls = ['d1', 'd2', 'd3', 'd4', 'd5']
    dims = ''
    for i, dm in enumerate(c.get('five_dims', [])[:5]):
        pts = ''.join(f'<li>{p}</li>' for p in dm.get('points', []))
        dims += f'''    <div class="dim {dim_cls[i]}">
      <div class="dim-h"><span class="e">{dim_icons[i]}</span><span class="t">{dm.get('name', '')}</span><span class="score">{dm.get('score', '')}</span></div>
      <ul>{pts}</ul>
    </div>
'''
    five_sec = f'''  <div class="sec" id="sec-five">
    <div class="sec-head">
      <div class="sec-ico" style="background:#ede9fe">🎯</div>
      <div class="sec-title">五维度深度拆解</div>
      <div class="sec-note">消息 / 情绪 / 技术 / 政策 / 资金</div>
    </div>
{dims}  </div>'''

    heat_rows = ''
    for h in c.get('heat', []):
        fc = 'up' if h.get('dir') == 'up' else 'down'
        vc = 'r' if h.get('dir') == 'up' else 'g'
        heat_rows += (f'    <div class="heat"><div class="heat-row"><div class="heat-name">{h.get("name", "")}</div>'
                      f'<div class="heat-track"><div class="heat-fill {fc}" style="width:{h.get("w", 50)}%"></div></div>'
                      f'<div class="heat-val {vc}">{h.get("label", "")}</div></div></div>\n')
    heat_sec = f'''  <div class="sec" id="sec-heat">
    <div class="sec-head">
      <div class="sec-ico" style="background:#fff0e0">🔥</div>
      <div class="sec-title">板块热力图</div>
      <div class="sec-note">红涨绿跌</div>
    </div>
{heat_rows}    <div class="callout">
      {c.get('heat_callout', '')}
    </div>
  </div>'''

    chips = ''
    for s in c.get('stocks', []):
        chips += (f'      <div class="chip"><span class="cn">{s.get("name", "")}</span>'
                  f'<span class="{s.get("tag", "taga")}">{s.get("tag_text", "")}</span>'
                  f'<span class="cv {s.get("cv_color", "r")}">{s.get("desc", "")}</span></div>\n')
    stock_sec = f'''  <div class="sec" id="sec-stock">
    <div class="sec-head">
      <div class="sec-ico" style="background:#e2ecfd">⭐</div>
      <div class="sec-title">焦点个股与资金流</div>
      <div class="sec-note">A股 + 港股 + 海外</div>
    </div>
    <div class="chips">
{chips}    </div>
    <div class="callout blue">
      {c.get('stocks_callout', '')}
    </div>
  </div>'''

    com_rows = (
        _row('现货黄金', com.get('gold'), cnote.get('现货黄金', ''), '美元/盎司', '~') +
        _row('COMEX黄金期货', com.get('gold_fut'), cnote.get('COMEX黄金期货', ''), '美元/盎司') +
        _row('COMEX白银期货', com.get('silver'), cnote.get('COMEX白银期货', ''), '美元/盎司') +
        _row('布伦特原油', com.get('brent'), cnote.get('布伦特原油', ''), '美元/桶') +
        _row('WTI原油', com.get('wti'), cnote.get('WTI原油', ''), '美元/桶') +
        _row('COMEX铜', com.get('copper'), cnote.get('COMEX铜', ''), '美元/磅')
    )
    fxb_rows = (
        _row('美元/人民币', fx.get('usdcny'), cnote.get('美元/人民币', ''), '', '', 4) +
        _row('美元指数', fx.get('dxy'), cnote.get('美元指数', '')) +
        _row('10年期美债收益率', bond.get('us10y'), cnote.get('10年期美债收益率', ''), '%', '', 3, 'bp') +
        _row('30年期美债收益率', bond.get('us30y'), cnote.get('30年期美债收益率', ''), '%', '', 3, 'bp')
    )
    crypto_rows = (
        _row('比特币', crypto.get('btc'), cnote.get('比特币', ''), '美元', '~', 0) +
        _row('以太坊', crypto.get('eth'), cnote.get('以太坊', ''), '美元', '~', 0)
    )
    commodity_sec = f'''  <div class="sec" id="sec-commodity">
    <div class="sec-head">
      <div class="sec-ico" style="background:#fef3c7">🪙</div>
      <div class="sec-title">大宗商品与汇率</div>
      <div class="sec-note">{ts} 数据</div>
    </div>
    <table class="tbl">
      <thead><tr><th>品种</th><th>最新</th><th>涨跌</th></tr></thead>
      <tbody>
        {com_rows}        <tr class="grp"><td colspan="3">汇率与利率</td></tr>
        {fxb_rows}        <tr class="grp"><td colspan="3">数字资产</td></tr>
        {crypto_rows}      </tbody>
    </table>
    <div class="callout">
      {c.get('commodity_callout', '')}
    </div>
  </div>'''

    ind_cards = ''
    for ind in c.get('industries', []):
        pts = ''.join(f'<li>{p}</li>' for p in ind.get('points', []))
        ind_cards += f'''      <div class="gf-card {ind.get('status', 'warm')}">
        <div class="gf-top">
          <span class="gf-ico">{ind.get('icon', '')}</span>
          <span class="gf-name">{ind.get('name', '')}</span>
          <span class="gf-status {ind.get('status', 'warm')}">{ind.get('status_text', '')}</span>
        </div>
        <ul>{pts}</ul>
        <div class="gf-src">信源: {ind.get('sources', '')}</div>
      </div>
'''
    industry_sec = f'''  <div class="sec" id="sec-grassroots">
    <div class="sec-head">
      <div class="sec-ico" style="background:#f3fbf6">🔬</div>
      <div class="sec-title">产业高频数据 · 机构/大户必读</div>
      <div class="sec-note">产业链一线追踪</div>
    </div>
    <div class="gf-grid">
{ind_cards}    </div>
    <div class="callout blue">
      {c.get('industry_callout', '')}
    </div>
  </div>'''

    strat_pts = ''.join(f'<li>{p}</li>' for p in c.get('strategy', []))
    dirs = ''.join(f'<span class="dir{" cool" if d.get("cool") else ""}">{d.get("text", "")}</span>' for d in c.get('dirs', []))
    risk_items = ''.join(f'<li>{r}</li>' for r in c.get('risks', []))
    strategy_sec = f'''  <div class="sec" id="sec-strategy">
    <div class="sec-head">
      <div class="sec-ico" style="background:#ffe4e6">🧭</div>
      <div class="sec-title">后市展望与操作策略</div>
    </div>
    <div class="strat">
      <div class="strat-in">
        <h4>🧭 核心判断</h4>
        <ul>{strat_pts}</ul>
        <div class="dirs">{dirs}</div>
      </div>
    </div>
    <div class="risk">
      <h4>⚠ 风险清单（按紧迫度排序）</h4>
      <ul>{risk_items}</ul>
    </div>
  </div>'''

    footer = f'''  <div class="foot">
    <div class="bk">每日全球股市观察</div>
    数据来源：路透社(Reuters) · 华尔街日报(WSJ) · 彭博(Bloomberg) · CNBC · 金融时报(FT) · Yahoo Finance · MarketWatch · 新华社 · 财联社 · 证券时报<br>
    报告时间：{td} 15:30（北京时间）<br><br>
    本报告基于公开信息整理，仅供研究参考，<b style="color:rgba(255,255,255,.6)">不构成任何投资建议</b>。<br>
    市场有风险，投资需谨慎。据此操作，风险自担。
  </div>'''

    tpl_path = os.path.join(SCRIPT_DIR, 'report_template.html')
    with open(tpl_path, 'r', encoding='utf-8') as f:
        tpl = f.read()
    head_end = tpl.find('</head>') + len('</head>')
    head_part = tpl[:head_end]
    wrap_start = tpl.find('<div class="wrap">')
    body_start = tpl.find('<body>')
    wrap_open = tpl[body_start:wrap_start + len('<div class="wrap">')]
    body_end = tpl.find('</body>')
    wrap_close = tpl[tpl.rfind('</div>', 0, body_end):body_end] + '\n</body>\n</html>'

    html = head_part + '\n' + wrap_open + '\n\n'
    html += hero + '\n\n' + nav + '\n\n'
    html += overview + '\n\n' + global_sec + '\n\n' + news_sec + '\n\n'
    html += five_sec + '\n\n' + heat_sec + '\n\n' + stock_sec + '\n\n'
    html += commodity_sec + '\n\n' + industry_sec + '\n\n' + strategy_sec + '\n\n'
    html += footer + '\n\n' + wrap_close
    return html


# ============ 首页归档列表更新 ============
def update_index(html_summary):
    """把当日报告插入 index.html 归档时间线最顶部（同日则替换）"""
    index_file = os.path.join(SCRIPT_DIR, 'index.html')
    if not os.path.exists(index_file):
        return
    with open(index_file, 'r', encoding='utf-8') as f:
        content = f.read()
    ts = today_str()
    n = _now()
    wd = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][n.weekday()]

    # 移除旧的 NEW 徽标（只保留最新一条）
    content = re.sub(r'\s*<span class="new-pill">NEW</span>', '', content)

    item = f'''<a class="report-item" href="archive/{ts}.html">
        <div class="ri-top">
          <span class="date-badge">{ts}</span>
          <span class="weekday">{wd}</span>
          <span class="new-pill">NEW</span>
          <span class="arrow-small">›</span>
        </div>
        <div class="summary">{html_summary}</div>
      </a>'''

    # 同日已存在则先删除旧条目
    content = re.sub(rf'<a class="report-item" href="archive/{re.escape(ts)}\.html">.*?</a>\s*\n', '', content, flags=re.S)

    marker = '<!-- 新报告插入到这里最前面 -->'
    if marker in content:
        content = content.replace(marker, marker + '\n      ' + item, 1)
    else:  # 兜底：插到 report-list 容器后
        content = re.sub(r'(<div class="report-list"[^>]*>)', r'\1\n      ' + item, content, count=1)
    with open(index_file, 'w', encoding='utf-8') as f:
        f.write(content)
    print('✅ index.html 归档列表已更新')


# ============ 主流程 ============
def main():
    print("=" * 60)
    print("每日全球股市报告生成器 v4")
    print("=" * 60)
    data = fetch_data()
    if not data or not data.get('a'):
        print("错误: 无法获取市场数据")
        sys.exit(1)
    news = fetch_news()
    content = gen_content(data, news)
    if not content:
        print("错误: 无法生成内容")
        sys.exit(1)
    html = build_html(content, data)
    ts = today_str()
    out = os.path.join(SCRIPT_DIR, 'latest.html')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)
    arch = os.path.join(SCRIPT_DIR, 'archive')
    os.makedirs(arch, exist_ok=True)
    with open(os.path.join(arch, f'{ts}.html'), 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"✅ 报告已保存: {out}")
    print(f"✅ 归档: {os.path.join(arch, f'{ts}.html')}")
    update_index(content.get('summary') or content.get('hero_sub') or '')
    print("=" * 60)


if __name__ == '__main__':
    main()
