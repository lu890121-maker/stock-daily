#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日股市报告生成脚本
基于抓取的数据生成 HTML 报告
"""

import json
import os
import shutil
from datetime import datetime

# 数据目录
DATA_DIR = "data"
DEPLOY_DIR = "deploy"

def load_market_data():
    """加载市场数据"""
    data_file = os.path.join(DATA_DIR, "market_data.json")
    with open(data_file, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_html_report(data):
    """生成 HTML 报告"""
    date_str = data["date"]
    
    # A 股数据
    a_stock = data.get("a_stock", {})
    shanghai = a_stock.get("shanghai", {})
    shenzhen = a_stock.get("shenzhen", {})
    chinext = a_stock.get("chinext", {})
    star50 = a_stock.get("star50", {})
    
    # 港股数据
    hk_stock = data.get("hk_stock", {})
    hsi = hk_stock.get("hsi", {})
    hstech = hk_stock.get("hstech", {})
    
    # 美股数据
    us_stock = data.get("us_stock", {})
    dowjones = us_stock.get("dowjones", {})
    nasdaq = us_stock.get("nasdaq", {})
    sp500 = us_stock.get("sp500", {})
    
    # 大宗商品
    commodities = data.get("commodities") or {}
    gold = commodities.get("gold", {}) or {}
    oil = commodities.get("oil", {}) or {}
    
    # 汇率
    forex = data.get("forex") or {}
    usd_index = forex.get("usd_index", {}) or {}
    
    # 新闻
    news_list = data.get("news", [])
    
    # 生成涨跌颜色类
    def get_color_class(change_pct):
        if change_pct > 0:
            return "up"
        elif change_pct < 0:
            return "down"
        return ""
    
    # 生成新闻 HTML
    news_html = ""
    for i, news in enumerate(news_list[:3], 1):
        news_html += f"""
        <div class="news-item">
            <h3>{news['title']}</h3>
            <p>{news['content']}</p>
            <span class="news-time">{news['time']}</span>
        </div>
        """
    
    # HTML 模板
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>每日股市观察 - {date_str}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background: #f5f5f5;
        }}
        .container {{
            max-width: 800px;
            margin: 0 auto;
            background: white;
        }}
        .hero {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px 20px;
            text-align: center;
        }}
        .hero h1 {{
            font-size: 28px;
            margin-bottom: 10px;
        }}
        .hero .subtitle {{
            font-size: 14px;
            opacity: 0.9;
        }}
        .section {{
            padding: 30px 20px;
            border-bottom: 1px solid #eee;
        }}
        .section-title {{
            font-size: 20px;
            font-weight: bold;
            margin-bottom: 20px;
            color: #333;
        }}
        .market-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 15px;
            margin-bottom: 20px;
        }}
        .market-card {{
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            text-align: center;
        }}
        .market-card .name {{
            font-size: 12px;
            color: #666;
            margin-bottom: 8px;
        }}
        .market-card .price {{
            font-size: 20px;
            font-weight: bold;
            margin-bottom: 5px;
        }}
        .market-card .change {{
            font-size: 14px;
            font-weight: 500;
        }}
        .up {{ color: #e74c3c; }}
        .down {{ color: #27ae60; }}
        .news-item {{
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 15px;
        }}
        .news-item h3 {{
            font-size: 16px;
            margin-bottom: 10px;
            color: #333;
        }}
        .news-item p {{
            font-size: 14px;
            color: #666;
            margin-bottom: 8px;
        }}
        .news-time {{
            font-size: 12px;
            color: #999;
        }}
        .footer {{
            background: #2c3e50;
            color: white;
            padding: 20px;
            text-align: center;
            font-size: 12px;
        }}
        @media (max-width: 600px) {{
            .market-grid {{
                grid-template-columns: repeat(2, 1fr);
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="hero">
            <h1>每日股市观察</h1>
            <div class="subtitle">{date_str} · 全球市场速览</div>
        </div>
        
        <div class="section">
            <div class="section-title">A 股市场</div>
            <div class="market-grid">
                <div class="market-card">
                    <div class="name">上证指数</div>
                    <div class="price {get_color_class(shanghai.get('change_pct', 0))}">{shanghai.get('price', '--')}</div>
                    <div class="change {get_color_class(shanghai.get('change_pct', 0))}">{shanghai.get('change_pct', 0):+.2f}%</div>
                </div>
                <div class="market-card">
                    <div class="name">深证成指</div>
                    <div class="price {get_color_class(shenzhen.get('change_pct', 0))}">{shenzhen.get('price', '--')}</div>
                    <div class="change {get_color_class(shenzhen.get('change_pct', 0))}">{shenzhen.get('change_pct', 0):+.2f}%</div>
                </div>
                <div class="market-card">
                    <div class="name">创业板指</div>
                    <div class="price {get_color_class(chinext.get('change_pct', 0))}">{chinext.get('price', '--')}</div>
                    <div class="change {get_color_class(chinext.get('change_pct', 0))}">{chinext.get('change_pct', 0):+.2f}%</div>
                </div>
                <div class="market-card">
                    <div class="name">科创50</div>
                    <div class="price {get_color_class(star50.get('change_pct', 0))}">{star50.get('price', '--')}</div>
                    <div class="change {get_color_class(star50.get('change_pct', 0))}">{star50.get('change_pct', 0):+.2f}%</div>
                </div>
            </div>
        </div>
        
        <div class="section">
            <div class="section-title">港股市场</div>
            <div class="market-grid">
                <div class="market-card">
                    <div class="name">恒生指数</div>
                    <div class="price {get_color_class(hsi.get('change_pct', 0))}">{hsi.get('price', '--')}</div>
                    <div class="change {get_color_class(hsi.get('change_pct', 0))}">{hsi.get('change_pct', 0):+.2f}%</div>
                </div>
                <div class="market-card">
                    <div class="name">恒生科技</div>
                    <div class="price {get_color_class(hstech.get('change_pct', 0))}">{hstech.get('price', '--')}</div>
                    <div class="change {get_color_class(hstech.get('change_pct', 0))}">{hstech.get('change_pct', 0):+.2f}%</div>
                </div>
            </div>
        </div>
        
        <div class="section">
            <div class="section-title">美股市场（上一交易日）</div>
            <div class="market-grid">
                <div class="market-card">
                    <div class="name">道琼斯</div>
                    <div class="price {get_color_class(dowjones.get('change_pct', 0))}">{dowjones.get('price', '--')}</div>
                    <div class="change {get_color_class(dowjones.get('change_pct', 0))}">{dowjones.get('change_pct', 0):+.2f}%</div>
                </div>
                <div class="market-card">
                    <div class="name">纳斯达克</div>
                    <div class="price {get_color_class(nasdaq.get('change_pct', 0))}">{nasdaq.get('price', '--')}</div>
                    <div class="change {get_color_class(nasdaq.get('change_pct', 0))}">{nasdaq.get('change_pct', 0):+.2f}%</div>
                </div>
                <div class="market-card">
                    <div class="name">标普500</div>
                    <div class="price {get_color_class(sp500.get('change_pct', 0))}">{sp500.get('price', '--')}</div>
                    <div class="change {get_color_class(sp500.get('change_pct', 0))}">{sp500.get('change_pct', 0):+.2f}%</div>
                </div>
            </div>
        </div>
        
        <div class="section">
            <div class="section-title">大宗商品与汇率</div>
            <div class="market-grid">
                <div class="market-card">
                    <div class="name">现货黄金</div>
                    <div class="price {get_color_class(gold.get('change_pct', 0))}">{gold.get('price', '--')}</div>
                    <div class="change {get_color_class(gold.get('change_pct', 0))}">{gold.get('change_pct', 0):+.2f}%</div>
                </div>
                <div class="market-card">
                    <div class="name">WTI原油</div>
                    <div class="price {get_color_class(oil.get('change_pct', 0))}">{oil.get('price', '--')}</div>
                    <div class="change {get_color_class(oil.get('change_pct', 0))}">{oil.get('change_pct', 0):+.2f}%</div>
                </div>
                <div class="market-card">
                    <div class="name">美元指数</div>
                    <div class="price {get_color_class(usd_index.get('change_pct', 0))}">{usd_index.get('price', '--')}</div>
                    <div class="change {get_color_class(usd_index.get('change_pct', 0))}">{usd_index.get('change_pct', 0):+.2f}%</div>
                </div>
            </div>
        </div>
        
        <div class="section">
            <div class="section-title">重要新闻</div>
            {news_html}
        </div>
        
        <div class="footer">
            <p>数据来源：东方财富、Yahoo Finance</p>
            <p>生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p>本报告由 GitHub Actions 自动生成，仅供参考，不构成投资建议</p>
        </div>
    </div>
</body>
</html>"""
    
    return html


def update_index(date_str):
    """更新 index.html"""
    index_file = os.path.join(DEPLOY_DIR, "index.html")
    
    # 读取现有 index.html
    with open(index_file, "r", encoding="utf-8") as f:
        content = f.read()
    
    # 更新最新报告链接
    # 这里需要根据实际的 index.html 结构来更新
    # 暂时简单处理：替换日期
    content = content.replace("2026-08-31", date_str)
    
    with open(index_file, "w", encoding="utf-8") as f:
        f.write(content)


def archive_report(date_str):
    """归档报告"""
    latest_file = os.path.join(DEPLOY_DIR, "latest.html")
    archive_file = os.path.join(DEPLOY_DIR, "archive", f"{date_str}.html")
    
    # 确保 archive 目录存在
    archive_dir = os.path.join(DEPLOY_DIR, "archive")
    if not os.path.exists(archive_dir):
        os.makedirs(archive_dir)
    
    # 复制最新报告到归档
    shutil.copy(latest_file, archive_file)


def main():
    """主函数"""
    print("=" * 50)
    print(f"开始生成报告 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    
    # 加载数据
    data = load_market_data()
    date_str = data["date"]
    
    print(f"✓ 数据加载成功: {date_str}")
    
    # 生成 HTML 报告
    html = generate_html_report(data)
    
    # 保存为 latest.html
    latest_file = os.path.join(DEPLOY_DIR, "latest.html")
    with open(latest_file, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✓ 报告已保存到 {latest_file}")
    
    # 归档报告
    archive_report(date_str)
    print(f"✓ 报告已归档")
    
    # 更新 index.html
    update_index(date_str)
    print(f"✓ index.html 已更新")
    
    print("=" * 50)
    print("✓ 报告生成完成")
    print("=" * 50)


if __name__ == "__main__":
    main()
