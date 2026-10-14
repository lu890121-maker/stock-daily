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
import sys
import json
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
def yf_quote(sym):
    """通用 yfinance 行情：返回 {'v': float, 'c': pct} 或 None"""
    if SKIP_YF:
        return None
    try:
        h = yf.Ticker(sym).history(period="7d")
        h = h.dropna()
        if len(h) >= 2:
            last = float(h.iloc[-1]['Close'])
            prev = float(h.iloc[-2]['Close'])
            if prev:
                return {'v': last, 'c': (last - prev) / prev * 100}
    except Exception as e:
        print(f"    yf {sym} 失败: {type(e).__name__}")
    return None


def fetch_data():
    data = {}

    # ---------- 1. A股指数（实时行情） ----------
    print("抓取A股指数...")
    try:
        # 优先用实时行情接口
        df = ak.stock_zh_index_spot_em()
        
        def _a_spot(code):
            row = df[df['代码'] == code]
            if len(row):
                r = row.iloc[0]
                return {'v': float(r['最新价']), 'c': float(r['涨跌幅'])}
            return None
        
        data['a'] = {
            'sh': _a_spot('000001'),  # 上证指数
            'sz': _a_spot('399001'),  # 深证成指
            'cy': _a_spot('399006'),  # 创业板指
            'kc': _a_spot('000688'),  # 科创50
        }
        
        # 如果实时接口失败，回退到历史接口
        if not data['a']['sh']:
            print("  实时接口失败，回退历史接口...")
            def _a_hist(sym):
                d = ak.stock_zh_index_daily(symbol=sym).iloc[-2:]
                return {'v': float(d.iloc[-1]['close']),
                        'c': (float(d.iloc[-1]['close']) - float(d.iloc[-2]['close'])) / float(d.iloc[-2]['close']) * 100}
            data['a'] = {'sh': _a_hist("sh000001"), 'sz': _a_hist("sz399001"), 
                        'cy': _a_hist("sz399006"), 'kc': _a_hist("sh000688")}
        
        print(f"  A股: 沪指{data['a']['sh']['v']:.2f}({data['a']['sh']['c']:+.2f}%)")
        
        # 获取成交额和涨跌家数（用于 statbar）
        try:
            # 获取两市成交额
            vol_df = ak.stock_zh_index_spot_em()
            sh_row = vol_df[vol_df['代码'] == '000001']
            sz_row = vol_df[vol_df['代码'] == '399001']
            if len(sh_row) and len(sz_row):
                sh_vol = float(sh_row.iloc[0].get('成交额', 0)) / 1e8  # 转为亿
                sz_vol = float(sz_row.iloc[0].get('成交额', 0)) / 1e8
                data['a_stats'] = {
                    'volume': f"{(sh_vol + sz_vol) / 10000:.2f}万亿",  # 转为万亿
                    'up_count': int(sh_row.iloc[0].get('上涨家数', 0)) + int(sz_row.iloc[0].get('上涨家数', 0)),
                    'down_count': int(sh_row.iloc[0].get('下跌家数', 0)) + int(sz_row.iloc[0].get('下跌家数', 0)),
                }
                print(f"  成交额: {data['a_stats']['volume']} | 上涨: {data['a_stats']['up_count']} | 下跌: {data['a_stats']['down_count']}")
        except Exception as e:
            print(f"  成交额/涨跌家数获取失败: {e}")
    except Exception as e:
        print(f"  A股失败: {e}")
        return None

    # ---------- 2. A股板块 ----------
    print("抓取A股板块...")
    try:
        sdf = ak.stock_board_industry_name_em()
        if sdf is not None and len(sdf):
            sdf = sdf.sort_values('涨跌幅', ascending=False)
            data['a_sectors'] = {
                'top5': sdf.head(5)[['板块名称', '涨跌幅']].to_dict('records'),
                'bottom5': sdf.tail(5)[['板块名称', '涨跌幅']].to_dict('records'),
            }
            print(f"  板块: 第一 {data['a_sectors']['top5'][0]['板块名称']} +{data['a_sectors']['top5'][0]['涨跌幅']:.2f}%")
    except Exception as e:
        print(f"  板块失败: {e}")

    # ---------- 3. A股涨停 ----------
    print("抓取A股涨停...")
    try:
        zt = ak.stock_zt_pool_em(date=today_str().replace('-', ''))
        if zt is not None and len(zt):
            data['a_stocks'] = {'zt_count': len(zt),
                                'zt_top5': zt.head(8)[['代码', '名称', '涨跌幅']].to_dict('records')}
            print(f"  涨停: {len(zt)}家")
    except Exception as e:
        print(f"  涨停失败: {e}")

    # ---------- 4. 港股 ----------
    print("抓取港股...")
    try:
        def _hk(sym):
            d = ak.stock_hk_index_daily_sina(symbol=sym).iloc[-2:]
            return {'v': float(d.iloc[-1]['close']),
                    'c': (float(d.iloc[-1]['close']) - float(d.iloc[-2]['close'])) / float(d.iloc[-2]['close']) * 100}
        data['hk'] = {'hsi': _hk("HSI"), 'hstech': _hk("HSTECH")}
        print(f"  港股: 恒指{data['hk']['hsi']['v']:.2f}({data['hk']['hsi']['c']:+.2f}%)")
    except Exception as e:
        print(f"  港股失败: {e}")

    # ---------- 5. 全球指数（akshare 东方财富全球指数，一次全取） ----------
    print("抓取全球指数...")
    try:
        g = ak.index_global_spot_em()

        def _g(code):
            row = g[g['代码'] == code]
            if len(row):
                r = row.iloc[0]
                try:
                    return {'v': float(r['最新价']), 'c': float(r['涨跌幅'])}
                except Exception:
                    return None
            return None

        data['us'] = {'dj': _g('DJIA'), 'sp': _g('SPX'), 'nq': _g('NDX')}
        data['asia'] = {'kospi': _g('KS11'), 'n225': _g('N225')}
        data['eu'] = {'stoxx': _g('SX5E'), 'dax': _g('GDAXI'), 'cac': _g('FCHI'), 'ftse': _g('FTSE')}
        data['fx'] = {'dxy': _g('UDI')}
        dj = data['us']['dj']
        ks = data['asia']['kospi']
        print(f"  全球指数: 道指{dj['v'] if dj else '—'} | KOSPI{ks['v'] if ks else '—'} | 美元指数{data['fx']['dxy']['v'] if data['fx']['dxy'] else '—'}")
    except Exception as e:
        print(f"  全球指数失败: {e}")

    # ---------- 6. 大宗商品（yfinance 主，akshare 回退） ----------
    print("抓取大宗商品...")
    com = {'gold': yf_quote('GC=F'), 'silver': yf_quote('SI=F'),
           'brent': yf_quote('BZ=F'), 'wti': yf_quote('CL=F'), 'copper': yf_quote('HG=F')}
    if not any(com.values()):
        print("  yfinance 商品失败，回退 akshare futures_global_spot_em...")
        try:
            fg = ak.futures_global_spot_em()

            def _fc(code):
                row = fg[fg['代码'] == code]
                if len(row):
                    r = row.iloc[0]
                    try:
                        return {'v': float(r['最新价']), 'c': float(r['涨跌幅'])}
                    except Exception:
                        return None
                return None

            def _fm(kw):
                sub = fg[fg['名称'].astype(str).str.contains(kw, na=False)].dropna(subset=['最新价'])
                if len(sub):
                    r = sub.iloc[0]
                    return {'v': float(r['最新价']), 'c': float(r['涨跌幅'])}
                return None

            com = {'gold': _fc('GC00Y'), 'silver': _fc('SI00Y'),
                   'brent': _fm('布伦特'), 'wti': _fc('CL00Y'), 'copper': _fc('HG00Y')}
        except Exception as e:
            print(f"  商品回退失败: {e}")
    data['com'] = com
    if com.get('gold'):
        print(f"  商品: 黄金{com['gold']['v']:.2f}({com['gold']['c']:+.2f}%)")

    # ---------- 7. 汇率 / 美债 / VIX ----------
    print("抓取汇率债券...")
    usdcny = yf_quote('CNY=X')
    if usdcny:
        data['fx']['usdcny'] = usdcny
    else:
        try:
            fxq = ak.fx_spot_quote()
            row = fxq[fxq['货币对'] == 'USD/CNY']
            if len(row):
                data['fx']['usdcny'] = {'v': float(row.iloc[0]['买报价']), 'c': None}
        except Exception as e:
            print(f"  汇率回退失败: {e}")
    tnx = yf_quote('^TNX')
    if tnx:
        data['bond'] = {'us10y': tnx}
    vix = yf_quote('^VIX')
    if vix:
        data['vix'] = vix

    # ---------- 8. 加密货币 ----------
    print("抓取加密货币...")
    btc = yf_quote('BTC-USD')
    eth = yf_quote('ETH-USD')
    if btc or eth:
        data['crypto'] = {'btc': btc, 'eth': eth}
        if btc:
            print(f"  加密: BTC{btc['v']:.0f}({btc['c']:+.2f}%)")

    got = sum(1 for k in ['a', 'hk', 'us', 'asia', 'eu', 'com', 'fx', 'bond', 'vix', 'crypto'] if data.get(k))
    print(f"数据抓取完成: {got}/10 个板块")
    return data


def fetch_news():
    """抓取财经新闻标题（best-effort）"""
    feeds = [
        ('Reuters', 'https://feeds.reuters.com/reuters/businessNews'),
        ('CNBC', 'https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114'),
        ('Yahoo Finance', 'https://finance.yahoo.com/news/rssindex'),
        ('MarketWatch', 'https://feeds.content.dowjones.io/public/rss/mw_topstories'),
    ]
    heads = []
    for name, url in feeds:
        try:
            r = requests.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
            root = ET.fromstring(r.content)
            for it in root.findall('.//item')[:6]:
                t = it.findtext('title')
                if t:
                    heads.append(f"[{name}] {t.strip()}")
        except Exception as e:
            print(f"  RSS {name} 失败: {type(e).__name__}")
    print(f"  新闻标题: {len(heads)} 条")
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
  "overview_callout": "A股定性总结（200字，含<b>标签，分析市场特点/资金行为/板块轮动）",
  "global_callout": "全球市场总结（320字，含<b>标签，逐一分析亚太/美股/欧股表现、联动关系、风险点）",
  "index_notes": {{"上证指数":"缩量阴跌","深证成指":"","创业板指":"失守3000","科创50":"","恒生指数":"","恒生科技":"","韩国 KOSPI":"外资砸盘","日经225":"","道琼斯":"","标普500":"逼近新高","纳斯达克":"","欧洲斯托克600":"","德国DAX":"领涨","法国CAC40":"","英国富时100":""}},
  "com_notes": {{"现货黄金":"续创新高","COMEX白银期货":"","布伦特原油":"微跌","WTI原油":"","COMEX铜":"","美元/离岸人民币":"","美元指数":"","10年期美债收益率":"高位","VIX恐慌指数":"恐慌退潮","比特币":"","以太坊":""}},
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
def _row(label, q, note='', unit='', prefix='', dec=2):
    """生成一行行情表格"""
    if not q:
        return f'<tr><td class="name">{label}</td><td>—</td><td class="n0">暂无数据</td></tr>\n'
    val = f"{prefix}{num(q['v'], dec)}{(' ' + unit) if unit else ''}"
    c = q.get('c')
    if c is None:
        return f'<tr><td class="name">{label}</td><td>{val}</td><td class="n0">{note or "—"}</td></tr>\n'
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

    a_stats = data.get('a_stats', {})
    
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
    {"" if not a_stats else f'''<div class="statbar">
      <div class="stat"><div class="k">两市成交</div><div class="v">{a_stats.get('volume', '-')}</div></div>
      <div class="stat"><div class="k">上涨家数</div><div class="v up">{a_stats.get('up_count', '-')}</div></div>
      <div class="stat"><div class="k">下跌家数</div><div class="v down">{a_stats.get('down_count', '-')}</div></div>
      <div class="stat"><div class="k">涨停家数</div><div class="v up">{data.get('a_stocks', {}).get('zt_count', '-')}</div></div>
    </div>'''}
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
        _row('欧洲斯托克50', eu.get('stoxx'), inote.get('欧洲斯托克50', '')) +
        _row('德国 DAX', eu.get('dax'), inote.get('德国DAX', '')) +
        _row('法国 CAC40', eu.get('cac'), inote.get('法国CAC40', '')) +
        _row('英国 富时100', eu.get('ftse'), inote.get('英国富时100', ''))
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
        _row('COMEX白银期货', com.get('silver'), cnote.get('COMEX白银期货', ''), '美元/盎司') +
        _row('布伦特原油', com.get('brent'), cnote.get('布伦特原油', ''), '美元/桶') +
        _row('WTI原油', com.get('wti'), cnote.get('WTI原油', ''), '美元/桶') +
        _row('COMEX铜', com.get('copper'), cnote.get('COMEX铜', ''), '美元/磅')
    )
    fxb_rows = (
        _row('美元/人民币', fx.get('usdcny'), cnote.get('美元/离岸人民币', ''), '', '', 4) +
        _row('美元指数', fx.get('dxy'), cnote.get('美元指数', '')) +
        _row('10年期美债收益率', bond.get('us10y'), cnote.get('10年期美债收益率', ''), '%') +
        _row('VIX恐慌指数', vix, cnote.get('VIX恐慌指数', ''))
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


# ============ 主流程 ============
def main():
    print("=" * 60)
    print("每日全球股市报告生成器 v3")
    print("=" * 60)
    data = fetch_data()
    if not data:
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
    print("=" * 60)


if __name__ == '__main__':
    main()
