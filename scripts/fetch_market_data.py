#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日股市数据抓取脚本
从多个数据源获取 A 股、港股、美股、大宗商品等数据
兼容 GitHub Actions（美国服务器）环境
"""

import requests
import json
import os
import time
from datetime import datetime

# 数据目录
DATA_DIR = "deploy/data"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def fetch_a_stock_data():
    """获取 A 股数据 - 使用新浪财经 HTTPS API"""
    print("正在获取 A 股数据...")
    a_stock = {}
    
    # 新浪财经 API（HTTPS，从美国可访问）
    codes = {
        "shanghai": "s_sh000001",
        "shenzhen": "s_sz399001",
        "chinext": "s_sz399006",
        "star50": "s_sh000688"
    }
    names = {
        "shanghai": "上证指数",
        "shenzhen": "深证成指",
        "chinext": "创业板指",
        "star50": "科创50"
    }
    
    url = "https://hq.sinajs.cn/list=" + ",".join(codes.values())
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.encoding = "gbk"
        
        for line in response.text.strip().split("\n"):
            line = line.strip()
            if not line or "=" not in line:
                continue
            var_name = line.split("=")[0].split("_")[-1]
            data_str = line.split('"')[1] if '"' in line else ""
            
            for key, code in codes.items():
                if code in var_name:
                    parts = data_str.split(",")
                    if len(parts) >= 4:
                        price = float(parts[1]) if parts[1] else 0
                        prev_close = float(parts[2]) if parts[2] else 0
                        change = price - prev_close
                        change_pct = (change / prev_close * 100) if prev_close else 0
                        
                        a_stock[key] = {
                            "name": names[key],
                            "price": round(price, 2),
                            "change_pct": round(change_pct, 2),
                            "change": round(change, 2)
                        }
        
        if a_stock:
            print(f"✓ A 股数据获取成功: {len(a_stock)} 个指数")
        else:
            print("⚠ A 股数据为空，尝试备用源...")
            a_stock = fetch_a_stock_eastmoney()
            
        return a_stock
        
    except Exception as e:
        print(f"✗ 新浪 A 股数据获取失败: {e}")
        return fetch_a_stock_eastmoney()


def fetch_a_stock_eastmoney():
    """备用：东方财富 HTTPS API"""
    print("尝试东方财富备用源...")
    a_stock = {}
    
    try:
        url = "https://push2.eastmoney.com/api/qt/ulist.np/get"
        params = {
            "fltt": 2,
            "fields": "f2,f3,f4,f12,f14",
            "secids": "1.000001,0.399001,0.399006,1.000688"
        }
        response = requests.get(url, params=params, headers=HEADERS, timeout=15)
        data = response.json()
        
        code_map = {
            "000001": ("shanghai", "上证指数"),
            "399001": ("shenzhen", "深证成指"),
            "399006": ("chinext", "创业板指"),
            "000688": ("star50", "科创50")
        }
        
        for item in data.get("data", {}).get("diff", []):
            code = item.get("f12")
            if code in code_map:
                key, name = code_map[code]
                a_stock[key] = {
                    "name": name,
                    "price": item.get("f2"),
                    "change_pct": item.get("f3"),
                    "change": item.get("f4")
                }
        
        print(f"✓ 东方财富 A 股数据获取成功")
        return a_stock
        
    except Exception as e:
        print(f"✗ 东方财富 A 股数据也失败: {e}")
        return {}


def fetch_hk_stock_data():
    """获取港股数据"""
    print("正在获取港股数据...")
    hk_stock = {}
    
    try:
        url = "https://push2.eastmoney.com/api/qt/ulist.np/get"
        params = {
            "fltt": 2,
            "fields": "f2,f3,f4,f12,f14",
            "secids": "100.HSI,100.HSTECH"
        }
        response = requests.get(url, params=params, headers=HEADERS, timeout=15)
        data = response.json()
        
        code_map = {
            "HSI": ("hsi", "恒生指数"),
            "HSTECH": ("hstech", "恒生科技")
        }
        
        for item in data.get("data", {}).get("diff", []):
            code = item.get("f12")
            if code in code_map:
                key, name = code_map[code]
                hk_stock[key] = {
                    "name": name,
                    "price": item.get("f2"),
                    "change_pct": item.get("f3"),
                    "change": item.get("f4")
                }
        
        print(f"✓ 港股数据获取成功")
        return hk_stock
        
    except Exception as e:
        print(f"✗ 港股数据获取失败: {e}")
        return {}


def fetch_us_stock_data():
    """获取美股数据 - Yahoo Finance"""
    print("正在获取美股数据...")
    us_stock = {}
    
    symbols = {
        "^DJI": ("dowjones", "道琼斯"),
        "^IXIC": ("nasdaq", "纳斯达克"),
        "^GSPC": ("sp500", "标普500")
    }
    
    for symbol, (key, name) in symbols.items():
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
            params = {"interval": "1d", "range": "2d"}
            response = requests.get(url, params=params, headers=HEADERS, timeout=15)
            data = response.json()
            
            result = data["chart"]["result"][0]
            meta = result["meta"]
            
            price = meta.get("regularMarketPrice", 0)
            prev_close = meta.get("chartPreviousClose", meta.get("previousClose", 0))
            
            if prev_close and price:
                change = price - prev_close
                change_pct = (change / prev_close) * 100
            else:
                change = 0
                change_pct = 0
            
            us_stock[key] = {
                "name": name,
                "price": round(price, 2),
                "change_pct": round(change_pct, 2),
                "change": round(change, 2)
            }
            
        except Exception as e:
            print(f"✗ {name}数据获取失败: {e}")
    
    if us_stock:
        print(f"✓ 美股数据获取成功: {len(us_stock)} 个指数")
    return us_stock


def fetch_commodity_data():
    """获取大宗商品数据"""
    print("正在获取大宗商品数据...")
    commodities = {}
    
    symbols = {
        "GC=F": ("gold", "现货黄金"),
        "CL=F": ("oil", "WTI原油"),
        "SI=F": ("silver", "现货白银"),
        "HG=F": ("copper", "COMEX铜")
    }
    
    for symbol, (key, name) in symbols.items():
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
            params = {"interval": "1d", "range": "2d"}
            response = requests.get(url, params=params, headers=HEADERS, timeout=15)
            data = response.json()
            
            result = data["chart"]["result"][0]
            meta = result["meta"]
            
            price = meta.get("regularMarketPrice", 0)
            prev_close = meta.get("chartPreviousClose", meta.get("previousClose", 0))
            
            if prev_close and price:
                change = price - prev_close
                change_pct = (change / prev_close) * 100
            else:
                change = 0
                change_pct = 0
            
            commodities[key] = {
                "name": name,
                "price": round(price, 2),
                "change_pct": round(change_pct, 2),
                "change": round(change, 2)
            }
            
        except Exception as e:
            print(f"✗ {name}数据获取失败: {e}")
    
    if commodities:
        print(f"✓ 大宗商品数据获取成功: {len(commodities)} 个品种")
    return commodities


def fetch_forex_data():
    """获取汇率数据"""
    print("正在获取汇率数据...")
    forex = {}
    
    symbols = {
        "DX-Y.NYB": ("usd_index", "美元指数"),
        "CNY=X": ("usdcnh", "美元/离岸人民币"),
        "JPY=X": ("usdjpy", "美元/日元")
    }
    
    for symbol, (key, name) in symbols.items():
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
            params = {"interval": "1d", "range": "2d"}
            response = requests.get(url, params=params, headers=HEADERS, timeout=15)
            data = response.json()
            
            result = data["chart"]["result"][0]
            meta = result["meta"]
            
            price = meta.get("regularMarketPrice", 0)
            prev_close = meta.get("chartPreviousClose", meta.get("previousClose", 0))
            
            if prev_close and price:
                change = price - prev_close
                change_pct = (change / prev_close) * 100
            else:
                change = 0
                change_pct = 0
            
            forex[key] = {
                "name": name,
                "price": round(price, 4),
                "change_pct": round(change_pct, 2),
                "change": round(change, 4)
            }
            
        except Exception as e:
            print(f"✗ {name}数据获取失败: {e}")
    
    # 美债收益率
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/%5ETNX"
        params = {"interval": "1d", "range": "2d"}
        response = requests.get(url, params=params, headers=HEADERS, timeout=15)
        data = response.json()
        result = data["chart"]["result"][0]
        meta = result["meta"]
        price = meta.get("regularMarketPrice", 0)
        prev_close = meta.get("chartPreviousClose", meta.get("previousClose", 0))
        if prev_close and price:
            change = price - prev_close
            change_pct = (change / prev_close) * 100
        else:
            change = 0
            change_pct = 0
        forex["us10y"] = {
            "name": "10年期美债收益率",
            "price": round(price, 3),
            "change_pct": round(change_pct, 2),
            "change": round(change, 3)
        }
    except Exception as e:
        print(f"✗ 美债收益率获取失败: {e}")
    
    if forex:
        print(f"✓ 汇率数据获取成功: {len(forex)} 个品种")
    return forex


def fetch_news():
    """获取重要财经新闻"""
    print("正在获取财经新闻...")
    news_list = []
    
    # 从新浪财经获取
    try:
        url = "https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2509&k=&num=10&page=1"
        response = requests.get(url, headers=HEADERS, timeout=15)
        data = response.json()
        
        for item in data.get("result", {}).get("data", [])[:5]:
            news_list.append({
                "title": item.get("title", ""),
                "content": item.get("intro", item.get("title", "")),
                "time": item.get("ctime", ""),
                "url": item.get("url", "")
            })
        
        print(f"✓ 新闻获取成功: {len(news_list)} 条")
        
    except Exception as e:
        print(f"✗ 新浪新闻获取失败: {e}")
    
    # 备用：从财联社获取
    if not news_list:
        try:
            url = "https://www.cls.cn/nodeapi/updateTelegraphList"
            params = {"app": "CailianpressWeb", "os": "web", "sv": "8.4.6"}
            response = requests.get(url, params=params, headers=HEADERS, timeout=15)
            data = response.json()
            
            for item in data.get("data", {}).get("roll_data", [])[:5]:
                news_list.append({
                    "title": item.get("title", ""),
                    "content": item.get("content", ""),
                    "time": item.get("ctime", ""),
                    "url": ""
                })
            
            print(f"✓ 财联社新闻获取成功: {len(news_list)} 条")
            
        except Exception as e:
            print(f"✗ 财联社新闻也失败: {e}")
    
    return news_list


def main():
    """主函数"""
    print("=" * 50)
    print(f"开始抓取市场数据 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    
    # 获取各类数据
    data = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "timestamp": datetime.now().isoformat(),
        "a_stock": fetch_a_stock_data(),
        "hk_stock": fetch_hk_stock_data(),
        "us_stock": fetch_us_stock_data(),
        "commodities": fetch_commodity_data(),
        "forex": fetch_forex_data(),
        "news": fetch_news()
    }
    
    # 保存数据
    output_file = os.path.join(DATA_DIR, "market_data.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    # 统计
    total = sum(1 for v in [data["a_stock"], data["hk_stock"], data["us_stock"], 
                            data["commodities"], data["forex"], data["news"]] if v)
    print(f"\n数据获取完成: {total}/6 个数据源成功")
    print(f"✓ 数据已保存到 {output_file}")
    print("=" * 50)


if __name__ == "__main__":
    main()
