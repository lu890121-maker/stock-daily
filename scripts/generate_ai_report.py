#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
使用 Qwen3.7 Plus API 生成高质量股市分析报告
采用完整 prompt + CSS 模板方式，确保 HTML 结构和样式始终正确
"""

import json
import os
import requests
from datetime import datetime

DATA_DIR = "deploy/data"
DEPLOY_DIR = "deploy"

# 完整的 CSS 样式模板（与本地报告完全一致）
CSS_TEMPLATE = """
  * { margin:0; padding:0; box-sizing:border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
    background: #eef1f6;
    color: #1a2233;
    line-height: 1.75;
    -webkit-font-smoothing: antialiased;
  }
  .wrap { max-width: 680px; margin: 0 auto; background: #fff; box-shadow: 0 2px 40px rgba(20,30,60,.08); }
  .hero {
    position: relative;
    background: linear-gradient(145deg, #131a2e 0%, #1e2a4a 45%, #2a1f45 100%);
    padding: 40px 26px 34px;
    color: #fff;
    overflow: hidden;
  }
  .hero::before {
    content:''; position:absolute; width:340px; height:340px; border-radius:50%;
    background: radial-gradient(circle, rgba(232,72,85,.32) 0%, transparent 68%);
    top:-150px; right:-110px;
  }
  .hero::after {
    content:''; position:absolute; width:280px; height:280px; border-radius:50%;
    background: radial-gradient(circle, rgba(64,158,255,.24) 0%, transparent 70%);
    bottom:-160px; left:-90px;
  }
  .hero-inner { position: relative; z-index: 2; }
  .hero .kicker {
    display:inline-block; font-size:11px; letter-spacing:3px; font-weight:600;
    background: rgba(255,255,255,.12); border:1px solid rgba(255,255,255,.2);
    padding:5px 13px; border-radius:20px; margin-bottom:16px;
  }
  .hero h1 { font-size:26px; font-weight:800; letter-spacing:-.6px; line-height:1.32; margin-bottom:10px; }
  .hero h1 em { font-style:normal; color:#ff9aa5; }
  .hero h1 i { font-style:normal; color:#7ee2a8; }
  .hero .sub { font-size:13.5px; color:rgba(255,255,255,.72); }
  .hero .datebar {
    margin-top:20px; padding-top:16px; border-top:1px solid rgba(255,255,255,.13);
    display:flex; justify-content:space-between; align-items:center; font-size:12.5px; color:rgba(255,255,255,.55);
  }
  .pulse { display:inline-flex; align-items:center; gap:6px; }
  .dot { width:7px; height:7px; border-radius:50%; background:#4ade80; box-shadow:0 0 0 3px rgba(74,222,128,.22); }
  .sec { padding: 30px 26px; border-bottom: 8px solid #f1f4f9; }
  .sec:last-of-type { border-bottom: none; }
  .sec-head { display:flex; align-items:center; gap:10px; margin-bottom:18px; }
  .sec-ico {
    width:32px; height:32px; border-radius:9px; display:flex; align-items:center; justify-content:center;
    font-size:16px; flex-shrink:0;
  }
  .sec-title { font-size:19px; font-weight:800; letter-spacing:-.3px; }
  .sec-note { font-size:12px; color:#8892a6; margin-left:auto; white-space:nowrap; }
  .idx-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:8px; }
  .idx {
    background:#fafbfd; border:1px solid #e8ecf3; border-radius:11px;
    padding:12px 9px 11px; position:relative; overflow:hidden;
  }
  .idx::before { content:''; position:absolute; left:0; top:0; bottom:0; width:3px; }
  .idx.up::before { background:#e84855; }
  .idx.down::before { background:#12a05c; }
  .idx .n { font-size:11px; color:#7c8698; margin-bottom:5px; font-weight:500; }
  .idx .v { font-size:15.5px; font-weight:800; letter-spacing:-.4px; font-variant-numeric:tabular-nums; }
  .idx .c { font-size:11.5px; font-weight:700; margin-top:3px; font-variant-numeric:tabular-nums; }
  .up .v, .up .c { color:#e84855; }
  .down .v, .down .c { color:#12a05c; }
  .statbar {
    display:grid; grid-template-columns:repeat(4,1fr); gap:1px;
    background:#e8ecf3; border-radius:11px; overflow:hidden; margin-top:12px;
  }
  .stat { background:#fff; padding:12px 6px; text-align:center; }
  .stat .k { font-size:10.5px; color:#8892a6; margin-bottom:4px; }
  .stat .v { font-size:15px; font-weight:800; font-variant-numeric:tabular-nums; }
  .r { color:#e84855; } .g { color:#12a05c; } .n0 { color:#1a2233; }
  .callout {
    margin-top:14px; background:linear-gradient(135deg,#fff6f6,#fff9f0);
    border:1px solid #ffdcd8; border-left:3px solid #e84855;
    border-radius:10px; padding:13px 15px; font-size:13.5px; color:#5a3a3a;
  }
  .callout b { color:#c9313e; }
  .callout.blue { background:linear-gradient(135deg,#f4f8ff,#f7f5ff); border-color:#d5e2fb; border-left-color:#3b6fe0; color:#2f3f5c; }
  .callout.blue b { color:#2456c4; }
  .news-legend {
    display:flex; flex-wrap:wrap; gap:12px; margin-bottom:16px;
    padding:10px 14px; background:#f7f9fc; border-radius:10px; font-size:12px; color:#5a6678;
  }
  .news-legend span { display:flex; align-items:center; gap:5px; }
  .tag { display:inline-block; font-size:11px; font-weight:700; padding:3px 10px; border-radius:20px; }
  .tag.a { background:#ffe4e6; color:#c9313e; }
  .tag.b { background:#fff0dc; color:#b8690f; }
  .tag.c { background:#e2ecfd; color:#2456c4; }
  .tag.mini { font-size:10px; padding:2px 8px; }
  .src { font-size:10px; padding:2px 8px; border-radius:12px; background:#eef2f8; color:#6b7688; }
  .src.intl { background:#eae4fb; color:#6a4bb8; }
  .news {
    position:relative; margin-bottom:16px; border-radius:12px; padding:16px 18px;
    border:1px solid transparent;
  }
  .news:last-child { margin-bottom:0; }
  .news.a { background:linear-gradient(135deg,#fff5f5,#fff0f0); border-color:#ffd5d5; }
  .news.b { background:linear-gradient(135deg,#fff9f0,#fff5e8); border-color:#ffe4c4; }
  .news.c { background:linear-gradient(135deg,#f5f8ff,#f0f5ff); border-color:#d0dff8; }
  .news-top { display:flex; flex-wrap:wrap; gap:6px; margin-bottom:10px; align-items:center; }
  .news h3 { font-size:15px; font-weight:800; line-height:1.5; margin-bottom:7px; letter-spacing:-.2px; }
  .news p { font-size:13px; line-height:1.85; color:#3d4660; margin-bottom:7px; }
  .news p:last-of-type { margin-bottom:0; }
  .hl { color:#e84855; font-weight:700; }
  .num { color:#e84855; font-weight:700; font-variant-numeric:tabular-nums; }
  .numg { color:#12a05c; font-weight:700; font-variant-numeric:tabular-nums; }
  .ph { color:#3b6fe0; font-weight:700; }
  .pl { color:#12a05c; font-weight:700; }
  .impact {
    margin-top:10px; padding:10px 13px; background:rgba(255,255,255,.65);
    border-radius:8px; border:1px solid rgba(0,0,0,.04);
    font-size:12.5px; color:#4a5568; line-height:1.8;
  }
  .dim {
    border-radius:12px; padding:16px 18px; margin-bottom:12px; position:relative; overflow:hidden;
  }
  .dim:last-child { margin-bottom:0; }
  .dim::before { content:''; position:absolute; left:0; top:0; bottom:0; width:3px; }
  .dim.d1::before { background:#e84855; }
  .dim.d2::before { background:#f0932b; }
  .dim.d3::before { background:#3b6fe0; }
  .dim.d4::before { background:#6a4bb8; }
  .dim.d5::before { background:#12a05c; }
  .dim.d1 { background:linear-gradient(135deg,#fff5f5,#fff0f0); }
  .dim.d2 { background:linear-gradient(135deg,#fff9f0,#fff5e8); }
  .dim.d3 { background:linear-gradient(135deg,#f5f8ff,#f0f5ff); }
  .dim.d4 { background:linear-gradient(135deg,#f8f5ff,#f5f0ff); }
  .dim.d5 { background:linear-gradient(135deg,#f0fff5,#e8fff0); }
  .dim-h { display:flex; align-items:center; gap:8px; margin-bottom:10px; }
  .dim-h .e { font-size:18px; }
  .dim-h .t { font-size:15px; font-weight:800; letter-spacing:-.2px; }
  .dim-h .score { margin-left:auto; font-size:11px; font-weight:600; color:#7c8698; }
  .dim ul { list-style:none; }
  .dim li {
    position:relative; padding:7px 0 7px 16px; font-size:13px; line-height:1.8;
    color:#3d4660; border-bottom:1px solid rgba(0,0,0,.04);
  }
  .dim li:last-child { border-bottom:none; }
  .dim li::before {
    content:''; position:absolute; left:0; top:15px; width:5px; height:5px;
    border-radius:50%; background:#b8c0ce;
  }
  .dim li b { color:#1a2233; }
  .heat { margin-bottom:10px; }
  .heat-row { display:flex; align-items:center; gap:8px; }
  .heat-name { width:90px; font-size:12.5px; font-weight:700; text-align:right; color:#3d4660; flex-shrink:0; }
  .heat-track { flex:1; height:22px; background:#f1f4f9; border-radius:11px; overflow:hidden; position:relative; }
  .heat-fill { height:100%; border-radius:11px; }
  .heat-fill.up { background:linear-gradient(90deg,#ffe4e6,#ff9aa5); }
  .heat-fill.down { background:linear-gradient(90deg,#d1fae5,#6ee7b7); }
  .heat-val { width:70px; font-size:11.5px; font-weight:700; }
  .heat-val.r { color:#e84855; }
  .heat-val.g { color:#12a05c; }
  .chips { display:grid; grid-template-columns:repeat(2,1fr); gap:8px; }
  .chip {
    display:flex; align-items:center; gap:8px;
    background:#fafbfd; border:1px solid #e8ecf3; border-radius:10px; padding:9px 12px;
  }
  .chip .cn { font-size:13px; font-weight:700; flex:1; }
  .chip .lim { font-size:10px; font-weight:700; padding:2px 7px; border-radius:10px; background:#ffe4e6; color:#c9313e; }
  .chip .tagi { font-size:10px; font-weight:700; padding:2px 7px; border-radius:10px; background:#eae4fb; color:#6a4bb8; }
  .chip .taga { font-size:10px; font-weight:700; padding:2px 7px; border-radius:10px; background:#e2ecfd; color:#2456c4; }
  .chip .limg { font-size:10px; font-weight:700; padding:2px 7px; border-radius:10px; background:#e8ecf3; color:#5a6678; }
  .chip .cv { font-size:12px; font-weight:800; font-variant-numeric:tabular-nums; }
  .tbl { width:100%; border-collapse:collapse; font-size:13px; }
  .tbl th { text-align:left; padding:10px 8px; font-size:11px; color:#8892a6; font-weight:600; border-bottom:1px solid #e8ecf3; }
  .tbl td { padding:10px 8px; border-bottom:1px solid #f1f4f9; }
  .tbl .name { font-weight:600; }
  .tbl .r { color:#e84855; font-weight:700; }
  .tbl .g { color:#12a05c; font-weight:700; }
  .tbl .n0 { color:#1a2233; font-weight:600; }
  .tbl tr.grp td { font-size:12px; font-weight:700; color:#5a6678; background:#f7f9fc; padding:8px; }
  .tbl tr.hot td { background:#fff9f0; }
  .tbl .st { font-size:10px; font-weight:600; padding:2px 8px; border-radius:10px; margin-left:6px; }
  .tbl .st.close { background:#e2ecfd; color:#2456c4; }
  .tbl .st.live { background:#fff0dc; color:#b8690f; }
  .tbl .st.ovn { background:#eae4fb; color:#6a4bb8; }
  .mkt-legend {
    display:flex; flex-wrap:wrap; gap:10px; margin-bottom:12px;
    padding:10px 14px; background:#f7f9fc; border-radius:10px; font-size:12px; color:#5a6678;
  }
  .mkt-legend span { display:flex; align-items:center; gap:5px; }
  .mkt-legend .dot { width:6px; height:6px; border-radius:50%; }
  .mkt-legend .dot.close { background:#3b6fe0; }
  .mkt-legend .dot.live { background:#f0932b; }
  .mkt-legend .dot.ovn { background:#6a4bb8; }
  .gf-grid { display:grid; grid-template-columns:repeat(2,1fr); gap:10px; }
  .gf-card {
    background:#fff; border:1px solid #e8ecf3; border-radius:12px;
    padding:14px 15px; position:relative; overflow:hidden;
  }
  .gf-card::before { content:''; position:absolute; left:0; top:0; bottom:0; width:3px; }
  .gf-card.hot::before { background:#e84855; }
  .gf-card.warm::before { background:#f0932b; }
  .gf-card.cool::before { background:#3b6fe0; }
  .gf-card.neut::before { background:#9aa6b8; }
  .gf-top { display:flex; align-items:center; gap:8px; margin-bottom:10px; }
  .gf-ico { font-size:20px; }
  .gf-name { font-size:14px; font-weight:800; flex:1; }
  .gf-status { font-size:10.5px; font-weight:700; padding:3px 9px; border-radius:12px; }
  .gf-status.hot { background:#ffe4e6; color:#c9313e; }
  .gf-status.warm { background:#fff0dc; color:#b8690f; }
  .gf-status.cool { background:#e2ecfd; color:#2456c4; }
  .gf-status.neut { background:#eef1f6; color:#5a6678; }
  .gf-card ul { list-style:none; }
  .gf-card li {
    position:relative; padding:6px 0 6px 14px; font-size:12.5px; line-height:1.7;
    color:#3d4660; border-bottom:1px solid rgba(0,0,0,.04);
  }
  .gf-card li:last-child { border-bottom:none; }
  .gf-card li::before {
    content:''; position:absolute; left:0; top:13px; width:4px; height:4px;
    border-radius:50%; background:#b8c0ce;
  }
  .gf-card li b { color:#1a2233; }
  .gf-card li .up { color:#e84855; font-weight:700; }
  .gf-card li .dn { color:#12a05c; font-weight:700; }
  .gf-src { font-size:10px; color:#9aa2b0; margin-top:7px; }
  @media (max-width:480px) { .gf-grid { grid-template-columns:1fr; } }
  .strat {
    background:linear-gradient(145deg,#1a2233,#2a3550); border-radius:14px;
    padding:22px 20px; color:#fff; margin-bottom:14px;
  }
  .strat-in h4 { font-size:16px; font-weight:800; margin-bottom:12px; }
  .strat-in ul { list-style:none; }
  .strat-in li {
    position:relative; padding:8px 0 8px 18px; font-size:13px; line-height:1.85;
    color:rgba(255,255,255,.82); border-bottom:1px solid rgba(255,255,255,.08);
  }
  .strat-in li:last-child { border-bottom:none; }
  .strat-in li::before {
    content:''; position:absolute; left:0; top:16px; width:6px; height:6px;
    border-radius:50%; background:#4ade80;
  }
  .strat-in li b { color:#fff; }
  .strat-in li .ph { color:#ff9aa5; font-weight:700; }
  .strat-in li .pl { color:#7ee2a8; font-weight:700; }
  .dirs { display:flex; flex-wrap:wrap; gap:8px; margin-top:14px; }
  .dir {
    font-size:12px; font-weight:700; padding:6px 13px; border-radius:20px;
    background:rgba(232,72,85,.2); color:#ff9aa5; border:1px solid rgba(232,72,85,.3);
  }
  .dir.cool {
    background:rgba(59,111,224,.15); color:#93b5ff; border-color:rgba(59,111,224,.25);
  }
  .risk {
    background:#fff5f5; border:1px solid #ffd5d5; border-radius:12px;
    padding:16px 18px;
  }
  .risk h4 { font-size:14px; font-weight:800; color:#c9313e; margin-bottom:10px; }
  .risk ul { list-style:none; }
  .risk li {
    position:relative; padding:7px 0 7px 18px; font-size:12.5px; line-height:1.8;
    color:#5a3a3a; border-bottom:1px solid rgba(201,49,62,.08);
  }
  .risk li:last-child { border-bottom:none; }
  .risk li::before {
    content:'⚠'; position:absolute; left:0; top:7px; font-size:10px;
  }
  .risk li b { color:#c9313e; }
  .foot {
    padding:28px 26px 34px; background:linear-gradient(145deg,#1a2233,#131a2e);
    color:rgba(255,255,255,.55); font-size:11.5px; line-height:1.8; text-align:center;
  }
  .foot .bk { font-size:14px; font-weight:800; color:rgba(255,255,255,.85); margin-bottom:10px; letter-spacing:1px; }
  .sec-nav {
    position:sticky; top:0; z-index:100;
    background:rgba(255,255,255,.95); backdrop-filter:blur(12px);
    border-bottom:1px solid #e8ecf3; padding:10px 26px;
    display:flex; align-items:center; gap:8px; overflow-x:auto;
  }
  .sec-nav::-webkit-scrollbar { display:none; }
  .sec-nav-label {
    font-size:12px; font-weight:700; color:#8892a6; white-space:nowrap;
    margin-right:8px; flex-shrink:0;
  }
  .sec-nav a {
    display:inline-block; font-size:12px; font-weight:600; color:#5a6678;
    padding:5px 14px; border-radius:20px; white-space:nowrap;
    background:#f1f4f9; text-decoration:none;
    flex-shrink:0;
  }
  .sec-nav a:hover { background:#e2ecfd; color:#2456c4; }
  @media (max-width:480px) {
    .idx-grid { grid-template-columns:repeat(2,1fr); }
    .chips { grid-template-columns:1fr; }
    .heat-name { width:78px; font-size:11.5px; }
    .heat-val { width:60px; font-size:12px; }
    .hero h1 { font-size:23px; }
  }
"""


def load_market_data():
    data_file = os.path.join(DATA_DIR, "market_data.json")
    with open(data_file, "r", encoding="utf-8") as f:
        return json.load(f)


def call_qwen_api(prompt, api_key):
    url = "https://coding-intl.dashscope.aliyuncs.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "qwen3.7-plus",
        "messages": [
            {"role": "system", "content": "你是一位专业的金融分析师，擅长撰写深度股市分析报告。请用通俗易懂的语言，结合数据进行分析。你只输出完整的HTML代码，不输出任何解释文字。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 16000
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=600)
        response.raise_for_status()
        result = response.json()
        if "choices" in result and len(result["choices"]) > 0:
            return result["choices"][0]["message"]["content"]
        else:
            print(f"API 返回格式异常: {result}")
            return None
    except Exception as e:
        print(f"调用 Qwen API 失败: {e}")
        return None


def generate_report(data, api_key):
    print("正在调用 Qwen3.7 Plus API 生成完整报告...")
    
    date_str = data["date"]
    a_stock = data.get("a_stock") or {}
    hk_stock = data.get("hk_stock") or {}
    us_stock = data.get("us_stock") or {}
    commodities = data.get("commodities") or {}
    forex = data.get("forex") or {}
    news_list = data.get("news") or []
    market_stats = data.get("market_stats") or {}
    sector_fund_flow = data.get("sector_fund_flow") or {}
    
    def fmt(d):
        if not d:
            return "数据暂缺"
        price = d.get("price", "N/A")
        pct = d.get("change_pct", 0)
        if pct is None:
            pct = 0
        return f"{price} ({pct:+.2f}%)"
    
    limit_up = market_stats.get("limit_up", 0)
    limit_down = market_stats.get("limit_down", 0)
    
    inflow_sectors = sector_fund_flow.get("inflow", [])
    outflow_sectors = sector_fund_flow.get("outflow", [])
    inflow_text = "\n".join([f"- {s['name']}: 主力净流入 {s['net_inflow']}亿" for s in inflow_sectors[:5]]) if inflow_sectors else "暂无数据"
    outflow_text = "\n".join([f"- {s['name']}: 主力净流出 {abs(s['net_inflow'])}亿" for s in outflow_sectors[:5]]) if outflow_sectors else "暂无数据"
    
    news_text = "\n".join([f"- {n.get('title', n.get('content', '')[:80])}" for n in news_list[:10]]) if news_list else "暂无新闻数据"
    
    prompt = f"""请基于以下 {date_str} 的市场数据，生成一份完整的每日股市分析报告 HTML。

## 市场数据

### A 股
- 上证指数: {fmt(a_stock.get('shanghai'))}
- 深证成指: {fmt(a_stock.get('shenzhen'))}
- 创业板指: {fmt(a_stock.get('chinext'))}
- 科创50: {fmt(a_stock.get('star50'))}

### 港股
- 恒生指数: {fmt(hk_stock.get('hsi'))}
- 恒生科技: {fmt(hk_stock.get('hstech'))}

### 美股（上一交易日）
- 道琼斯: {fmt(us_stock.get('dowjones'))}
- 纳斯达克: {fmt(us_stock.get('nasdaq'))}
- 标普500: {fmt(us_stock.get('sp500'))}

### 大宗商品
- 现货黄金: {fmt(commodities.get('gold'))}
- WTI原油: {fmt(commodities.get('oil'))}
- 现货白银: {fmt(commodities.get('silver'))}
- COMEX铜: {fmt(commodities.get('copper'))}

### 汇率与利率
- 美元指数: {fmt(forex.get('usd_index'))}
- 美元/离岸人民币: {fmt(forex.get('usdcnh'))}
- 美元/日元: {fmt(forex.get('usdjpy'))}
- 10年期美债收益率: {fmt(forex.get('us10y'))}

### 市场统计
- 涨停: {limit_up}家
- 跌停: {limit_down}家

### 板块资金流向
流入TOP5:
{inflow_text}

流出TOP5:
{outflow_text}

### 重要新闻
{news_text}

## 报告结构（必须包含以下全部板块）

1. **HERO 区域**：对仗标题（用em标红关键词、i标绿关键词）+ 副标题 + 日期栏
2. **导航栏**：sticky导航，快速跳转到各板块
3. **A股收盘速览**：四大指数卡片(idx-grid) + 统计栏(statbar) + 定性总结(callout)
4. **全球市场全景**：市场状态图例 + 数据表格(tbl) + 全球图景总结(callout blue)
5. **环球要闻（8-10条）**：三级重要性(news a/b/c) + 信源标签 + 标题 + 解读 + 影响分析
6. **五维度深度分析**：消息面(d1)/情绪面(d2)/技术面(d3)/政策面(d4)/资金面(d5)，每个dim包含要点列表+结论
7. **板块热力图**：领涨(heat-fill up)+领跌(heat-fill down)各5个
8. **焦点个股与资金流**：16个焦点个股卡片(chips) + 对比分析(callout blue)
9. **大宗商品与汇率**：数据表格(tbl) + 关键信号分析(callout)
10. **产业高频数据**：6个产业链卡片(gf-grid/gf-card)
11. **后市展望与操作策略**：strat卡片 + 方向标签(dirs) + 风险清单(risk)
12. **页脚**：数据来源 + 报告时间 + 免责声明

## CSS 样式要求

请使用以下CSS样式（红涨绿跌，max-width 680px）：

<style>
{CSS_TEMPLATE}
</style>

## HTML 结构要求

- 输出完整的HTML代码（从<!DOCTYPE html>到</html>）
- 使用UTF-8编码
- 所有section用sec类包裹
- 导航栏用sec-nav类
- 使用上述CSS中定义的所有类名
- 不要输出任何解释文字，只输出HTML代码

请直接输出完整的HTML代码。
"""
    
    ai_content = call_qwen_api(prompt, api_key)
    
    if ai_content:
        print("✓ AI 报告生成成功")
        # 清理可能的markdown代码块标记
        content = ai_content.strip()
        if content.startswith("```html"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        return content
    else:
        print("✗ AI 报告生成失败")
        return None


def save_report(html_content, date_str):
    latest_file = os.path.join(DEPLOY_DIR, "latest.html")
    with open(latest_file, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"✓ 报告已保存到 {latest_file}")
    
    archive_dir = os.path.join(DEPLOY_DIR, "archive")
    if not os.path.exists(archive_dir):
        os.makedirs(archive_dir)
    
    archive_file = os.path.join(archive_dir, f"{date_str}.html")
    with open(archive_file, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"✓ 报告已归档到 {archive_file}")


def main():
    print("=" * 50)
    print(f"开始生成 AI 分析报告 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    
    api_key = os.environ.get("QWEN_API_KEY")
    if not api_key:
        print("✗ 错误: 未设置 QWEN_API_KEY 环境变量")
        return False
    
    data = load_market_data()
    date_str = data["date"]
    print(f"✓ 数据加载成功: {date_str}")
    
    html_content = generate_report(data, api_key)
    
    if not html_content:
        print("✗ AI 报告生成失败")
        return False
    
    save_report(html_content, date_str)
    
    print("=" * 50)
    print("✓ AI 分析报告生成完成")
    print("=" * 50)
    return True


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
