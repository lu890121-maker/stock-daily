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
    
    prompt = f"""你是"每日全球股市观察"的AI金融分析师。请基于以下 {date_str} 的市场数据，生成一份**完整、深度、专业**的每日股市分析报告。

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

## 报告结构要求（必须包含以下全部10个板块）

### 1. HERO 区域（顶部横幅）
- 标题格式："XXX鹰啸全球承压 · A股低开高走独立行情"（对仗句式，用em和i标签分别标红/绿关键词）
- 副标题：一行概括核心数据（沪指涨跌幅、成交额、涨停数、关键事件）
- 日期栏：日期+星期+收盘全维度分析

### 2. A股收盘速览
- 四大指数卡片网格（上证指数/深证成指/创业板指/科创50），每个显示点位+涨跌幅
- 统计栏：两市成交额、较昨日增减、涨停家数、跌停家数
- 定性总结段落（callout样式）：3-5句话概括今日行情特征，用粗体标注关键数据和结论

### 3. 全球市场全景
- 市场状态图例（收盘/盘中/昨夜）
- 完整数据表格：亚太（日经225、KOSPI、恒指、恒生科技）、美股（道指、纳指、标普500、费半）、欧股（STOXX50、DAX、富时100、CAC40）、美股期货
- 全球图景总结段落（callout blue样式）：3-5句话概括全球市场联动关系

### 4. 环球要闻（8-10条）
- 三级重要性标注：🔴极重要（红色背景）、🟠重要（橙色背景）、🔵关注（蓝色背景）
- 每条新闻结构：信源标签 + 标题 + 大白话解读段落（2-3句）+ "对你有啥影响"段落
- 必须覆盖：美联储/央行动态、地缘政治、国内政策、产业重大事件、海外市场
- 信源标注：Reuters/Bloomberg/CNBC/WSJ/FT（国际）+ 央行/住建部/统计局（国内）

### 5. 五维度深度分析
- 消息面（d1红色）：利好/利空分类，每条带粗体关键词
- 情绪面（d2橙色）：涨停/跌停对比、成交量变化、板块轮动特征
- 技术面（d3蓝色）：四大指数关键支撑/压力位、月线/周线形态
- 政策面（d4紫色）：最新政策梳理、政策力度评估
- 资金面（d5绿色）：主力资金流向TOP、板块资金净流入/流出、港股通数据
- 每个维度末尾附"结论"句

### 6. 板块热力图
- 领涨板块（红色进度条）+ 领跌板块（绿色进度条），各5个
- 每个板块标注代表个股或涨跌幅
- 底部callout总结板块轮动特征

### 7. 焦点个股与资金流
- 16个焦点个股卡片（2列网格）：涨停股、资金流入/流出个股、海外重点个股
- 每张卡片：股票名 + 标签（涨停/跌停/板块概念）+ 关键数据
- 底部callout blue：一组对比分析（如"AI应用落地 vs 光伏业绩暴雷"）

### 8. 大宗商品与汇率
- 完整数据表格：黄金/白银/原油/铜 + 美元指数/人民币/日元/美债收益率 + 比特币
- 底部callout：4个关键信号分析（黄金、油价、美元、美债）

### 9. 产业高频数据（6个产业链卡片）
- 2列网格布局，每个卡片包含：图标+名称+状态标签 + 5条要点 + 信源
- 必须覆盖：AI应用/短剧、液冷/算力、房地产、贵金属、半导体/科技、地缘/能源
- 每条要点用粗体标注关键数据，涨跌幅用up/dn类名标色

### 10. 后市展望与操作策略
- 深色背景strat卡片：短/中/长期判断（各1-2句）+ 风险点列举
- 关注方向标签（dir红色=看多，dir cool蓝色=观望/回避）
- 风险清单（risk红色卡片）：6条风险按紧迫度排序，每条带粗体关键词

### 11. 页脚
- 数据来源列表
- 报告时间
- 免责声明

## HTML/CSS 技术要求

- 红涨绿跌配色：涨用 #e84855（红色），跌用 #12a05c（绿色）
- max-width: 680px，居中显示
- UTF-8 编码
- 导航栏 sticky（sec-nav类），支持平滑滚动跳转
- 所有section用sec类包裹，sec-head包含图标+标题+备注
- 使用以下CSS类名：idx-grid/idx(up/down)、statbar/stat、callout/callout blue、news(a/b/c)、dim(d1-d5)、heat/heat-row/heat-fill(up/down)、chips/chip、tbl/tbl tr.grp/hot、gf-grid/gf-card(hot/warm/cool/neut)、strat/strat-in、dirs/dir(cool)、risk
- 输出完整的HTML代码（从<!DOCTYPE html>到</html>），包含所有CSS样式在<style>标签内
- 不要输出任何解释文字，只输出HTML代码

请直接输出完整的HTML代码。
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
