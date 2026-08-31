#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
使用 Qwen3.7 Plus 生成高质量股市分析报告
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


def call_qwen_api(prompt, api_key):
    """调用 Qwen3.7 Plus API"""
    url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "qwen-plus",
        "input": {
            "messages": [
                {
                    "role": "system",
                    "content": "你是一位专业的金融分析师，擅长撰写深度股市分析报告。请用通俗易懂的语言，结合数据进行分析。"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        },
        "parameters": {
            "temperature": 0.7,
            "max_tokens": 4000
        }
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=120)
        response.raise_for_status()
        result = response.json()
        
        if "output" in result and "text" in result["output"]:
            return result["output"]["text"]
        else:
            print(f"API 返回格式异常: {result}")
            return None
            
    except Exception as e:
        print(f"调用 Qwen API 失败: {e}")
        return None


def generate_ai_analysis(data, api_key):
    """使用 AI 生成完整分析报告"""
    print("正在调用 Qwen3.7 Plus 生成深度分析...")
    
    # 构建提示词
    date_str = data["date"]
    a_stock = data.get("a_stock", {})
    hk_stock = data.get("hk_stock", {})
    us_stock = data.get("us_stock", {})
    commodities = data.get("commodities", {})
    forex = data.get("forex", {})
    news_list = data.get("news", [])
    
    prompt = f"""请基于以下 {date_str} 的市场数据，生成一份完整的每日股市分析报告。

## 市场数据

### A 股
- 上证指数: {a_stock.get('shanghai', {}).get('price', 'N/A')} ({a_stock.get('shanghai', {}).get('change_pct', 0):+.2f}%)
- 深证成指: {a_stock.get('shenzhen', {}).get('price', 'N/A')} ({a_stock.get('shenzhen', {}).get('change_pct', 0):+.2f}%)
- 创业板指: {a_stock.get('chinext', {}).get('price', 'N/A')} ({a_stock.get('chinext', {}).get('change_pct', 0):+.2f}%)
- 科创50: {a_stock.get('star50', {}).get('price', 'N/A')} ({a_stock.get('star50', {}).get('change_pct', 0):+.2f}%)

### 港股
- 恒生指数: {hk_stock.get('hsi', {}).get('price', 'N/A')} ({hk_stock.get('hsi', {}).get('change_pct', 0):+.2f}%)
- 恒生科技: {hk_stock.get('hstech', {}).get('price', 'N/A')} ({hk_stock.get('hstech', {}).get('change_pct', 0):+.2f}%)

### 美股（上一交易日）
- 道琼斯: {us_stock.get('dowjones', {}).get('price', 'N/A')} ({us_stock.get('dowjones', {}).get('change_pct', 0):+.2f}%)
- 纳斯达克: {us_stock.get('nasdaq', {}).get('price', 'N/A')} ({us_stock.get('nasdaq', {}).get('change_pct', 0):+.2f}%)
- 标普500: {us_stock.get('sp500', {}).get('price', 'N/A')} ({us_stock.get('sp500', {}).get('change_pct', 0):+.2f}%)

### 大宗商品
- 现货黄金: {commodities.get('gold', {}).get('price', 'N/A')} ({commodities.get('gold', {}).get('change_pct', 0):+.2f}%)
- WTI原油: {commodities.get('oil', {}).get('price', 'N/A')} ({commodities.get('oil', {}).get('change_pct', 0):+.2f}%)

### 汇率
- 美元指数: {forex.get('usd_index', {}).get('price', 'N/A')} ({forex.get('usd_index', {}).get('change_pct', 0):+.2f}%)

### 重要新闻
{chr(10).join([f"- {n.get('title', '')}" for n in news_list[:5]])}

## 报告要求

请生成包含以下内容的完整 HTML 报告（严格参照 2026-08-25.html 的模板结构）：

1. **HERO 区域**：一句话总结今日行情（如"沃什鹰啸全球承压 · A股低开高走独立行情"）

2. **A 股速览**：
   - 四大指数点位与涨跌幅
   - 两市成交额、涨停/跌停家数
   - 今日定性总结（2-3句话）

3. **全球市场全景**：
   - 亚太、美股、欧股、期货数据表格
   - 全球图景总结

4. **环球要闻（8-10条）**：
   - 按极重要/重要/关注三级分类
   - 每条包含：标题、大白话解读、对你有啥影响
   - 覆盖国内外重要事件

5. **五维度深度分析**：
   - 消息面（利好/利空）
   - 情绪面（涨停/跌停、成交量）
   - 技术面（关键支撑/压力位）
   - 政策面（最新政策）
   - 资金面（主力资金流向）

6. **板块热力图**：领涨/领跌板块

7. **焦点个股**：涨停股、资金流入/流出个股

8. **大宗商品与汇率**：详细数据表格

9. **产业高频数据**：2-3个重点产业链追踪

10. **后市展望与操作策略**：
    - 短期/中期/长期判断
    - 关注方向与风险点

请输出完整的 HTML 代码（包含所有 CSS 样式），确保可以直接保存为 .html 文件。使用红涨绿跌配色，max-width 680px，UTF-8 编码。
"""
    
    # 调用 API
    ai_content = call_qwen_api(prompt, api_key)
    
    if ai_content:
        print("✓ AI 分析生成成功")
        return ai_content
    else:
        print("✗ AI 分析生成失败")
        return None


def save_report(html_content, date_str):
    """保存报告"""
    # 保存为 latest.html
    latest_file = os.path.join(DEPLOY_DIR, "latest.html")
    with open(latest_file, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"✓ 报告已保存到 {latest_file}")
    
    # 归档
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
    
    # 检查 API Key
    api_key = os.environ.get("QWEN_API_KEY")
    if not api_key:
        print("✗ 错误: 未设置 QWEN_API_KEY 环境变量")
        print("请在 GitHub Secrets 中配置 QWEN_API_KEY")
        return False
    
    # 加载数据
    data = load_market_data()
    date_str = data["date"]
    print(f"✓ 数据加载成功: {date_str}")
    
    # 生成 AI 分析
    html_content = generate_ai_analysis(data, api_key)
    
    if not html_content:
        print("✗ AI 分析生成失败")
        return False
    
    # 保存报告
    save_report(html_content, date_str)
    
    print("=" * 50)
    print("✓ AI 分析报告生成完成")
    print("=" * 50)
    return True


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
