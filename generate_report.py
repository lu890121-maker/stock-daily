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

def generate_html_report(market_data):
    """使用通义千问生成完整的 HTML 报告"""
    print("正在生成 HTML 报告...")
    
    today_display = get_today_display()
    today_str = get_today_str()
    
    # 读取模板文件作为参考
    script_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(script_dir, 'report_template.html')
    
    template_content = ""
    if os.path.exists(template_path):
        with open(template_path, 'r', encoding='utf-8') as f:
            template_content = f.read()
    
    prompt = f"""你是一位专业的财经分析师和前端开发工程师。请根据以下市场数据，生成一份完整的 HTML 格式的每日全球股市观察报告。

今天的日期：{today_display}

市场数据：
{json.dumps(market_data, ensure_ascii=False, indent=2)}

要求：
1. 输出完整的 HTML 文档（包含 <!DOCTYPE html>、<html>、<head>、<body> 等所有标签）
2. 保持以下结构和样式：
   - Hero 区域：渐变背景、装饰圆圈、标题、副标题、日期栏
   - 板块导航：sticky 导航栏，包含9个锚点链接
   - A股收盘速览：4个指数卡片 + 统计栏 + callout 总结
   - 全球市场全景：表格展示各市场数据 + callout 分析
   - 环球要闻：9条新闻，分极重要（红色）/重要（橙色）/关注（蓝色）三级，每条包含信源标签、标题、正文、影响分析
   - 五维度深度拆解：消息面/情绪面/技术面/政策面/资金面，每个维度有标题、评分、要点列表
   - 板块热力图：10个板块的热力条，红色表示上涨，绿色表示下跌
   - 焦点个股：16只个股的卡片网格（2列），包含标签和涨跌颜色
   - 大宗商品与汇率：表格展示 + callout 分析
   - 产业高频数据：6个产业卡片（2列网格），每个卡片有图标、标题、状态标签、要点列表、信源
   - 后市展望与操作策略：策略建议（深色背景）+ 风险清单（红色背景）
   - Footer：数据来源、报告时间、免责声明

3. 使用以下 CSS 类名和样式（保持与模板一致）：
   - 颜色：红色 #e84855（涨），绿色 #12a05c（跌）
   - 卡片样式：.idx（指数卡片）、.chip（个股卡片）、.gf-card（产业卡片）
   - 标签样式：.tag.a（极重要）、.tag.b（重要）、.tag.c（关注）
   - 热力条：.heat-row、.heat-fill.up（红色）、.heat-fill.down（绿色）

4. 内容要求：
   - 语言风格：客观中立，可以带一点犀利点评，不要套话
   - 数据准确：所有数据必须基于我提供的市场数据
   - 逻辑清晰：每个分析都要有因果关系
   - 全球视角：用全球市场对比来评价A股表现
   - 每条新闻都要有"影响分析"（<div class="impact">）

5. 直接输出完整的 HTML 代码，不要有任何解释文字或 markdown 标记。

请生成完整的 HTML 报告："""

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
            'max_tokens': 8000
        }
        
        response = requests.post(DASHSCOPE_API_URL, headers=headers, json=data, timeout=180)
        response.raise_for_status()
        
        result = response.json()
        html_content = result['choices'][0]['message']['content']
        
        # 清理可能的 markdown 标记
        html_content = html_content.strip()
        if html_content.startswith('```html'):
            html_content = html_content[7:]
        if html_content.startswith('```'):
            html_content = html_content[3:]
        if html_content.endswith('```'):
            html_content = html_content[:-3]
        html_content = html_content.strip()
        
        print("HTML 报告生成成功")
        return html_content
    except Exception as e:
        print(f"HTML 报告生成失败: {e}")
        return None

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
    
    # 生成 HTML 报告
    html = generate_html_report(market_data)
    if not html:
        print("错误: 无法生成 HTML 报告")
        sys.exit(1)
    
    # 保存 HTML 文件
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
