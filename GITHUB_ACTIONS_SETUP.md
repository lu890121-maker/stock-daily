# GitHub Actions 云端自动报告配置指南

## 概述

本配置使用 Qwen3.7 Plus 大模型在 GitHub Actions 云端自动生成高质量股市分析报告，无需本地电脑运行。

## 配置步骤

### 1. 获取 Qwen API Key

1. 访问阿里云 DashScope 控制台：https://dashscope.console.aliyun.com/
2. 如果没有账号，先注册阿里云账号
3. 开通 DashScope 服务（新用户有免费额度）
4. 在左侧菜单选择 "API-KEY 管理"
5. 点击 "创建新的 API-KEY"
6. 复制生成的 API Key（格式如：sk-xxxxxxxxxxxxxxxx）

### 2. 配置 GitHub Secrets

1. 访问你的 GitHub 仓库：https://github.com/lu890121-maker/stock-daily
2. 点击顶部菜单 "Settings"（设置）
3. 在左侧菜单找到 "Secrets and variables" → "Actions"
4. 点击 "New repository secret"
5. 填写：
   - Name: `QWEN_API_KEY`
   - Secret: 粘贴你的 Qwen API Key
6. 点击 "Add secret"

### 3. 测试配置

配置完成后，可以手动触发测试：

1. 访问：https://github.com/lu890121-maker/stock-daily/actions
2. 点击左侧 "Daily Stock Report"
3. 点击右侧 "Run workflow" 按钮
4. 选择分支（main），点击 "Run workflow"
5. 等待 2-3 分钟，查看运行结果

### 4. 查看报告

报告生成后会自动发布到：
- 最新报告：https://lu890121-maker.github.io/stock-daily/latest.html
- 归档报告：https://lu890121-maker.github.io/stock-daily/archive/YYYY-MM-DD.html

## 自动化时间

- 每个交易日（周一至周五）北京时间 16:30 自动运行
- 数据抓取：从东方财富、新浪财经等获取实时数据
- AI 分析：Qwen3.7 Plus 生成五维度深度分析
- 自动发布：推送到 GitHub Pages

## 费用说明

- GitHub Actions：免费额度每月 2000 分钟（公开仓库）
- Qwen API：新用户有免费额度，之后按调用量计费
  - qwen-plus 模型：约 0.008元/千 tokens
  - 每次报告约 4000 tokens，成本约 0.03 元
  - 每月 22 个交易日，总成本约 0.66 元

## 故障排查

### 问题：API Key 无效
- 检查是否正确配置到 GitHub Secrets
- 确认 API Key 格式正确（sk- 开头）
- 在 DashScope 控制台检查 Key 状态

### 问题：报告生成失败
- 查看 GitHub Actions 运行日志
- 检查数据抓取是否成功（data/market_data.json）
- 确认 Qwen API 额度是否充足

### 问题：报告未发布
- 检查 GitHub Pages 是否启用
- 确认 deploy 目录文件是否提交
- 查看 Actions 日志中的 git push 步骤

## 手动触发

如需手动生成报告（如节假日调休）：

```bash
# 本地测试
export QWEN_API_KEY="你的API Key"
python scripts/fetch_market_data.py
python scripts/generate_ai_report.py

# 提交并推送
git add .
git commit -m "Manual report generation"
git push
```

## 技术架构

```
GitHub Actions (云端)
  ↓
fetch_market_data.py (数据抓取)
  ↓
market_data.json (原始数据)
  ↓
generate_ai_report.py (AI 分析)
  ↓
Qwen3.7 Plus API (大模型)
  ↓
latest.html + archive/YYYY-MM-DD.html
  ↓
GitHub Pages (自动发布)
```

## 优化建议

1. **监控成本**：定期检查 DashScope 控制台的使用量
2. **备份数据**：data 目录会自动提交到仓库
3. **自定义提示词**：可修改 generate_ai_report.py 中的 prompt 优化报告质量
4. **添加通知**：可配置邮件/微信通知报告生成结果
