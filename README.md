# 🍚 饭记 (FoodLog)

> 日常饮食记录平台 — 截图识别、营养分析、智能推荐

## 功能

- 📸 截图识别：上传外卖截图，AI自动识别食物、热量、价格
- ✏️ 快速修正：AI生成草稿，10秒修正保存
- 📊 每日/每周统计：热量、营养素、支出、标签追踪
- 🎯 智能推荐：根据营养缺口，从你的历史记录中推荐
- 💰 消费追踪：按标签查看咖啡、奶茶、大餐的消费汇总
- 🔍 关键词搜索：快速查找历史记录

## 快速开始

### 安装

```bash
git clone <repo-url>
cd foodlog
pip install -e .
```

### 配置

```bash
cp .env.example .env
# 编辑 .env，填入你的 AI API Key
```

支持的 AI API 提供商：
- OpenAI (GPT-4o)
- Anthropic (Claude)
- 阿里云百炼 (通义千问)
- 任何兼容 OpenAI 接口的服务

### 初始化

```bash
foodlog init    # 初始化数据库 + 示例数据
```

### 使用

```bash
# 命令行
foodlog today           # 查看今日总结
foodlog week            # 查看本周报告
foodlog recommend       # 获取推荐
foodlog add             # 交互式添加记录
foodlog screenshot x.png # 识别截图
foodlog export          # 导出CSV
foodlog serve           # 启动Web服务 → http://localhost:8000
```

## 截图配置示例

### OpenAI
```
AI_API_PROVIDER=openai
AI_API_KEY=sk-xxx
AI_MODEL=gpt-4o
```

### 阿里云百炼
```
AI_API_PROVIDER=aliyun
AI_API_KEY=sk-xxx
AI_MODEL=qwen-vl-max
```

### Anthropic
```
AI_API_PROVIDER=anthropic
AI_API_KEY=sk-ant-xxx
AI_MODEL=claude-sonnet-4-20250514
```

## 技术栈

- Python 3.9+
- FastAPI + Uvicorn (Web后端)
- SQLite (数据存储)
- Typer + Rich (命令行)
- Pillow (图片处理)
- httpx (AI API调用)

## 项目结构

```
foodlog/
├── foodlog/
│   ├── cli.py           # 命令行入口
│   ├── database.py      # 数据存储层
│   ├── ai_recognizer.py # AI截图识别
│   ├── stats.py         # 统计分析
│   ├── recommender.py   # 推荐引擎
│   ├── sample_data.py   # 示例数据
│   └── web/
│       ├── app.py       # FastAPI应用
│       └── templates/
│           └── index.html # Web前端
├── tests/               # 测试
├── data/                # 数据和截图
└── pyproject.toml
```

## 测试

```bash
python -m pytest tests/ -v
```

## License

MIT
