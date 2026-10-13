#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日全球股市报告生成器 - 使用固定模板 + LLM 填充内容
"""

import os
import sys
import json
import requests
import akshare as ak
from datetime import datetime
import pytz

DASHSCOPE_API_KEY = os.environ.get('DASHSCOPE_API_KEY')
DASHSCOPE_API_URL = 'https://coding-intl.dashscope.aliyuncs.com/v1/chat/completions'
MODEL_NAME = 'qwen3.7-plus'

def get_today_str():
    beijing_tz = pytz.timezone('Asia/Shanghai')
    return datetime.now(beijing_tz).strftime('%Y-%m-%d')

def get_today_display():
    beijing_tz = pytz.timezone('Asia/Shanghai')
    today = datetime.now(beijing_tz)
    weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
    return f"{today.year}年{today.month}月{today.day}日 {weekdays[today.weekday()]}"

def fetch_all_data():
    """抓取所有市场数据"""
    data = {}
    
    # A股
    try:
        sh = ak.stock_zh_index_daily(symbol="sh000001").iloc[-2:]
        sz = ak.stock_zh_index_daily(symbol="sz399001").iloc[-2:]
        cy = ak.stock_zh_index_daily(symbol="sz399006").iloc[-2:]
        kc = ak.stock_zh_index_daily(symbol="sh000688").iloc[-2:]
        data['a_share'] = {
            'sh': {'close': float(sh.iloc[1]['close']), 'change': round((sh.iloc[1]['close']-sh.iloc[0]['close'])/sh.iloc[0]['close']*100, 2)},
            'sz': {'close': float(sz.iloc[1]['close']), 'change': round((sz.iloc[1]['close']-sz.iloc[0]['close'])/sz.iloc[0]['close']*100, 2)},
            'cy': {'close': float(cy.iloc[1]['close']), 'change': round((cy.iloc[1]['close']-cy.iloc[0]['close'])/cy.iloc[0]['close']*100, 2)},
            'kc': {'close': float(kc.iloc[1]['close']), 'change': round((kc.iloc[1]['close']-kc.iloc[0]['close'])/kc.iloc[0]['close']*100, 2)},
        }
        print(f"A股: 沪指{data['a_share']['sh']['close']:.0f}({data['a_share']['sh']['change']:+.2f}%)")
    except Exception as e:
        print(f"A股抓取失败: {e}")
        return None
    
    # 港股
    try:
        hs = ak.stock_hk_index_daily_sina(symbol="HSI").iloc[-2:]
        hst = ak.stock_hk_index_daily_sina(symbol="HSTECH").iloc[-2:]
        data['hk'] = {
            'hsi': {'close': float(hs.iloc[1]['close']), 'change': round((hs.iloc[1]['close']-hs.iloc[0]['close'])/hs.iloc[0]['close']*100, 2)},
            'hstech': {'close': float(hst.iloc[1]['close']), 'change': round((hst.iloc[1]['close']-hst.iloc[0]['close'])/hst.iloc[0]['close']*100, 2)},
        }
    except: pass
    
    # 美股
    try:
        dj = ak.index_us_stock_sina(symbol=".DJI").iloc[-2:]
        sp = ak.index_us_stock_sina(symbol=".INX").iloc[-2:]
        nq = ak.index_us_stock_sina(symbol=".IXIC").iloc[-2:]
        data['us'] = {
            'dj': {'close': float(dj.iloc[1]['close']), 'change': round((dj.iloc[1]['close']-dj.iloc[0]['close'])/dj.iloc[0]['close']*100, 2)},
            'sp': {'close': float(sp.iloc[1]['close']), 'change': round((sp.iloc[1]['close']-sp.iloc[0]['close'])/sp.iloc[0]['close']*100, 2)},
            'nq': {'close': float(nq.iloc[1]['close']), 'change': round((nq.iloc[1]['close']-nq.iloc[0]['close'])/nq.iloc[0]['close']*100, 2)},
        }
    except: pass
    
    # 大宗商品
    try:
        gold = ak.futures_foreign_hist(symbol="XAU").iloc[-2:]
        oil = ak.futures_foreign_hist(symbol="B").iloc[-2:]
        data['commodity'] = {
            'gold': {'price': float(gold.iloc[1]['收盘价']), 'change': round((gold.iloc[1]['收盘价']-gold.iloc[0]['收盘价'])/gold.iloc[0]['收盘价']*100, 2)},
            'brent': {'price': float(oil.iloc[1]['收盘价']), 'change': round((oil.iloc[1]['收盘价']-oil.iloc[0]['收盘价'])/oil.iloc[0]['收盘价']*100, 2)},
        }
    except: pass
    
    return data

def generate_content_json(market_data):
    """让 LLM 生成结构化的 JSON 内容"""
    today_display = get_today_display()
    
    prompt = f"""你是专业财经分析师。根据以下市场数据，生成今日股市报告的各部分内容。

日期：{today_display}
数据：{json.dumps(market_data, ensure_ascii=False)}

请严格按以下 JSON 格式输出（不要有任何其他文字）：

{{
  "hero_title": "主标题（20字内，用·分隔两个要点，可用<em>和<i>标签强调）",
  "hero_sub": "副标题（一句话概括关键数据）",
  "overview_callout": "A股定性总结段落（含<b>标签）",
  "global_callout": "全球市场总结段落",
  "news": [
    {{
      "level": "a或b或c",
      "sources": ["Reuters", "财联社"],
      "title": "新闻标题",
      "body": "新闻正文（可用<span class=\"num\">等标签）",
      "impact_title": "说人话：",
      "impact_body": "影响分析"
    }}
  ],
  "five_dims": [
    {{
      "name": "消息面",
      "score": "利空主导 ★★☆☆☆",
      "points": ["要点1", "要点2", "要点3", "要点4", "结论"]
    }}
  ],
  "heat_sectors": [
    {{"name": "板块名", "direction": "up或down", "width": 95, "label": "说明"}}
  ],
  "heat_callout": "热力图总结",
  "stocks": [
    {{"name": "股票名", "tag_type": "lim/taga/limg", "tag_text": "标签", "desc": "说明"}}
  ],
  "stocks_callout": "个股总结",
  "commodity_callout": "大宗总结",
  "industries": [
    {{
      "icon": "",
      "name": "产业名",
      "status_class": "hot/warm/cool/neut",
      "status_text": "状态",
      "points": ["要点1", "要点2", ...],
      "sources": "信源列表"
    }}
  ],
  "industry_callout": "产业总结",
  "strategy_points": ["短期判断", "中期判断", "长期判断", "风险点"],
  "strategy_dirs": [
    {{"text": "方向", "class": ""或"cool"}}
  ],
  "risks": ["风险1", "风险2", ...]
}}

要求：
- news 至少9条，分4条a级+3条b级+2条c级
- five_dims 正好5个维度
- heat_sectors 正好10个板块
- stocks 正好16只个股
- industries 正好6个产业卡片
- strategy_dirs 8个方向
- risks 6条风险
- 语言犀利客观，不要套话
- 所有数据基于我提供的市场数据"""

    try:
        resp = requests.post(DASHSCOPE_API_URL, headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {DASHSCOPE_API_KEY}'
        }, json={
            'model': MODEL_NAME,
            'messages': [{'role': 'user', 'content': prompt}],
            'temperature': 0.7,
            'max_tokens': 8000
        }, timeout=180)
        resp.raise_for_status()
        result = resp.json()['choices'][0]['message']['content'].strip()
        
        # 清理 markdown 标记
        if result.startswith('```json'): result = result[7:]
        if result.startswith('```'): result = result[3:]
        if result.endswith('```'): result = result[:-3]
        
        content = json.loads(result.strip())
        print("✅ 内容生成成功")
        return content
    except Exception as e:
        print(f"❌ 内容生成失败: {e}")
        return None

def build_html(content):
    """用固定模板构建完整 HTML"""
    d = get_today_display()
    ds = get_today_str()
    
    # Hero
    hero = f'''  <div class="hero">
    <div class="hero-inner">
      <div class="kicker">DAILY GLOBAL MARKET WATCH</div>
      <h1>{content['hero_title']}</h1>
      <div class="sub">{content['hero_sub']}</div>
      <div class="datebar">
        <span>{d} · 收盘全维度分析</span>
        <span class="pulse"><span class="dot"></span> LIVE</span>
      </div>
    </div>
  </div>'''
    
    # Overview (简化版，不含具体指数值，因为akshare可能抓不到)
    overview = '''  <div class="sec" id="sec-overview">
    <div class="sec-head">
      <div class="sec-ico" style="background:#ffe4e6">📈</div>
      <div class="sec-title">A股收盘速览</div>
      <div class="sec-note">收盘数据</div>
    </div>
    <div class="callout">
      ''' + content['overview_callout'] + '''
    </div>
  </div>'''
    
    # Global
    global_sec = '''  <div class="sec" id="sec-global">
    <div class="sec-head">
      <div class="sec-ico" style="background:#e2ecfd">🌏</div>
      <div class="sec-title">全球市场全景</div>
    </div>
    <div class="callout blue">
      ''' + content['global_callout'] + '''
    </div>
  </div>'''
    
    # News
    news_items = ''
    for n in content['news']:
        src_tags = ''.join(f'<span class="src{" intl" if s in ["Reuters","Bloomberg","WSJ","FT","CNBC","Invezz","gatekeepers","convex","vittarthi","TSMC","Samsung"] else ""}">{s}</span>' for s in n['sources'])
        news_items += f'''    <div class="news {n['level']}">
      <div class="news-top">
        <span class="tag">{"🔴 极重要" if n['level']=='a' else "🟠 重要" if n['level']=='b' else "🔵 关注"}</span>
        {src_tags}
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
      <div class="sec-note">{len(content['news'])}条核心新闻</div>
    </div>
    <div class="news-legend">
      <span class="tag mini a">🔴 极重要</span>
      <span class="tag mini b">🟠 重要</span>
      <span class="tag mini c">🔵 关注</span>
    </div>
{news_items}  </div>'''
    
    # Five dimensions
    dim_icons = ['📰','','📊','🏛','']
    dim_classes = ['d1','d2','d3','d4','d5']
    dims = ''
    for i, dm in enumerate(content['five_dims']):
        pts = ''.join(f'<li><b>{p.split("：")[0]}：</b>{p.split("：",1)[1] if "：" in p else p}</li>' for p in dm['points'])
        dims += f'''    <div class="dim {dim_classes[i]}">
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
    
    # Heatmap
    heat_rows = ''
    for h in content['heat_sectors']:
        fill_class = 'up' if h['direction']=='up' else 'down'
        val_class = 'r' if h['direction']=='up' else 'g'
        heat_rows += f'    <div class="heat"><div class="heat-row"><div class="heat-name">{h["name"]}</div><div class="heat-track"><div class="heat-fill {fill_class}" style="width:{h["width"]}%"></div></div><div class="heat-val {val_class}">{h["label"]}</div></div></div>\n'
    
    heat_sec = f'''  <div class="sec" id="sec-heat">
    <div class="sec-head">
      <div class="sec-ico" style="background:#fff0e0">🔥</div>
      <div class="sec-title">板块热力图</div>
      <div class="sec-note">红涨绿跌</div>
    </div>
{heat_rows}
    <div class="callout">
      {content['heat_callout']}
    </div>
  </div>'''
    
    # Stocks
    chips = ''
    for s in content['stocks']:
        tag_cls = {'lim':'lim','taga':'taga','tagi':'tagi','limg':'limg'}.get(s['tag_type'],'limg')
        cv_cls = 'r' if s['tag_type'] in ['lim','taga','tagi'] else 'g'
        chips += f'      <div class="chip"><span class="cn">{s["name"]}</span><span class="{tag_cls}">{s["tag_text"]}</span><span class="cv {cv_cls}">{s["desc"]}</span></div>\n'
    
    stock_sec = f'''  <div class="sec" id="sec-stock">
    <div class="sec-head">
      <div class="sec-ico" style="background:#e2ecfd">⭐</div>
      <div class="sec-title">焦点个股与资金流</div>
      <div class="sec-note">A股 + 港股 + 海外</div>
    </div>
    <div class="chips">
{chips}    </div>
    <div class="callout blue">
      {content['stocks_callout']}
    </div>
  </div>'''
    
    # Commodity (简化表格)
    commodity_sec = f'''  <div class="sec" id="sec-commodity">
    <div class="sec-head">
      <div class="sec-ico" style="background:#fef3c7">🪙</div>
      <div class="sec-title">大宗商品与汇率</div>
    </div>
    <div class="callout">
      {content['commodity_callout']}
    </div>
  </div>'''
    
    # Industries
    ind_cards = ''
    for ind in content['industries']:
        pts = ''.join(f'<li>{p}</li>' for p in ind['points'])
        ind_cards += f'''      <div class="gf-card {ind['status_class']}">
        <div class="gf-top">
          <span class="gf-ico">{ind['icon']}</span>
          <span class="gf-name">{ind['name']}</span>
          <span class="gf-status {ind['status_class']}">{ind['status_text']}</span>
        </div>
        <ul>{pts}</ul>
        <div class="gf-src">信源: {ind['sources']}</div>
      </div>
'''
    
    industry_sec = f'''  <div class="sec" id="sec-grassroots">
    <div class="sec-head">
      <div class="sec-ico" style="background:#f3fbf6"></div>
      <div class="sec-title">产业高频数据 · 机构/大户必读</div>
      <div class="sec-note">产业链一线追踪</div>
    </div>
    <div class="gf-grid">
{ind_cards}    </div>
    <div class="callout blue">
      {content['industry_callout']}
    </div>
  </div>'''
    
    # Strategy
    strat_pts = ''.join(f'<li><b>{p.split("：")[0]}：</b>{p.split("：",1)[1] if "：" in p else p}</li>' for p in content['strategy_points'])
    dirs = ''.join(f'<span class="dir{" cool" if d.get("class")=="cool" else ""}">{d["text"]}</span>' for d in content['strategy_dirs'])
    risk_items = ''.join(f'<li><b>{r.split("——")[0]}</b>{r.split("——",1)[1] if "——" in r else ""}</li>' for r in content['risks'])
    
    strategy_sec = f'''  <div class="sec" id="sec-strategy">
    <div class="sec-head">
      <div class="sec-ico" style="background:#ffe4e6">🧭</div>
      <div class="sec-title">后市展望与操作策略</div>
    </div>
    <div class="strat">
      <div class="strat-in">
        <h4> 核心判断</h4>
        <ul>{strat_pts}</ul>
        <div class="dirs">{dirs}</div>
      </div>
    </div>
    <div class="risk">
      <h4>⚠ 风险清单（按紧迫度排序）</h4>
      <ul>{risk_items}</ul>
    </div>
  </div>'''
    
    # Footer
    footer = f'''  <div class="foot">
    <div class="bk">每日全球股市观察</div>
    数据来源：路透社(Reuters) · 华尔街日报(WSJ) · 彭博(Bloomberg) · CNBC · 金融时报(FT) · 新华社 · 财联社 · 证券时报<br>
    报告时间：{d} 15:30（北京时间）<br><br>
    本报告基于公开信息整理，仅供研究参考，<b style="color:rgba(255,255,255,.6)">不构成任何投资建议</b>。<br>
    市场有风险，投资需谨慎。据此操作，风险自担。
  </div>'''
    
    # Read template CSS+JS+structure
    script_dir = os.path.dirname(os.path.abspath(__file__))
    tpl_path = os.path.join(script_dir, 'report_template.html')
    with open(tpl_path, 'r', encoding='utf-8') as f:
        tpl = f.read()
    
    # Extract head (CSS+JS) and wrap start/end
    head_end = tpl.find('</head>')
    body_start = tpl.find('<body>') + len('<body>')
    wrap_start = tpl.find('<div class="wrap">', body_start)
    wrap_end = tpl.rfind('</div>', wrap_start)
    body_end = tpl.find('</body>')
    
    head_part = tpl[:head_end + len('</head>')]
    wrap_open = tpl[body_start:wrap_start + len('<div class="wrap">')]
    wrap_close = tpl[wrap_end:body_end] + tpl[body_end:]
    
    # Assemble
    html = head_part + '\n' + wrap_open + '\n\n'
    html += hero + '\n\n'
    html += '''  <!-- 板块导航 -->
  <div class="sec-nav">
    <span class="sec-nav-label">快速跳转：</span>
    <a href="#sec-overview">📈 A股速览</a>
    <a href="#sec-global"> 全球市场</a>
    <a href="#sec-news">📰 环球要闻</a>
    <a href="#sec-five"> 五维分析</a>
    <a href="#sec-heat">🔥 板块热力</a>
    <a href="#sec-stock">💰 焦点个股</a>
    <a href="#sec-commodity">🛢️ 大宗商品</a>
    <a href="#sec-grassroots">🏭 产业高频</a>
    <a href="#sec-strategy"> 策略研判</a>
  </div>

'''
    html += overview + '\n\n' + global_sec + '\n\n' + news_sec + '\n\n'
    html += five_sec + '\n\n' + heat_sec + '\n\n' + stock_sec + '\n\n'
    html += commodity_sec + '\n\n' + industry_sec + '\n\n' + strategy_sec + '\n\n'
    html += footer + '\n\n'
    html += wrap_close
    
    return html

def main():
    print("=" * 60)
    print("每日全球股市报告生成器")
    print("=" * 60)
    
    if not DASHSCOPE_API_KEY:
        print("错误: 未设置 DASHSCOPE_API_KEY"); sys.exit(1)
    
    market_data = fetch_all_data()
    if not market_data:
        print("错误: 无法获取市场数据"); sys.exit(1)
    
    content = generate_content_json(market_data)
    if not content:
        print("错误: 无法生成内容"); sys.exit(1)
    
    html = build_html(content)
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    today_str = get_today_str()
    
    out = os.path.join(script_dir, 'latest.html')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)
    
    arch_dir = os.path.join(script_dir, 'archive')
    os.makedirs(arch_dir, exist_ok=True)
    with open(os.path.join(arch_dir, f'{today_str}.html'), 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"✅ 报告已保存: {out}")
    print("=" * 60)

if __name__ == '__main__':
    main()
