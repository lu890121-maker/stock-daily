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
  "hero_title": "主标题，40字内，包含4个核心数据点，用<em>和<i>标签强调关键数据。格式示例：'沪指-1.59%险守3700 · <em>创业板-2.92%逼近2800</em> · <i>成交1.63万亿放量2186亿</i> · 5105股下跌'",
  "hero_sub": "副标题，一句话概括关键数据，用·分隔。格式：'沪指-1.59%深成指-2.43% · 成交1.63万亿放量2186亿 · 5105股下跌 · 布油106美元 · 黄金4127美元 · 美债5.19%'",
  "summary": "首页归档列表摘要（300-400字）：开头一句最亮眼事件，然后按'周四A股…：沪指-1.59%报3707…成交1.63万亿放量2186亿，5105股下跌仅425涨'格式浓缩全部核心指数点位涨跌幅（精确到小数点）、成交额、板块主线、3-4条重要消息、美股/港股/商品关键数据，结尾固定加'含9条环球要闻深度解读+五维度全分析+6大产业高频数据+策略研判'；数字必须来自市场数据，不要分点、不要换行",
  "overview_callout": "A股定性总结（250字，含<b>标签，分析市场特点/资金行为/板块轮动。要求：1）指出成交放量/缩量具体数字 2）分析涨跌家数对比 3）点评主线板块逻辑 4）用'说人话'方式犀利点评，可以带讽刺。示例：'<b>今日定性：放量杀跌 · 5100股尽墨 · 红利防御独撑 · PCB逆势抱团。</b> 周四A股全天震荡下行，<b>三大指数齐跌</b>，沪指-1.59%险守3700点…成交1.63万亿放量2186亿——<b>不是抄底，是跑路</b>。'",
  "global_callout": "全球市场总结（400字，含<b>标签，逐一分析亚太/美股/欧股表现、联动关系、风险点。要求：1）每个市场都要点评 2）用全球视角对比 3）客观评价A股表现 4）可以批评。示例：'<b>全球图景：亚洲黑色星期四+美国CPI核弹+台积电财报的冰火两重天。</b> <b>韩国最惨</b>：KOSPI暴跌7.56%触发两次熔断…<b>日本跟跌</b>：日经暴跌4.90%…<b>A股跟随但跌幅相对小</b>：沪指-1.59%比日韩温和得多，但5105股下跌=全市场屠杀。'",
  "index_notes": {{"上证指数":"放量杀跌","深证成指":"跌破12000","创业板指":"逼近2800","科创50":"相对抗跌","恒生指数":"科技拖累","恒生科技":"创本轮新低","韩国 KOSPI":"触发熔断！","日经225":"半年最大跌幅","道琼斯":"小幅回调","标普500":"CPI冲击","纳斯达克":"芯片六连跌","欧洲斯托克600":"逆势收涨","德国 DAX":"逆势收涨","法国 CAC40":"","英国 富时100":"领涨"}},
  "com_notes": {{"现货黄金":"CPI后承压","COMEX黄金期货":"","COMEX白银期货":"暴跌","布伦特原油":"胡塞袭击推升","WTI原油":"地缘溢价","COMEX铜":"跟跌","美元/人民币":"央行维稳","美元指数":"CPI后走强","10年期美债收益率":"高位","30年期美债收益率":"","比特币":"","以太坊":""}},
  "news": [{{"level":"a","sources":["Reuters","Bloomberg","财联社"],"title":"标题40字内，包含关键数据和影响，格式：'美国9月CPI超预期——同比3.7%核心2.6%双超预期，美联储10月加息概率飙升至44%'","body":"正文150字，可用<span class=\\"num\\">等标签，详细描述事件+数据+影响。示例：'美国劳工统计局10月14日公布9月CPI数据：<b>环比+0.6%（4月以来最快）</b>，<b>同比+3.7%</b>高于预期3.6%；核心CPI环比+0.3%，<b>同比+2.6%</b>高于预期2.5%。<span class=\\"hl\\">汽油价格环比飙升9.1%贡献过半涨幅</span>，能源成本正向核心商品服务传导。'","impact_title":"说人话：","impact_body":"影响分析120字，犀利点评事件影响和逻辑，可以带讽刺。示例：'<b>说人话：</b>这份CPI是一颗"核弹"。汽油环比涨9.1%——中东冲突推高油价→美国通胀反弹→美联储可能加息→全球流动性收紧→风险资产杀跌。<b>传导链条清晰得可怕</b>。更关键的是核心CPI也超预期（2.6% vs 预期2.5%），说明通胀压力不只在能源——服务通胀黏性依旧。'"}}],
  "five_dims": [{{"name":"消息面","score":"利空核弹 ★☆☆☆☆","points":["<b>最大利空（美国CPI超预期）：</b>9月CPI同比3.7%核心2.6%双超预期，汽油环比+9.1%。美联储10月加息概率从32%飙升至44%。这是今天亚洲崩盘的直接导火索。","<b>利空（长鑫4F²技术突破）：</b>中国存储芯片技术突破→韩国三星/海力士垄断逻辑被打破→KOSPI-7.56%熔断→日经-4.90%跟跌→全球半导体重定价。","<b>利空（联想暴跌14%）：</b>PC出货疲软+企业级AI落地担忧+美股AI服务器戴尔-11%传导→港股AI硬件板块全线杀跌→恒生科技-2.72%创本轮新低。","<b>利空（中东地缘升级）：</b>胡塞袭击沙特阿美总部+霍尔木兹海峡12艘商船遇袭→布油106美元→高油价→高通胀→加息预期恶性循环。","<b>最大利好（台积电Q3超预期）：</b>营收467亿美元+51%，净利润+68.7%，Q4指引523-543亿高于市场503亿。2nm占8%。AI需求"极度强劲"——但A股完全无视这个利好继续杀跌。","<b>结论：</b>消息面利空核弹级。CPI超预期+长鑫技术突破+中东升级三重利空共振，台积电超预期的利好被完全淹没。<b>市场已经进入"利好不涨、利空暴杀"的恐慌模式</b>。"]}}],
  "heat": [{{"name":"PCB概念","dir":"up","w":95,"label":"金禄电子20CM涨停"}},{{"name":"白酒","dir":"up","w":65,"label":"皇台酒业涨停"}},{{"name":"券商","dir":"up","w":55,"label":"华林证券涨停"}},{{"name":"银行","dir":"up","w":50,"label":"六大行逆势微涨"}},{{"name":"创新药","dir":"up","w":45,"label":"百花医药涨停"}},{{"name":"CPO/光模块","dir":"down","w":95,"label":"中际旭创-5.73%"}},{{"name":"航运港口","dir":"down","w":90,"label":"招商轮船跌停"}},{{"name":"半导体/存储","dir":"down","w":88,"label":"长鑫冲击+六连跌"}},{{"name":"军工/航天","dir":"down","w":80,"label":"全线杀跌"}},{{"name":"煤炭/油气","dir":"down","w":65,"label":"高位回调"}}],
  "heat_callout": "热力图总结（200字，分析板块轮动逻辑。要求：1）指出逆势板块逻辑 2）分析杀跌板块原因 3）点评资金行为。示例：'<b>今日格局：PCB独苗抱团 + 红利防御撑盘 + 科技/航运全线崩塌。</b> 5105股下跌，仅白酒/银行/券商两个半行业收红。<b>PCB板块逆势7只涨停是全场唯一亮点</b>——金禄电子20CM涨停（三季报预增219%）、澳弘电子19天11板。航运港口遭遇重挫——招商轮船、中远海能跌停。CPO/光模块延续昨日杀跌——中际旭创-5.73%、新易盛-5.84%。<span class=\\"ph\\">科技硬件+航运港口双线崩盘</span>，白酒/银行/券商逆势收红=典型risk-off格局。成交1.63万亿放量2186亿——<b>资金在逃命，不是在抄底</b>。'",
  "stocks": [{{"name":"金禄电子","tag":"lim","tag_text":"20CM涨停","desc":"PCB三季报预增219%","cv_color":"r"}},{{"name":"澳弘电子","tag":"lim","tag_text":"19天11板","desc":"PCB创新高","cv_color":"r"}},{{"name":"慈文传媒","tag":"lim","tag_text":"5连板","desc":"AI漫剧妖股","cv_color":"r"}},{{"name":"华林证券","tag":"lim","tag_text":"涨停","desc":"券商午后护盘","cv_color":"r"}},{{"name":"皇台酒业","tag":"lim","tag_text":"涨停","desc":"白酒逆势","cv_color":"r"}},{{"name":"中际旭创","tag":"limg","tag_text":"-5.73%","desc":"CPO龙头被砸","cv_color":"g"}},{{"name":"新易盛","tag":"limg","tag_text":"-5.84%","desc":"CPO跟跌","cv_color":"g"}},{{"name":"招商轮船","tag":"limg","tag_text":"跌停","desc":"航运崩盘","cv_color":"g"}},{{"name":"联想集团(HK)","tag":"limg","tag_text":"-14.34%","desc":"PC出货+AI担忧","cv_color":"g"}},{{"name":"三星电子(KR)","tag":"limg","tag_text":"-9.48%","desc":"长鑫冲击+外资砸","cv_color":"g"}},{{"name":"SK海力士(KR)","tag":"limg","tag_text":"-10.01%","desc":"存储芯片信仰崩塌","cv_color":"g"}},{{"name":"台积电(US)","tag":"taga","tag_text":"Q3超预期+51%","desc":"AI验证通过","cv_color":"r"}},{{"name":"铠侠(JP)","tag":"limg","tag_text":"-13.28%","desc":"存储芯片暴跌","cv_color":"g"}},{{"name":"软银集团(JP)","tag":"limg","tag_text":"-8%","desc":"ARM持股拖累","cv_color":"g"}},{{"name":"戴尔(US)","tag":"limg","tag_text":"-11%","desc":"AI服务器泡沫退潮","cv_color":"g"}},{{"name":"长鑫存储","tag":"taga","tag_text":"4F²突破","desc":"中国存储芯片崛起","cv_color":"r"}}],
  "stocks_callout": "个股总结（200字，分析资金流向。要求：1）对比逆势股和杀跌股 2）点评资金行为 3）全球视角。示例：'<b>今日最值得关注的三个对比：</b> <b>① 台积电Q3超预期（AI验证通过） vs 全球芯片股六连跌（市场不信）</b>——台积电说AI需求"极度强劲"，市场说"我不信，先跑了"。<span class=\\"ph\\">基本面和情绪面完全背离</span>。 <b>② 金禄电子20CM涨停（业绩驱动） vs 慈文传媒5连板（情绪投机）</b>——同一个市场里，有人在买业绩，有人在追妖股。<b>说明资金极度分裂，没有共识方向</b>。 <b>③ 长鑫4F²技术突破（中国存储崛起） vs 三星-9.48%/SK海力士-10.01%（韩国存储崩塌）</b>——中国技术突破的蝴蝶效应，一天蒸发韩国5800亿市值。<span class=\\"ph\\">全球半导体格局正在被重写</span>。'",
  "commodity_callout": "大宗商品与汇率总结（300字，逐一分析各品种走势和逻辑。要求：1）每个品种都要点评 2）分析驱动因素 3）点评风险。示例：'<b>大宗关键信号：</b><b>布油106美元+WTI 95美元</b>——胡塞袭击沙特阿美总部+霍尔木兹海峡12艘商船遇袭，地缘溢价持续。IEA警告柴油紧缺至2027下半年。<b>高油价→高通胀→加息预期→全球杀跌</b>，恶性循环仍在运转。 <b>黄金4127美元-1.20%</b>——CPI超预期后美元走强压制黄金。但现货黄金今日反弹超1%至4158美元——<b>美元走强+黄金反弹=市场在"通胀+避险"之间撕裂</b>。白银暴跌6.26%至55.80美元，工业属性拖累。 <b>10年美债5.188%高位</b>——CPI超预期后短端涨（2年期+0.64bp），长端微跌（10年期-2.51bp）。<b>曲线平坦化=市场在定价"短期加息+长期衰退"</b>。加息概率44%。 <b>美元指数102.53</b>——CPI后走强，人民币中间价6.7253调贬4基点。日元158.33接近干预区间。 <b>中国10年国债1.650%</b>——继续下行，说明国内资金充裕但不愿进股市。<b>中美利差3.54个百分点=外资流出压力持续</b>。'",
  "industries": [{{"icon":"💾","name":"存储芯片/半导体","status":"hot","status_text":"长鑫核弹+韩日崩盘","points":["<b>长鑫存储4F²架构突破</b>：10月10日官宣，年底推出新一代DDR5 RDIMM服务器内存。<span class=\\"hl\\">存储密度提升30%-50%，绕开EUV限制</span>——国产DRAM首次正面冲击三星/海力士/美光垄断的服务器市场","<b>三星电子</b> <span class=\\"dn\\">-9.48%（210,000韩元）</span>，SK海力士 <span class=\\"dn\\">-10.01%（1,277,000韩元）</span>——两大巨头单日蒸发约5800亿人民币","<b>外资集中抛售</b>：10月13日韩国外资净卖出4.53万亿韩元，<span class=\\"hl\\">82%集中在三星和SK海力士</span>——不是普通减仓，是对存储芯片逻辑的重定价","<b>台积电Q3验证通过</b>：营收467亿美元+51%，Q4指引523-543亿高于市场503亿。2nm占8%晶圆营收。但市场选择"无视利好继续杀"","<b>费城半导体六连跌</b>：创2025年5月以来最长。存储芯片全线重挫——<b>代工赚钱≠芯片公司赚钱</b>","<b>关注点</b>：长鑫4F²=全球存储芯片格局重塑的开始。如果DDR5 RDIMM年底量产成功，三星/海力士的垄断溢价将系统性下降"],"sources":"长鑫存储 · SEMI · 东方财富 · Bloomberg · 雪球 · 百度百科"}},{{"icon":"⛽","name":"原油/能源","status":"hot","status_text":"胡塞打阿美+柴油紧缺","points":["<b>布伦特原油</b> <span class=\\"up\\">106.11美元/桶（+0.40%）</span>，WTI <span class=\\"up\\">95.17美元（+1.09%）</span>——地缘溢价持续支撑","<b>胡塞袭击沙特阿美总部</b>：10月14日袭击宰赫兰总部+利雅得机场+炼油厂——<span class=\\"hl\\">不是骚扰，是正面升级</span>","<b>霍尔木兹海峡</b>：10月5-11日<span class=\\"hl\\">12艘商船遇袭</span>，创冲突以来单周最高。经霍尔木兹原油运量约740万桶/日，远低于冲突前2000万桶/日","<b>IEA月报</b>：<span class=\\"hl\\">"柴油供应受限持续至2027年下半年"</span>——Q3库存降幅远高于正常水平。G7投放1亿桶柴油+原油","<b>国内燃油附加费</b>：10月10日起800公里以上90元（+20元）——物流成本继续攀升","<b>OPEC</b>：连续第六个月下调2026年需求增长预期，但沙特增产推动9月产量大增"],"sources":"IEA · OPEC · Reuters · 新华社 · 央视新闻 · Kpler · 东方财富"}},{{"icon":"🔌","name":"PCB/AI硬件","status":"warm","status_text":"PCB逆势+AI硬件退潮","points":["<b>金禄电子20CM涨停</b>：前三季归母净利润预增<span class=\\"up\\">192.88%-218.92%</span>——AI算力PCB+汽车电子双驱动。开盘3分钟直线涨停","<b>澳弘电子19天11板</b>：续创历史新高——PCB板块预喜率100%","<b>PCB板块逆势7只涨停</b>：崇达技术、骏亚科技、天津普林、金禄电子涨停——<span class=\\"hl\\">5100股下跌中贡献近20%涨停数</span>","<b>港股AI硬件退潮</b>：联想集团<span class=\\"dn\\">-14.34%</span>，长飞光纤光缆-13%，建滔积层板-9%+——戴尔-11%/慧与-8.28%传导","<b>台积电Q4指引523-543亿美元</b>：高于市场503亿——芯片代工需求确认，但终端硬件能否变现存疑","<b>关注点</b>：PCB逆势涨停=业绩驱动的结构性机会，但在系统性杀跌中独木难支。AI硬件从"信仰"到"验证"的转折点"],"sources":"东方财富 · 财联社 · 凤凰财经 · NBD · 台积电 · Bloomberg"}},{{"icon":"🪙","name":"贵金属/汇率","status":"cool","status_text":"CPI冲击+黄金撕裂","points":["<b>COMEX黄金期货</b> <span class=\\"dn\\">4,127.30美元（-1.20%）</span>——CPI超预期后美元走强压制。但现货黄金今日反弹超1%至<span class=\\"up\\">4,158.63美元</span>","<b>COMEX白银期货</b> <span class=\\"dn\\">55.80美元（-6.26%）</span>——暴跌，工业+贵金属双属性共振下跌","<b>美元指数</b> <span class=\\"up\\">102.53（+0.33%）</span>——CPI后走强，一度冲18个月高点。今日小幅回落至102.06","<b>人民币中间价</b> 6.7253（调贬4基点），在岸6.6925（+20基点）——<b>央行维稳但力度减弱</b>","<b>10年美债</b> <span class=\\"dn\\">5.188%（-2.51基点）</span>——长端微跌，短端2年期涨至4.798%。曲线平坦化=定价"短加息+长衰退"","<b>中美利差</b> 3.54个百分点（美5.188% vs 中1.650%）——外资流出压力持续"],"sources":"东方财富 · 新浪财经 · 金投网 · COMEX · Moneycontrol · 中国货币网"}},{{"icon":"⚡","name":"新能源/锂电","status":"cool","status_text":"排产高增+价格下行","points":["<b>10月锂电排产</b> <span class=\\"up\\">345GWh（环比+3.9%，同比+35%-59%）</span>——头部6家电池企业排产214.6GWh，同比+57%","<b>碳酸锂期货</b>：昨日跌破10万元/吨——从5月高点20.5万跌了50.8%。<span class=\\"hl\\">供过于求格局未改</span>","<b>固态电池政策</b>：七部门"新型电池十五五规划"明确2030年全固态电池初步规模化——财政部免征消费税至2028年底","<b>韩国EcoPro BM+三星SDI</b>：签署MOU围绕全固态电池材料合作，推进2027年商业化","<b>风电前三季度核准</b> <span class=\\"up\\">117.5GW（同比+32.16%）</span>——但A股风电设备加速出清，大金重工此前连续跌停","<b>特高压</b>：国家电网"十五五"力争投产特高压直流15回以上；2026年智能电表招标同比+69%"],"sources":"广期所 · 大东时代智库 · 七部门规划 · 国金证券 · 国家电网"}},{{"icon":"🚢","name":"航运/地缘","status":"hot","status_text":"港口跌停+霍尔木兹升级","points":["<b>A股航运港口崩盘</b>：<span class=\\"hl\\">招商轮船、中远海能跌停</span>——板块领跌全场。尽管霍尔木兹海峡风险升级，但市场在risk-off中无差别抛售","<b>霍尔木兹海峡</b>：10月首周<span class=\\"hl\\">12艘商船遇袭</span>，创冲突以来最高。经霍尔木兹运量约740万桶/日，远低于冲突前2000万桶/日","<b>胡塞袭击沙特阿美</b>：10月14日袭击宰赫兰总部+利雅得机场+炼油厂——"接下来几天将继续"","<b>油轮运价</b>：四季度脏油轮运价维持高位，MEG航线风险溢价叠加","<b>关注点</b>：航运港口跌停看似矛盾（地缘升级应该利好运价），实则是<b>资金在risk-off中无差别抛售</b>。11月3日特朗普中期选举后"选前不动武"承诺到期——如果对伊动武=油价冲120+运价飙升"],"sources":"Reuters · 新华社 · Kpler · 东方财富 · 财通交运 · 国际海事组织"}}],
  "industry_callout": "产业总结（250字，分析产业链动态。要求：1）提炼3条最关键信号 2）分析产业链影响 3）点评风险。示例：'<b>本周最值得关注的三条产业链信号：</b> <b>① 长鑫4F²技术突破=全球存储芯片格局重塑</b>——年底DDR5 RDIMM量产如果成功，三星/海力士垄断溢价系统性下降。韩国一天蒸发5800亿市值只是开始； <b>② 台积电Q3超预期+Q4指引高于市场=AI需求"极度强劲"</b>——但全球芯片股六连跌说明市场不买账。代工赚钱≠芯片公司赚钱≠硬件品牌赚钱。<b>AI硬件价值链正在被重新定价</b>； <b>③ 美国CPI超预期+中东地缘升级=高油价→高通胀→加息的恶性循环</b>——布油106美元+柴油紧缺至2027+加息概率44%。全球risk-off常态化。'",
  "strategy": ["<b>短期（1-3天）：台积电超预期是反弹催化剂，但CPI核弹压制效果有限。</b>台积电Q3营收+51%、Q4指引高于市场、AI需求"极度强劲"——这是昨天CPO被砸30亿后最关键的"翻盘牌"。但美国CPI超预期+加息概率44%+亚洲熔断=系统性风险压顶。<span class=\\"ph\\">如果明天美股期货反弹（台积电ADR盘后涨超3%），A股科技可能迎来"错杀修复"</span>。但如果CPI恐慌持续发酵，反弹空间有限。沪指3700/创业板2800是关键防线。","<b>中期（1-2周）：三季报窗口=业绩验证+方向选择。</b>PCB三季报预喜率100%（金禄电子预增219%）=结构性机会存在。但5105股下跌说明<b>业绩好≠能涨</b>。长鑫4F²技术突破将重塑存储芯片格局——韩国蒸发5800亿只是定价重写的第一步。<b>如果A股科技在台积电超预期后仍然不涨，说明资金已经系统性撤离，不再是"错杀"而是"出清"</b>。","<b>长期（1-3月）：高油价+高利率+技术替代=全球半导体格局剧变。</b>布油106美元+10年美债5.19%+美元指数102+加息概率44%=<b>全球资产定价之锚被重新定价</b>。长鑫技术突破=中国存储芯片从"低端替代"到"正面硬刚"。韩国连续7天下跌+两次熔断=东亚半导体"卡脖子"叙事动摇。<b>全球资金正在从"AI泡沫"向"确定性"迁移</b>——煤炭/红利/高股息是A股的确定性，美元/美债是全球的确定性。","<b>风险点：</b>①美联储11月加息——CPI连续超预期则从"小概率"变"基准情形"；②创业板破2800——技术面全面崩塌引发更大规模止损；③韩国危机扩散——KOSPI熔断如果引发外资从亚洲全面撤退；④特朗普选后对伊动武——油价冲120美元；⑤长鑫量产不及预期——存储芯片反弹但中国技术路线不确定性仍在。"],
  "dirs": [{{"text":"PCB/业绩高增（结构性机会）","cool":false}},{{"text":"白酒/红利（risk-off护甲）","cool":false}},{{"text":"煤炭/高股息（防御配置）","cool":false}},{{"text":"台积电产业链（超预期验证）","cool":false}},{{"text":"CPO/光模块（六连跌回避）","cool":true}},{{"text":"航运港口（跌停潮回避）","cool":true}},{{"text":"半导体/存储（长鑫冲击+六连跌）","cool":true}},{{"text":"风电/新能源（加速出清回避）","cool":true}}],
  "risks": ["<b>美联储11月议息会议</b>——CPI超预期后加息概率44%。如果10月PPI/零售数据继续超预期，加息可能从"可能"变"确定"。这是全球风险资产的最大威胁。","<b>创业板2800点防线</b>——今天收2783，距离2800仅一步之遥。跌破=技术面全面崩塌=更大规模止损。这是A股的"生死线"。","<b>韩国危机扩散风险</b>——KOSPI两天蒸发5800亿+两次熔断。如果外资从亚洲全面撤退，A股/港股/日股连环受压。韩国金融服务委员会紧急介入但能力有限。","<b>中东冲突升级</b>——胡塞袭击沙特阿美总部+霍尔木兹海峡12艘商船遇袭。如果对伊动武=油价冲120美元=全球通胀加剧=加息加速。","<b>长鑫量产不确定性</b>——4F²架构DDR5 RDIMM年底量产如果不及预期，存储芯片可能反弹，但中国技术路线的长期不确定性仍在。","<b>成交持续萎缩或放量杀跌</b>——1.63万亿放量杀跌比缩量阴跌更可怕。如果明天继续放量向下，可能引发流动性危机。"]
}}

要求：
1. hero_title: 40字内，包含4个核心数据点，用<em>和<i>标签强调关键数据
2. hero_sub: 一句话概括关键数据，用·分隔
3. summary: 300-400字，开头一句最亮眼事件，然后按格式浓缩全部核心指数点位涨跌幅（精确到小数点）、成交额、板块主线、3-4条重要消息、美股/港股/商品关键数据，结尾固定加'含9条环球要闻深度解读+五维度全分析+6大产业高频数据+策略研判'
4. overview_callout: 250字，含<b>标签，分析市场特点/资金行为/板块轮动，用'说人话'方式犀利点评，可以带讽刺
5. global_callout: 400字，含<b>标签，逐一分析亚太/美股/欧股表现、联动关系、风险点，用全球视角对比，客观评价A股表现，可以批评
6. index_notes / com_notes: 为每个指数/品种填一句6字内的定性后缀（无补充则留空字符串）
7. news: 9条（4条a级极重要 + 3条b级重要 + 2条c级关注），sources中至少含1个国际源（Reuters/Bloomberg/WSJ/FT/CNBC），每条都有深度分析。title 40字内，body 150字，impact_body 120字，犀利点评事件影响和逻辑，可以带讽刺
8. five_dims: 5个维度（消息面/情绪面/技术面/政策面/资金面），每个5个points，每个point 80字，含<b>标签强调关键数据
9. heat: 10个板块（5涨5跌），基于a_sectors数据，dir为up或down，w为10-95，label 10字内
10. heat_callout: 200字，分析板块轮动逻辑，指出逆势板块逻辑，分析杀跌板块原因，点评资金行为
11. stocks: 16只个股（A股8 + 港股4 + 美股4），基于a_stocks数据，tag为lim/taga/tagi/limg之一，cv_color为r或g
12. stocks_callout: 200字，对比逆势股和杀跌股，点评资金行为，全球视角
13. commodity_callout: 300字，逐一分析各品种走势和逻辑，每个品种都要点评，分析驱动因素，点评风险
14. industries: 6个产业卡片（存储芯片/半导体、原油/能源、PCB/AI硬件、贵金属/汇率、新能源/锂电、航运/地缘），status为hot/warm/cool，每个point 80字，含<span class="num">等标签
15. industry_callout: 250字，提炼3条最关键信号，分析产业链影响，点评风险
16. strategy: 4条（短期/中期/长期/风险），每条120字，含<b>标签强调关键判断
17. dirs: 8个方向（部分cool:true表示回避）
18. risks: 6条，每条80字，含<b>标签强调关键风险
19. 语言风格：犀利客观、可以带讽刺、不要套话，用"说人话"的方式解读
20. 所有数字必须来自我提供的市场数据，不得编造
21. 直接输出JSON，不要```json标记

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
