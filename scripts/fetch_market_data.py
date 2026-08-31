#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日股市数据抓取脚本
从多个数据源获取 A 股、港股、美股、大宗商品等数据
"""

import requests
import json
import os
from datetime import datetime
from bs4 import BeautifulSoup

# 创建数据目录
DATA_DIR = "data"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

def fetch_a_stock_data():
    """获取 A 股数据"""
    print("正在获取 A 股数据...")
    
    # 使用东方财富 API
    url = "http://push2.eastmoney.com/api/qt/ulist.np/get"
    params = {
        "fltt": 2,
        "fields": "f2,f3,f4,f12,f14",
        "secids": "1.000001,0.399001,0.399006,1.000688"  # 上证、深证、创业板、科创50
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        a_stock = {}
        for item in data.get("data", {}).get("diff", []):
            code = item.get("f12")
            name = item.get("f14")
            price = item.get("f2")
            change_pct = item.get("f3")
            change = item.get("f4")
            
            if code == "000001":
                a_stock["shanghai"] = {
                    "name": "上证指数",
                    "price": price,
                    "change_pct": change_pct,
                    "change": change
                }
            elif code == "399001":
                a_stock["shenzhen"] = {
                    "name": "深证成指",
                    "price": price,
                    "change_pct": change_pct,
                    "change": change
                }
            elif code == "399006":
                a_stock["chinext"] = {
                    "name": "创业板指",
                    "price": price,
                    "change_pct": change_pct,
                    "change": change
                }
            elif code == "000688":
                a_stock["star50"] = {
                    "name": "科创50",
                    "price": price,
                    "change_pct": change_pct,
                    "change": change
                }
        
        print(f"✓ A 股数据获取成功")
        return a_stock
        
    except Exception as e:
        print(f"✗ A 股数据获取失败: {e}")
        return None


def fetch_hk_stock_data():
    """获取港股数据"""
    print("正在获取港股数据...")
    
    url = "http://push2.eastmoney.com/api/qt/ulist.np/get"
    params = {
        "fltt": 2,
        "fields": "f2,f3,f4,f12,f14",
        "secids": "100.HSI,100.HSTECH"  # 恒生指数、恒生科技
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        hk_stock = {}
        for item in data.get("data", {}).get("diff", []):
            code = item.get("f12")
            name = item.get("f14")
            price = item.get("f2")
            change_pct = item.get("f3")
            change = item.get("f4")
            
            if code == "HSI":
                hk_stock["hsi"] = {
                    "name": "恒生指数",
                    "price": price,
                    "change_pct": change_pct,
                    "change": change
                }
            elif code == "HSTECH":
                hk_stock["hstech"] = {
                    "name": "恒生科技",
                    "price": price,
                    "change_pct": change_pct,
                    "change": change
                }
        
        print(f"✓ 港股数据获取成功")
        return hk_stock
        
    except Exception as e:
        print(f"✗ 港股数据获取失败: {e}")
        return None


def fetch_us_stock_data():
    """获取美股数据"""
    print("正在获取美股数据...")
    
    # 使用 Yahoo Finance API
    symbols = ["^DJI", "^IXIC", "^GSPC"]  # 道琼斯、纳斯达克、标普500
    names = ["道琼斯", "纳斯达克", "标普500"]
    keys = ["dowjones", "nasdaq", "sp500"]
    
    us_stock = {}
    
    for symbol, name, key in zip(symbols, names, keys):
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
            params = {"interval": "1d", "range": "1d"}
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            result = data["chart"]["result"][0]
            meta = result["meta"]
            
            price = meta["regularMarketPrice"]
            prev_close = meta["chartPreviousClose"]
            change = price - prev_close
            change_pct = (change / prev_close) * 100
            
            us_stock[key] = {
                "name": name,
                "price": round(price, 2),
                "change_pct": round(change_pct, 2),
                "change": round(change, 2)
            }
            
        except Exception as e:
            print(f"✗ {name}数据获取失败: {e}")
    
    if us_stock:
        print(f"✓ 美股数据获取成功")
    return us_stock


def fetch_commodity_data():
    """获取大宗商品数据"""
    print("正在获取大宗商品数据...")
    
    # 黄金、原油
    symbols = ["GC=F", "CL=F"]  # 黄金期货、原油期货
    names = ["现货黄金", "WTI原油"]
    keys = ["gold", "oil"]
    
    commodities = {}
    
    for symbol, name, key in zip(symbols, names, keys):
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
            params = {"interval": "1d", "range": "1d"}
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            result = data["chart"]["result"][0]
            meta = result["meta"]
            
            price = meta["regularMarketPrice"]
            prev_close = meta["chartPreviousClose"]
            change = price - prev_close
            change_pct = (change / prev_close) * 100
            
            commodities[key] = {
                "name": name,
                "price": round(price, 2),
                "change_pct": round(change_pct, 2),
                "change": round(change, 2)
            }
            
        except Exception as e:
            print(f"✗ {name}数据获取失败: {e}")
    
    if commodities:
        print(f"✓ 大宗商品数据获取成功")
    return commodities


def fetch_forex_data():
    """获取汇率数据"""
    print("正在获取汇率数据...")
    
    # 美元指数
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB"
        params = {"interval": "1d", "range": "1d"}
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        result = data["chart"]["result"][0]
        meta = result["meta"]
        
        price = meta["regularMarketPrice"]
        prev_close = meta["chartPreviousClose"]
        change = price - prev_close
        change_pct = (change / prev_close) * 100
        
        forex = {
            "usd_index": {
                "name": "美元指数",
                "price": round(price, 2),
                "change_pct": round(change_pct, 2),
                "change": round(change, 2)
            }
        }
        
        print(f"✓ 汇率数据获取成功")
        return forex
        
    except Exception as e:
        print(f"✗ 汇率数据获取失败: {e}")
        return None


def fetch_news():
    """获取重要财经新闻"""
    print("正在获取财经新闻...")
    
    news_list = []
    
    # 从东方财富获取新闻
    try:
        url = "http://newsapi.eastmoney.com/kuaixun/v1/getlist_102_ajaxResult_50_1_.html"
        response = requests.get(url, timeout=10)
        text = response.text
        
        # 解析 JSONP
        json_str = text[text.find("(") + 1:text.rfind(")")]
        data = json.loads(json_str)
        
        for item in data.get("LivesList", [])[:5]:
            news_list.append({
                "title": item.get("Title", ""),
                "content": item.get("Digest", ""),
                "time": item.get("ShowTime", "")
            })
        
        print(f"✓ 新闻获取成功")
        
    except Exception as e:
        print(f"✗ 新闻获取失败: {e}")
    
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
    
    print("=" * 50)
    print(f"✓ 数据已保存到 {output_file}")
    print("=" * 50)


if __name__ == "__main__":
    main()
