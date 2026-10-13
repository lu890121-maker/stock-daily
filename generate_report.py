#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日全球股市报告生成器
用于 GitHub Actions 自动化
"""

import os
import sys
import json
import requests
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
import pytz
import re

# 配置
DASHSCOPE_API_KEY = os.environ.get('DASHSCOPE_API_KEY')
DASHSCOPE_API_URL = 'https://coding-intl.dashscope.aliyuncs.com/v1/chat/completions'
MODEL_NAME = 'qwen3.7-plus'

def get_today_str():
    """获取今天的日期字符串"""
    beijing_tz = pytz.timezone('Asia/Shanghai')
    today = datetime.now(beijing_tz)
    return today.strftime('%Y-%m-%d')

def get_today_display():
    """获取今天的显示格式"""
    beijing_tz = pytz.timezone('Asia/Shanghai')
    today = datetime.now(beijing_tz)
    weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
    weekday = weekdays[today.weekday()]
    return today.strftime(f'%Y年{today.month}月{today.day}日 {weekday}')

def fetch_a_share_data():
    """抓取A股数据"""
    print("正在抓取A股数据...")
    try:
        # 上证指数
        sh_index = ak.stock_zh_index_daily(symbol="sh000001")
        sh_latest = sh_index.iloc[-1]
        
        # 深证成指
        sz_index = ak.stock_zh_index_daily(symbol="sz399001")
        sz_latest = sz_index.iloc[-1]
        
        # 创业板指
        cy_index = ak.stock_zh_index_daily(symbol="sz399006")
        cy_latest = cy_index.iloc[-1]
        
        # 科创50
        kc_index = ak.stock_zh_index_daily(symbol="sh000688")
        kc_latest = kc_index.iloc[-1]
        
        data = {
            'shanghai': {
                'close': float(sh_latest['close']),
                'change': float(sh_latest['close'] - sh_index.iloc[-2]['close']) / float(sh_index.iloc[-2]['close']) * 100
            },
            'shenzhen': {
                'close': float(sz_latest['close']),
                'change': float(sz_latest['close'] - sz_index.iloc[-2]['close']) / float(sz_index.iloc[-2]['close']) * 100
            },
            'chinext': {
                'close': float(cy_latest['close']),
                'change': float(cy_latest['close'] - cy_index.iloc[-2]['close']) / float(cy_index.iloc[-2]['close']) * 100
            },
            'star50': {
                'close': float(kc_latest['close']),
                'change': float(kc_latest['close'] - kc_index.iloc[-2]['close']) / float(kc_index.iloc[-2]['close']) * 100
            }
        }
        
        print(f"A股数据抓取成功: 沪指 {data['shanghai']['close']:.2f} ({data['shanghai']['change']:+.2f}%)")
        return data
    except Exception as e:
        print(f"A股数据抓取失败: {e}")
        return None

def fetch_hk_data():
    """抓取港股数据"""
    print("正在抓取港股数据...")
    try:
        # 恒生指数
        hs_index = ak.stock_hk_index_daily_sina(symbol="HSI")
        hs_latest = hs_index.iloc[-1]
        
        data = {
            'hangseng': {
                'close': float(hs_latest['close']),
                'change': float(hs_latest['close'] - hs_index.iloc[-2]['close']) / float(hs_index.iloc[-2]['close']) * 100
            }
        }
        
        print(f"港股数据抓取成功: 恒指 {data['hangseng']['close']:.2f} ({data['hangseng']['change']:+.2f}%)")
        return data
    except Exception as e:
        print(f"港股数据抓取失败: {e}")
        return None

def fetch_us_data():
    """抓取美股数据（上一个交易日）"""
    print("正在抓取美股数据...")
    try:
        # 道琼斯
        dj_index = ak.index_us_stock_sina(symbol=".DJI")
        dj_latest = dj_index.iloc[-1]
        
        # 标普500
        sp_index = ak.index_us_stock_sina(symbol=".INX")
        sp_latest = sp_index.iloc[-1]
        
        # 纳斯达克
        nq_index = ak.index_us_stock_sina(symbol=".IXIC")
        nq_latest = nq_index.iloc[-1]
        
        data = {
            'dow': {
                'close': float(dj_latest['close']),
                'change': float(dj_latest['close'] - dj_index.iloc[-2]['close']) / float(dj_index.iloc[-2]['close']) * 100
            },
            'sp500': {
                'close': float(sp_latest['close']),
                'change': float(sp_latest['close'] - sp_index.iloc[-2]['close']) / float(sp_index.iloc[-2]['close']) * 100
            },
            'nasdaq': {
                'close': float(nq_latest['close']),
                'change': float(nq_latest['close'] - nq_index.iloc[-2]['close']) / float(nq_index.iloc[-2]['close']) * 100
            }
        }
        
        print(f"美股数据抓取成功: 道指 {data['dow']['close']:.2f} ({data['dow']['change']:+.2f}%)")
        return data
    except Exception as e:
        print(f"美股数据抓取失败: {e}")
        return None

def fetch_commodity_data():
    """抓取大宗商品数据"""
    print("正在抓取大宗商品数据...")
    try:
        # 黄金现货
        gold = ak.futures_foreign_hist(symbol="XAU")
        gold_latest = gold.iloc[-1]
        
        # 布伦特原油
        oil = ak.futures_foreign_hist(symbol="B")
        oil_latest = oil.iloc[-1]
        
        data = {
            'gold': {
                'price': float(gold_latest['收盘价']),
                'change': float(gold_latest['收盘价'] - gold.iloc[-2]['收盘价']) / float(gold.iloc[-2]['收盘价']) * 100
            },
            'brent': {
                'price': float(oil_latest['收盘价']),
                'change': float(oil_latest['收盘价'] - oil.iloc[-2]['收盘价']) / float(oil.iloc[-2]['收盘价']) * 100
            }
        }
        
        print(f"大宗商品数据抓取成功: 黄金 {data['gold']['price']:.2f} ({data['gold']['change']:+.2f}%)")
        return data
    except Exception as e:
        print(f"大宗商品数据抓取失败: {e}")
        return None

def generate_report_content(market_data):
    """使用通义千问生成报告内容"""
    print("正在生成报告内容...")
    
    # 构建 prompt
    today_display = get_today_display()
    
    prompt = f"""你是一位专业的财经分析师，请根据以下市场数据生成一份每日全球股市观察报告。

今天的日期：{today_display}

市场数据：
{json.dumps(market_data, ensure_ascii=False, indent=2)}

请生成以下内容（用中文）：

1. **报告标题**（一句话概括今日市场特点，20字以内）

2. **核心摘要**（3-5句话概括今日市场主要特点，100字左右）

3. **A股收盘速览**（200字左右，分析沪指、深成指、创业板、科创50的表现，成交量，涨跌家数等）

4. **全球市场全景**（300字左右，分析港股、美股、欧股、日韩等主要市场表现，突出亮点和风险点）

5. **环球要闻·深度解读**（3-5条重要新闻，每条100字左右，包含新闻事件和你的专业解读）

6. **五维度深度拆解**（从消息面、情绪面、技术面、政策面、资金面五个维度分析，每个维度100字左右）

7. **板块热力图**（列出今日涨幅前5和跌幅前5的板块，每个板块一句话点评）

8. **焦点个股与资金流**（列出5-8只今日最受关注的个股，包括A股、港股、美股，每只股票一句话点评）

9. **大宗商品与汇率**（分析黄金、原油、美元、人民币等主要品种走势，150字左右）

10. **产业高频数据**（选择2-3个重点产业链，分析最新动态，每个产业链150字左右）

11. **后市展望与操作策略**（短期、中期、长期判断，以及风险提示，300字左右）

要求：
- 语言风格：客观中立，可以带一点犀利点评，不要套话
- 数据准确：所有数据必须基于我提供的市场数据
- 逻辑清晰：每个分析都要有因果关系
- 全球视角：用全球市场对比来评价A股表现

请直接输出完整的报告内容，我会将其嵌入到HTML模板中。"""

    try:
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {DASHSCOPE_API_KEY}'
        }
        
        data = {
            'model': MODEL_NAME,
            'messages': [
                {'role': 'user', 'content': prompt}
            ],
            'temperature': 0.7,
            'max_tokens': 4000
        }
        
        response = requests.post(DASHSCOPE_API_URL, headers=headers, json=data, timeout=120)
        response.raise_for_status()
        
        result = response.json()
        content = result['choices'][0]['message']['content']
        
        print("报告内容生成成功")
        return content
    except Exception as e:
        print(f"报告内容生成失败: {e}")
        return None

def generate_html(report_content, market_data):
    """生成HTML报告"""
    print("正在生成HTML...")
    
    today_str = get_today_str()
    today_display = get_today_display()
    
    # 读取HTML模板（修正路径）
    script_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(script_dir, 'latest.html')
    with open(template_path, 'r', encoding='utf-8') as f:
        template = f.read()
    
    # 这里应该解析 report_content 并替换模板中的占位符
    # 但为了简化，我们先创建一个简化的HTML
    
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>每日全球股市观察 | {today_display}</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
    background: #eef1f6;
    color: #1a2233;
    line-height: 1.75;
  }}
  .wrap {{ max-width: 680px; margin: 0 auto; background: #fff; box-shadow: 0 2px 40px rgba(20,30,60,.08); }}
  .hero {{
    position: relative;
    background: linear-gradient(145deg, #131a2e 0%, #1e2a4a 45%, #2a1f45 100%);
    padding: 40px 26px 34px;
    color: #fff;
  }}
  .hero h1 {{ font-size:26px; font-weight:800; line-height:1.4; margin-bottom:10px; }}
  .hero .sub {{ font-size:13.5px; color:rgba(255,255,255,.72); margin-top:10px; }}
  .content {{ padding: 30px 26px; }}
  .content h2 {{ font-size:20px; font-weight:800; margin:30px 0 15px; color:#1a2233; }}
  .content h3 {{ font-size:16px; font-weight:700; margin:20px 0 10px; color:#2d3748; }}
  .content p {{ font-size:14px; line-height:1.8; color:#4a5568; margin-bottom:15px; }}
  .content ul {{ margin:10px 0 15px 20px; }}
  .content li {{ font-size:14px; line-height:1.8; color:#4a5568; margin-bottom:8px; }}
  .foot {{
    padding:28px 26px; background:#1a2233;
    color:rgba(255,255,255,.55); font-size:11.5px; text-align:center;
  }}
</style>
</head>
<body>
<div class="wrap">
  <div class="hero">
    <h1>每日全球股市观察</h1>
    <div class="sub">{today_display}</div>
  </div>
  <div class="content">
    <pre style="white-space: pre-wrap; font-family: inherit;">{report_content}</pre>
  </div>
  <div class="foot">
    数据来源：新浪财经 · 东方财富 · 路透社 · 彭博<br>
    报告时间：{today_display} 15:30（北京时间）<br>
    本报告基于公开信息整理，仅供研究参考，不构成任何投资建议。
  </div>
</div>
</body>
</html>"""
    
    print("HTML生成成功")
    return html

def main():
    """主函数"""
    print("=" * 60)
    print("每日全球股市报告生成器")
    print("=" * 60)
    
    # 检查环境变量
    if not DASHSCOPE_API_KEY:
        print("错误: 未设置 DASHSCOPE_API_KEY 环境变量")
        sys.exit(1)
    
    # 抓取市场数据
    market_data = {}
    
    a_share_data = fetch_a_share_data()
    if a_share_data:
        market_data['a_share'] = a_share_data
    
    hk_data = fetch_hk_data()
    if hk_data:
        market_data['hk'] = hk_data
    
    us_data = fetch_us_data()
    if us_data:
        market_data['us'] = us_data
    
    commodity_data = fetch_commodity_data()
    if commodity_data:
        market_data['commodity'] = commodity_data
    
    if not market_data:
        print("错误: 无法获取任何市场数据")
        sys.exit(1)
    
    # 生成报告内容
    report_content = generate_report_content(market_data)
    if not report_content:
        print("错误: 无法生成报告内容")
        sys.exit(1)
    
    # 生成HTML
    html = generate_html(report_content, market_data)
    
    # 保存HTML文件（修正路径）
    script_dir = os.path.dirname(os.path.abspath(__file__))
    today_str = get_today_str()
    output_file = os.path.join(script_dir, 'latest.html')
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)
    
    # 同时保存到归档
    archive_dir = os.path.join(script_dir, 'archive')
    if not os.path.exists(archive_dir):
        os.makedirs(archive_dir)
    archive_file = os.path.join(archive_dir, f'{today_str}.html')
    with open(archive_file, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"报告已保存到: {output_file}")
    print(f"归档文件: {archive_file}")
    print("=" * 60)

if __name__ == '__main__':
    main()
