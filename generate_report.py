#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日全球股市报告生成器 - 增强版
包含完整的数据抓取：A股、港股、美股、欧股、大宗商品、汇率、债券、加密货币
"""

import os
import sys
import json
import requests
import akshare as ak
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import pytz

# 配置
DASHSCOPE_API_KEY = os.environ.get('DASHSCOPE_API_KEY')
if not DASHSCOPE_API_KEY:
    print("错误：未设置 DASHSCOPE_API_KEY 环境变量")
    sys.exit(1)

API_URL = 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions'
MODEL = 'qwen-plus'

def today_str():
    """获取今天的日期字符串"""
    beijing_tz = pytz.timezone('Asia/Shanghai')
    now = datetime.now(beijing_tz)
    return now.strftime('%Y-%m-%d')

def today_display():
    """获取今天的显示格式"""
    beijing_tz = pytz.timezone('Asia/Shanghai')
    now = datetime.now(beijing_tz)
    weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
    return f"{now.year}年{now.month}月{now.day}日 {weekdays[now.weekday()]}"

def today_short():
    """获取今天的短格式"""
    beijing_tz = pytz.timezone('Asia/Shanghai')
    now = datetime.now(beijing_tz)
    return f"{now.month}/{now.day}"

def fmt_pct(value):
    """格式化百分比"""
    if value > 0:
        return f"+{value:.2f}%"
    elif value < 0:
        return f"{value:.2f}%"
    else:
        return f"{value:.2f}%"

def idx_cls(value):
    """判断指数涨跌类别"""
    if value > 0:
        return 'up'
    elif value < 0:
        return 'down'
    else:
        return 'flat'

def fetch_data():
    """抓取所有市场数据"""
    data = {}
    
    # 1. A股数据
    print("抓取A股数据...")
    try:
        sh = ak.stock_zh_index_daily(symbol="sh000001").iloc[-2:]
        sz = ak.stock_zh_index_daily(symbol="sz399001").iloc[-2:]
        cy = ak.stock_zh_index_daily(symbol="sz399006").iloc[-2:]
        kc = ak.stock_zh_index_daily(symbol="sh000688").iloc[-2:]
        
        data['a'] = {
            'sh': {'v': f"{sh.iloc[-1]['close']:.2f}", 'c': round((sh.iloc[-1]['close'] - sh.iloc[-2]['close']) / sh.iloc[-2]['close'] * 100, 2)},
            'sz': {'v': f"{sz.iloc[-1]['close']:.2f}", 'c': round((sz.iloc[-1]['close'] - sz.iloc[-2]['close']) / sz.iloc[-2]['close'] * 100, 2)},
            'cy': {'v': f"{cy.iloc[-1]['close']:.2f}", 'c': round((cy.iloc[-1]['close'] - cy.iloc[-2]['close']) / cy.iloc[-2]['close'] * 100, 2)},
            'kc': {'v': f"{kc.iloc[-1]['close']:.2f}", 'c': round((kc.iloc[-1]['close'] - kc.iloc[-2]['close']) / kc.iloc[-2]['close'] * 100, 2)},
        }
        print(f"  A股: 沪指{data['a']['sh']['v']}({data['a']['sh']['c']:+.2f}%)")
    except Exception as e:
        print(f"  A股失败: {e}")
        return None
    
    # 2. A股板块数据
    print("抓取A股板块数据...")
    try:
        sector_df = ak.stock_board_industry_name_em()
        if sector_df is not None and len(sector_df) > 0:
            # 获取涨幅前5和跌幅前5
            sector_df = sector_df.sort_values('涨跌幅', ascending=False)
            top5 = sector_df.head(5)[['板块名称', '涨跌幅']].to_dict('records')
            bottom5 = sector_df.tail(5)[['板块名称', '涨跌幅']].to_dict('records')
            data['a_sectors'] = {'top5': top5, 'bottom5': bottom5}
            print(f"  板块: 涨幅第一 {top5[0]['板块名称']} +{top5[0]['涨跌幅']:.2f}%")
    except Exception as e:
        print(f"  板块失败: {e}")
    
    # 3. A股个股数据
    print("抓取A股个股数据...")
    try:
        zt_df = ak.stock_zt_pool_em(date=today_str().replace('-', ''))
        if zt_df is not None and len(zt_df) > 0:
            data['a_stocks'] = {
                'zt_count': len(zt_df),
                'zt_top5': zt_df.head(5)[['代码', '名称', '涨跌幅']].to_dict('records')
            }
            print(f"  涨停: {len(zt_df)}家")
    except Exception as e:
        print(f"  个股失败: {e}")
    
    # 4. 港股数据
    print("抓取港股数据...")
    try:
        hs = ak.stock_hk_index_daily_sina(symbol="HSI").iloc[-2:]
        ht = ak.stock_hk_index_daily_sina(symbol="HSTECH").iloc[-2:]
        data['hk'] = {
            'hsi': {'v': f"{hs.iloc[-1]['close']:.2f}", 'c': round((hs.iloc[-1]['close'] - hs.iloc[-2]['close']) / hs.iloc[-2]['close'] * 100, 2)},
            'hstech': {'v': f"{ht.iloc[-1]['close']:.2f}", 'c': round((ht.iloc[-1]['close'] - ht.iloc[-2]['close']) / ht.iloc[-2]['close'] * 100, 2)},
        }
        print(f"  港股: 恒指{data['hk']['hsi']['v']}({data['hk']['hsi']['c']:+.2f}%)")
    except Exception as e:
        print(f"  港股失败: {e}")
    
    # 5. 美股数据
    print("抓取美股数据...")
    try:
        dj = ak.index_us_stock_sina(symbol=".DJI").iloc[-2:]
        sp = ak.index_us_stock_sina(symbol=".INX").iloc[-2:]
        nq = ak.index_us_stock_sina(symbol=".IXIC").iloc[-2:]
        data['us'] = {
            'dj': {'v': f"{dj.iloc[-1]['close']:.2f}", 'c': round((dj.iloc[-1]['close'] - dj.iloc[-2]['close']) / dj.iloc[-2]['close'] * 100, 2)},
            'sp': {'v': f"{sp.iloc[-1]['close']:.2f}", 'c': round((sp.iloc[-1]['close'] - sp.iloc[-2]['close']) / sp.iloc[-2]['close'] * 100, 2)},
            'nq': {'v': f"{nq.iloc[-1]['close']:.2f}", 'c': round((nq.iloc[-1]['close'] - nq.iloc[-2]['close']) / nq.iloc[-2]['close'] * 100, 2)},
        }
        print(f"  美股: 道指{data['us']['dj']['v']}({data['us']['dj']['c']:+.2f}%)")
    except Exception as e:
        print(f"  美股失败: {e}")
    
    # 6. 欧股数据
    print("抓取欧股数据...")
    try:
        dax = yf.Ticker("^GDAXI").history(period="2d")
        cac = yf.Ticker("^FCHI").history(period="2d")
        ftse = yf.Ticker("^FTSE").history(period="2d")
        
        if len(dax) >= 2 and len(cac) >= 2 and len(ftse) >= 2:
            data['eu'] = {
                'dax': {'v': f"{dax.iloc[-1]['Close']:.2f}", 'c': round((dax.iloc[-1]['Close'] - dax.iloc[-2]['Close']) / dax.iloc[-2]['Close'] * 100, 2)},
                'cac': {'v': f"{cac.iloc[-1]['Close']:.2f}", 'c': round((cac.iloc[-1]['Close'] - cac.iloc[-2]['Close']) / cac.iloc[-2]['Close'] * 100, 2)},
                'ftse': {'v': f"{ftse.iloc[-1]['Close']:.2f}", 'c': round((ftse.iloc[-1]['Close'] - ftse.iloc[-2]['Close']) / ftse.iloc[-2]['Close'] * 100, 2)},
            }
            print(f"  欧股: DAX{data['eu']['dax']['v']}({data['eu']['dax']['c']:+.2f}%)")
    except Exception as e:
        print(f"  欧股失败: {e}")
    
    # 7. 大宗商品数据
    print("抓取大宗商品数据...")
    try:
        gold = ak.futures_foreign_hist(symbol="XAU").iloc[-2:]
        silver = ak.futures_foreign_hist(symbol="XAG").iloc[-2:]
        oil_brent = ak.futures_foreign_hist(symbol="B").iloc[-2:]
        oil_wti = ak.futures_foreign_hist(symbol="CL").iloc[-2:]
        copper = ak.futures_foreign_hist(symbol="HG").iloc[-2:]
        
        data['com'] = {
            'gold': {'v': f"{gold.iloc[-1]['收盘价']:.2f}", 'c': round((gold.iloc[-1]['收盘价'] - gold.iloc[-2]['收盘价']) / gold.iloc[-2]['收盘价'] * 100, 2)},
            'silver': {'v': f"{silver.iloc[-1]['收盘价']:.2f}", 'c': round((silver.iloc[-1]['收盘价'] - silver.iloc[-2]['收盘价']) / silver.iloc[-2]['收盘价'] * 100, 2)},
            'brent': {'v': f"{oil_brent.iloc[-1]['收盘价']:.2f}", 'c': round((oil_brent.iloc[-1]['收盘价'] - oil_brent.iloc[-2]['收盘价']) / oil_brent.iloc[-2]['收盘价'] * 100, 2)},
            'wti': {'v': f"{oil_wti.iloc[-1]['收盘价']:.2f}", 'c': round((oil_wti.iloc[-1]['收盘价'] - oil_wti.iloc[-2]['收盘价']) / oil_wti.iloc[-2]['收盘价'] * 100, 2)},
            'copper': {'v': f"{copper.iloc[-1]['收盘价']:.2f}", 'c': round((copper.iloc[-1]['收盘价'] - copper.iloc[-2]['收盘价']) / copper.iloc[-2]['收盘价'] * 100, 2)},
        }
        print(f"  商品: 黄金{data['com']['gold']['v']}({data['com']['gold']['c']:+.2f}%)")
    except Exception as e:
        print(f"  商品失败: {e}")
    
    # 8. 汇率数据
    print("抓取汇率数据...")
    try:
        dxy = yf.Ticker("DX-Y.NYB").history(period="2d")
        usdcny = yf.Ticker("CNY=X").history(period="2d")
        
        if len(dxy) >= 2 and len(usdcny) >= 2:
            data['fx'] = {
                'dxy': {'v': f"{dxy.iloc[-1]['Close']:.2f}", 'c': round((dxy.iloc[-1]['Close'] - dxy.iloc[-2]['Close']) / dxy.iloc[-2]['Close'] * 100, 2)},
                'usdcny': {'v': f"{usdcny.iloc[-1]['Close']:.4f}", 'c': round((usdcny.iloc[-1]['Close'] - usdcny.iloc[-2]['Close']) / usdcny.iloc[-2]['Close'] * 100, 2)},
            }
            print(f"  汇率: 美元指数{data['fx']['dxy']['v']}({data['fx']['dxy']['c']:+.2f}%)")
    except Exception as e:
        print(f"  汇率失败: {e}")
    
    # 9. 债券数据
    print("抓取债券数据...")
    try:
        us10y = yf.Ticker("^TNX").history(period="2d")
        
        if len(us10y) >= 2:
            data['bond'] = {
                'us10y': {'v': f"{us10y.iloc[-1]['Close']:.3f}", 'c': round((us10y.iloc[-1]['Close'] - us10y.iloc[-2]['Close']) / us10y.iloc[-2]['Close'] * 100, 2)},
            }
            print(f"  债券: 10年美债{data['bond']['us10y']['v']}%({data['bond']['us10y']['c']:+.2f}%)")
    except Exception as e:
        print(f"  债券失败: {e}")
    
    # 10. 加密货币数据
    print("抓取加密货币数据...")
    try:
        btc = yf.Ticker("BTC-USD").history(period="2d")
        eth = yf.Ticker("ETH-USD").history(period="2d")
        
        if len(btc) >= 2 and len(eth) >= 2:
            data['crypto'] = {
                'btc': {'v': f"{btc.iloc[-1]['Close']:.0f}", 'c': round((btc.iloc[-1]['Close'] - btc.iloc[-2]['Close']) / btc.iloc[-2]['Close'] * 100, 2)},
                'eth': {'v': f"{eth.iloc[-1]['Close']:.0f}", 'c': round((eth.iloc[-1]['Close'] - eth.iloc[-2]['Close']) / eth.iloc[-2]['Close'] * 100, 2)},
            }
            print(f"  加密: BTC{data['crypto']['btc']['v']}({data['crypto']['btc']['c']:+.2f}%)")
    except Exception as e:
        print(f"  加密货币失败: {e}")
    
    print(f"数据抓取完成: {len(data)} 个市场")
    return data

def gen_content(data):
    """LLM 生成完整的报告内容"""
    td = today_display()
    ts = today_short()
    
    # 构建详细的数据描述
    data_desc = json.dumps(data, ensure_ascii=False, indent=2)
    
    prompt = f"""你是专业财经分析师。根据以下市场数据生成完整的每日全球股市观察报告。

日期：{td}（{ts}）

市场数据：
{data_desc}

请严格按以下 JSON 格式输出（不要任何额外文字，不要 markdown 标记）：

{{
  "hero_title": "主标题（20字内，用·分隔两个要点，可用<em>和<i>标签强调关键部分）",
  "hero_sub": "副标题（一句话概括关键数据，用·分隔）",
  "overview_callout": "A股定性总结（200字，含<b>标签强调关键句，分析市场特点、资金行为、板块轮动）",
  "global_callout": "全球市场总结（300字，含<b>标签，详细分析各市场表现、联动关系、风险点）",
  "news": [
    {{"level":"a","sources":["Reuters","财联社"],"title":"新闻标题（15字内）","body":"新闻正文（100字，可用<span class=\"num\">等标签）","impact_title":"说人话：","impact_body":"影响分析（80字）"}}
  ],
  "five_dims": [
    {{"name":"消息面","score":"利空主导 ★★☆☆☆","points":["要点1（50字）","要点2","要点3","要点4","结论（50字）"]}}
  ],
  "heat": [
    {{"name":"板块名","dir":"up","w":95,"label":"说明（10字内）"}}
  ],
  "heat_callout": "热力图总结（150字，分析板块轮动逻辑）",
  "stocks": [
    {{"name":"股票名","tag":"lim","tag_text":"标签","desc":"说明","cv_color":"r"}}
  ],
  "stocks_callout": "个股总结（150字，分析资金流向）",
  "commodity_callout": "大宗商品总结（200字，分析各品种走势和逻辑）",
  "industries": [
    {{"icon":"","name":"产业名","status":"hot","status_text":"状态（4字）","points":["要点1（50字）","要点2","要点3","要点4","要点5"],"sources":"信源列表"}}
  ],
  "industry_callout": "产业总结（200字，分析产业链动态）",
  "strategy": ["短期判断（80字）","中期判断（80字）","长期判断（80字）","风险点（80字）"],
  "dirs": [{{"text":"方向名","cool":false}}],
  "risks": ["风险1（50字）","风险2","风险3","风险4","风险5","风险6"]
}}

要求：
1. news: 9条（4条a级极重要 + 3条b级重要 + 2条c级关注），每条都要有深度分析
2. five_dims: 5个维度（消息面/情绪面/技术面/政策面/资金面），每个5个points
3. heat: 10个板块（5涨5跌），基于 a_sectors 数据，dir为up或down，w为10-95
4. stocks: 16只个股（A股8只+港股4只+美股4只），基于 a_stocks 数据，tag为lim/taga/tagi/limg之一
5. industries: 6个产业卡片（原油/能源、锂矿/能源金属、半导体/存储、传媒/AI应用、银行/高股息、贵金属）
6. strategy: 4条判断（短期/中期/长期/风险）
7. dirs: 10个方向（部分cool:true表示回避）
8. risks: 6条风险
9. 语言风格：犀利客观，可以带讽刺，不要套话，用"说人话"的方式解读
10. 所有数据基于我提供的市场数据，不要编造
11. 直接输出 JSON，不要 ```json 标记
12. 重点分析：A股板块轮动、个股表现、资金流向、全球市场联动

请生成完整报告："""

    try:
        print("调用 LLM 生成报告...")
        resp = requests.post(API_URL, 
            headers={'Content-Type':'application/json','Authorization':f'Bearer {DASHSCOPE_API_KEY}'},
            json={'model':MODEL,'messages':[{'role':'user','content':prompt}],'temperature':0.7,'max_tokens':8000}, 
            timeout=180)
        resp.raise_for_status()
        raw = resp.json()['choices'][0]['message']['content'].strip()
        if raw.startswith('```'): raw = raw[raw.find('\n')+1:]
        if raw.endswith('```'): raw = raw[:-3]
        content = json.loads(raw.strip())
        print("✅ LLM 生成成功")
        return content
    except Exception as e:
        print(f"❌ LLM 失败: {e}")
        import traceback
        traceback.print_exc()
        return None

def build_html(c, data):
    """用固定模板构建 HTML（和 10/9 模板 100% 一致）"""
    td = today_display()
    ts = today_short()
    a = data.get('a', {})
    hk = data.get('hk', {})
    us = data.get('us', {})
    com = data.get('com', {})

    sh_c = a.get('sh',{}).get('c',0)
    sz_c = a.get('sz',{}).get('c',0)
    cy_c = a.get('cy',{}).get('c',0)
    kc_c = a.get('kc',{}).get('c',0)
    hsi_c = hk.get('hsi',{}).get('c',0)
    hstech_c = hk.get('hstech',{}).get('c',0)
    dj_c = us.get('dj',{}).get('c',0)
    sp_c = us.get('sp',{}).get('c',0)
    nq_c = us.get('nq',{}).get('c',0)
    gold_c = com.get('gold',{}).get('c',0)
    brent_c = com.get('brent',{}).get('c',0)

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

    overview = f'''  <div class="sec" id="sec-overview">
    <div class="sec-head">
      <div class="sec-ico" style="background:#ffe4e6">📈</div>
      <div class="sec-title">A股收盘速览</div>
      <div class="sec-note">{ts} 15:00 收盘</div>
    </div>
    <div class="idx-grid">
      <div class="idx {idx_cls(sh_c)}"><div class="n">上证指数</div><div class="v">{a.get('sh',{}).get('v','')}</div><div class="c">{fmt_pct(sh_c)}</div></div>
      <div class="idx {idx_cls(sz_c)}"><div class="n">深证成指</div><div class="v">{a.get('sz',{}).get('v','')}</div><div class="c">{fmt_pct(sz_c)}</div></div>
      <div class="idx {idx_cls(cy_c)}"><div class="n">创业板指</div><div class="v">{a.get('cy',{}).get('v','')}</div><div class="c">{fmt_pct(cy_c)}</div></div>
      <div class="idx {idx_cls(kc_c)}"><div class="n">科创50</div><div class="v">{a.get('kc',{}).get('v','')}</div><div class="c">{fmt_pct(kc_c)}</div></div>
    </div>
    <div class="callout">
      {c['overview_callout']}
    </div>
  </div>'''

    global_sec = f'''  <div class="sec" id="sec-global">
    <div class="sec-head">
      <div class="sec-ico" style="background:#e2ecfd">🌏</div>
      <div class="sec-title">全球市场全景</div>
      <div class="sec-note">数据截至 {ts} 15:30</div>
    </div>
    <div class="mkt-legend">
      <span><span class="dot close"></span><b>收盘</b>：A股/港股 {ts}</span>
      <span><span class="dot ovn"></span><b>昨夜</b>：美股 {ts}</span>
    </div>
    <table class="tbl">
      <thead><tr><th>市场 / 指数</th><th>点位</th><th>涨跌</th></tr></thead>
      <tbody>
        <tr class="grp"><td colspan="3">亚太 <span class="st close">{ts} 收盘</span></td></tr>
        <tr class="{'hot' if hsi_c>0 else ''}"><td class="name">恒生指数</td><td>{hk.get('hsi',{}).get('v','')}</td><td class="{'r' if hsi_c>0 else 'g'}">{fmt_pct(hsi_c)}</td></tr>
        <tr><td class="name">恒生科技</td><td>{hk.get('hstech',{}).get('v','')}</td><td class="{'r' if hstech_c>0 else 'g'}">{fmt_pct(hstech_c)}</td></tr>
        <tr class="grp"><td colspan="3">美股 <span class="st ovn">{ts} 收盘</span></td></tr>
        <tr class="{'hot' if dj_c>0 else ''}"><td class="name">道琼斯</td><td>{us.get('dj',{}).get('v','')}</td><td class="{'r' if dj_c>0 else 'g'}">{fmt_pct(dj_c)}</td></tr>
        <tr class="{'hot' if sp_c>0 else ''}"><td class="name">标普500</td><td>{us.get('sp',{}).get('v','')}</td><td class="{'r' if sp_c>0 else 'g'}">{fmt_pct(sp_c)}</td></tr>
        <tr><td class="name">纳斯达克</td><td>{us.get('nq',{}).get('v','')}</td><td class="{'r' if nq_c>0 else 'g'}">{fmt_pct(nq_c)}</td></tr>
      </tbody>
    </table>
    <div class="callout blue">
      {c['global_callout']}
    </div>
  </div>'''

    news_items = ''
    for n in c['news']:
        srcs = ''.join(f'<span class="src{" intl" if s in ["Reuters","Bloomberg","WSJ","FT","CNBC","Invezz","gatekeepers","convex","vittarthi","TSMC","Samsung"] else ""}">{s}</span>' for s in n['sources'])
        tag_text = {'a':'🔴 极重要','b':'🟠 重要','c':'🔵 关注'}.get(n['level'],'🔵 关注')
        news_items += f'''    <div class="news {n['level']}">
      <div class="news-top">
        <span class="tag">{tag_text}</span>
        {srcs}
      </div>
      <h3>{n['title']}</h3>
      <p>{n['body']}</p>
      <div class="impact">
        <b>{n['impact_title']}</b>{n['impact_body']}
      </div>
    </div>
'''
    news_sec = f'''  <div class="sec" id="sec-news">
    <div class="sec-head">
      <div class="sec-ico" style="background:#fff0e0">📰</div>
      <div class="sec-title">环球要闻 · 深度解读</div>
      <div class="sec-note">{len(c['news'])}条核心新闻</div>
    </div>
    <div class="news-legend">
      <span class="tag mini a">🔴 极重要</span>
      <span class="tag mini b">🟠 重要</span>
      <span class="tag mini c">🔵 关注</span>
    </div>
{news_items}  </div>'''

    dim_icons = ['📰','🔥','📊','🏛','💰']
    dim_cls = ['d1','d2','d3','d4','d5']
    dims = ''
    for i, dm in enumerate(c['five_dims']):
        pts = ''.join(f'<li>{p}</li>' for p in dm['points'])
        dims += f'''    <div class="dim {dim_cls[i]}">
      <div class="dim-h"><span class="e">{dim_icons[i]}</span><span class="t">{dm['name']}</span><span class="score">{dm['score']}</span></div>
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
    for h in c['heat']:
        fc = 'up' if h['dir']=='up' else 'down'
        vc = 'r' if h['dir']=='up' else 'g'
        heat_rows += f'    <div class="heat"><div class="heat-row"><div class="heat-name">{h["name"]}</div><div class="heat-track"><div class="heat-fill {fc}" style="width:{h["w"]}%"></div></div><div class="heat-val {vc}">{h["label"]}</div></div></div>\n'
    heat_sec = f'''  <div class="sec" id="sec-heat">
    <div class="sec-head">
      <div class="sec-ico" style="background:#fff0e0">🔥</div>
      <div class="sec-title">板块热力图</div>
      <div class="sec-note">红涨绿跌</div>
    </div>
{heat_rows}
    <div class="callout">
      {c['heat_callout']}
    </div>
  </div>'''

    chips = ''
    for s in c['stocks']:
        cv_c = s.get('cv_color','r')
        chips += f'      <div class="chip"><span class="cn">{s["name"]}</span><span class="{s["tag"]}">{s["tag_text"]}</span><span class="cv {cv_c}">{s["desc"]}</span></div>\n'
    stock_sec = f'''  <div class="sec" id="sec-stock">
    <div class="sec-head">
      <div class="sec-ico" style="background:#e2ecfd">⭐</div>
      <div class="sec-title">焦点个股与资金流</div>
      <div class="sec-note">A股 + 港股 + 海外</div>
    </div>
    <div class="chips">
{chips}    </div>
    <div class="callout blue">
      {c['stocks_callout']}
    </div>
  </div>'''

    commodity_sec = f'''  <div class="sec" id="sec-commodity">
    <div class="sec-head">
      <div class="sec-ico" style="background:#fef3c7">🪙</div>
      <div class="sec-title">大宗商品与汇率</div>
      <div class="sec-note">{ts} 数据</div>
    </div>
    <table class="tbl">
      <thead><tr><th>品种</th><th>最新</th><th>涨跌</th></tr></thead>
      <tbody>
        <tr class="{'hot' if gold_c>0 else ''}"><td class="name">现货黄金</td><td>~{com.get('gold',{}).get('v','')} 美元/盎司</td><td class="{'r' if gold_c>0 else 'g'}">{fmt_pct(gold_c)}</td></tr>
        <tr><td class="name">现货白银</td><td>~{com.get('silver',{}).get('v','')} 美元/盎司</td><td class="{'r' if com.get('silver',{}).get('c',0)>0 else 'g'}">{fmt_pct(com.get('silver',{}).get('c',0))}</td></tr>
        <tr class="{'hot' if brent_c>0 else ''}"><td class="name">布伦特原油</td><td>{com.get('brent',{}).get('v','')} 美元/桶</td><td class="{'r' if brent_c>0 else 'g'}">{fmt_pct(brent_c)}</td></tr>
      </tbody>
    </table>
    <div class="callout">
      {c['commodity_callout']}
    </div>
  </div>'''

    ind_cards = ''
    for ind in c['industries']:
        pts = ''.join(f'<li>{p}</li>' for p in ind['points'])
        ind_cards += f'''      <div class="gf-card {ind['status']}">
        <div class="gf-top">
          <span class="gf-ico">{ind['icon']}</span>
          <span class="gf-name">{ind['name']}</span>
          <span class="gf-status {ind['status']}">{ind['status_text']}</span>
        </div>
        <ul>{pts}</ul>
        <div class="gf-src">信源: {ind['sources']}</div>
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
      {c['industry_callout']}
    </div>
  </div>'''

    strat_pts = ''.join(f'<li>{p}</li>' for p in c['strategy'])
    dirs = ''.join(f'<span class="dir{" cool" if d.get("cool") else ""}">{d["text"]}</span>' for d in c['dirs'])
    risk_items = ''.join(f'<li>{r}</li>' for r in c['risks'])
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
    数据来源：路透社(Reuters) · 华尔街日报(WSJ) · 彭博(Bloomberg) · CNBC · 金融时报(FT) · 新华社 · 财联社 · 证券时报<br>
    报告时间：{td} 15:30（北京时间）<br><br>
    本报告基于公开信息整理，仅供研究参考，<b style="color:rgba(255,255,255,.6)">不构成任何投资建议</b>。<br>
    市场有风险，投资需谨慎。据此操作，风险自担。
  </div>'''

    # Read template for CSS+JS
    script_dir = os.path.dirname(os.path.abspath(__file__))
    tpl_path = os.path.join(script_dir, 'report_template.html')
    with open(tpl_path, 'r', encoding='utf-8') as f:
        tpl = f.read()

    head_end = tpl.find('</head>')
    head_part = tpl[:head_end + len('</head>')]
    body_start = tpl.find('<body>') + len('<body>')
    wrap_open = tpl[body_start:tpl.find('<div class="wrap">', body_start) + len('<div class="wrap">')]
    wrap_close = tpl[tpl.rfind('</div>', tpl.find('<div class="wrap">')):tpl.find('</body>')] + '\n</body>\n</html>'

    html = head_part + '\n' + wrap_open + '\n\n'
    html += hero + '\n\n' + nav + '\n\n'
    html += overview + '\n\n' + global_sec + '\n\n' + news_sec + '\n\n'
    html += five_sec + '\n\n' + heat_sec + '\n\n' + stock_sec + '\n\n'
    html += commodity_sec + '\n\n' + industry_sec + '\n\n' + strategy_sec + '\n\n'
    html += footer + '\n\n' + wrap_close
    return html

def main():
    print("=" * 60)
    print("每日全球股市报告生成器 - 增强版")
    print("=" * 60)
    data = fetch_data()
    if not data:
        print("错误: 无法获取市场数据"); sys.exit(1)
    content = gen_content(data)
    if not content:
        print("错误: 无法生成内容"); sys.exit(1)
    html = build_html(content, data)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    ts = today_str()
    out = os.path.join(script_dir, 'latest.html')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)
    arch = os.path.join(script_dir, 'archive')
    os.makedirs(arch, exist_ok=True)
    with open(os.path.join(arch, f'{ts}.html'), 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"✅ 报告已保存: {out}")
    print(f"✅ 归档: {os.path.join(arch, f'{ts}.html')}")
    print("=" * 60)

if __name__ == '__main__':
    main()
