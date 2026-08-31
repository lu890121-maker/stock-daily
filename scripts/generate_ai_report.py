#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
使用 OpenAI API 生成高质量股市分析报告
"""

import json
import os
import requests
from datetime import datetime

# 数据目录
DATA_DIR = "deploy/data"
DEPLOY_DIR = "deploy"

def load_market_data():
    """加载市场数据"""
    data_file = os.path.join(DATA_DIR, "market_data.json")
    with open(data_file, "r", encoding="utf-8") as f:
        return json.load(f)


def call_openai_api(prompt, api_key):
    """调用 Qwen3.7 Plus API (DashScope 国际站)"""
    url = "https://coding-intl.dashscope.aliyuncs.com/v1/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "qwen3.7-plus",
        "messages": [
            {
                "role": "system",
                "content": "你是一位专业的金融分析师，擅长撰写深度股市分析报告。请用通俗易懂的语言，结合数据进行分析。报告需要包含五维度分析（消息面/情绪面/技术面/政策面/资金面）、环球要闻、板块热力图、焦点个股、大宗商品、产业高频数据和后市展望。"
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.7,
        "max_tokens": 4000
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=180)
        response.raise_for_status()
        result = response.json()
        
        if "choices" in result and len(result["choices"]) > 0:
            return result["choices"][0]["message"]["content"]
        else:
            print(f"API 返回格式异常: {result}")
            return None
            
    except Exception as e:
        print(f"调用 OpenAI API 失败: {e}")
        return None


def generate_ai_analysis(data, api_key):
    """使用 AI 生成完整分析报告"""
    print("正在调用 OpenAI API 生成深度分析...")
    
    # 构建提示词
    date_str = data["date"]
    a_stock = data.get("a_stock") or {}
    hk_stock = data.get("hk_stock") or {}
    us_stock = data.get("us_stock") or {}
    commodities = data.get("commodities") or {}
    forex = data.get("forex") or {}
    news_list = data.get("news") or []
    
    # 格式化数据
    def fmt(d):
        if not d:
            return "数据暂缺"
        price = d.get("price", "N/A")
        pct = d.get("change_pct", 0)
        if pct is None:
            pct = 0
        return f"{price} ({pct:+.2f}%)"
    
    news_text = "\n".join([f"- {n.get('title', n.get('content', '')[:50])}" for n in news_list[:8]]) if news_list else "暂无新闻数据"
    
    prompt = f"""请基于以下 {date_str} 的市场数据，生成一份完整的每日股市分析报告。

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

### 重要新闻
{news_text}

## 报告要求

请生成包含以下内容的完整 HTML 报告：

1. **HERO 区域**：一句话总结今日行情
2. **A 股速览**：四大指数、成交额、涨停/跌停、今日定性
3. **全球市场全景**：亚太/美股/欧股/期货数据表格 + 全球图景总结
4. **环球要闻（8-10条）**：按极重要/重要/关注三级分类，每条含标题+大白话解读+影响分析
5. **五维度深度分析**：消息面/情绪面/技术面/政策面/资金面
6. **板块热力图**：领涨/领跌板块
7. **焦点个股**：涨停股、资金流入/流出个股
8. **大宗商品与汇率**：详细数据表格
9. **产业高频数据**：2-3个重点产业链追踪
10. **后市展望与操作策略**：短/中/长期判断 + 关注方向 + 风险点

## HTML 格式要求

- 严格使用以下 CSS 样式（红涨绿跌，max-width 680px）
- 输出完整的 HTML 代码（从 <!DOCTYPE html> 到 </html>）
- 使用 UTF-8 编码
- 导航栏 sticky
- 包含 HERO / A股速览 / 全球市场 / 环球要闻 / 五维度 / 板块热力图 / 焦点个股 / 大宗商品 / 产业高频 / 策略研判 / 页脚

请直接输出完整的 HTML 代码，不要加任何解释文字。
"""
    
    # 调用 API
    ai_content = call_openai_api(prompt, api_key)
    
    if ai_content:
        print("✓ AI 分析生成成功")
        return ai_content
    else:
        print("✗ AI 分析生成失败")
        return None


def save_report(html_content, date_str):
    """保存报告"""
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
    """主函数"""
    print("=" * 50)
    print(f"开始生成 AI 分析报告 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    
    api_key = os.environ.get("QWEN_API_KEY")
    if not api_key:
        print("✗ 错误: 未设置 QWEN_API_KEY 环境变量")
        print("请在 GitHub Secrets 中配置 QWEN_API_KEY")
        return False
    
    data = load_market_data()
    date_str = data["date"]
    print(f"✓ 数据加载成功: {date_str}")
    
    html_content = generate_ai_analysis(data, api_key)
    
    if not html_content:
        print("✗ AI 分析生成失败")
        return False
    
    save_report(html_content, date_str)
    
    print("=" * 50)
    print("✓ AI 分析报告生成完成")
    print("=" * 50)
    return True


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
