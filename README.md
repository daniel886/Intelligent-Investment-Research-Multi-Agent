# 📊 Intelligent-Investment-Research-Multi-Agent

> **基于 LangGraph 的多智能体投资研究系统**：自动协调「基本面」「技术面」「风险评估」三大专业 Agent，
> 跨市场（A股 / 港股 / 美股 / 加密货币）抓取实时数据 → 协作完成研究 → 生成专业中文（可双语）报告，
> 支持 Web 面板、定时日报推送（Telegram / Email）、向量记忆与历史回溯。

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2%2B-green.svg)](https://github.com/langchain-ai/langgraph)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-teal.svg)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-ready-blue.svg)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](#)

---

## ✨ 核心亮点

- **三大专业智能体并行协作**：`FundamentalAgent` / `TechnicalAgent` / `RiskAgent` 由 LangGraph 调度并行执行，最后由首席投资官 (CIO) 节点综合输出。
- **多市场数据接入**：Polygon API + yfinance + Alpha Vantage + Playwright（雪球/东方财富）+ CoinGecko，覆盖 A股 / 港股 / 美股 / 加密货币。
- **自然语言驱动**：用户输入「分析腾讯控股」「生成今日投资日报」即可自动完成研究。
- **生产级工程质量**：完整类型提示 (Pydantic v2) · 异步实现 · API 限流 · 异常恢复 · Loguru 日志 · 健康检查。
- **持久化与记忆**：SQLite 存储历史报告 + Chroma 向量数据库支持语义检索过往研究。
- **定时推送**：APScheduler + Telegram / SMTP 邮件，每日自动生成投资日报。
- **Web 面板**：内嵌深色主题 Web UI，支持新建研究、历史浏览、语义搜索、股票池管理。
- **中英双语报告**：language=`en-US` 时自动输出英文翻译版。
- **一键部署**：Dockerfile + docker-compose + GitHub Actions CI/CD 完整配套。

---

## 🧠 系统架构

```
┌──────────────────────────────────────────────────────────────────┐
│                  自然语言指令 (Web / API / CLI)                   │
└─────────────────────────────┬────────────────────────────────────┘
                              ▼
                   workflows.symbol_resolver  (中→ticker)
                              ▼
                ┌────────────LangGraph────────────┐
                │              start              │
                │     ┌──────────┼──────────┐      │
                │     ▼          ▼          ▼      │
                │ Fundamental Technical    Risk    │
                │     Agent     Agent     Agent    │
                │     └──────────┼──────────┘      │
                │           synthesize (CIO)       │
                └─────────────────┬────────────────┘
                                  ▼
              ┌──────────┴───────────┐
              ▼                      ▼
       SQLite + Chroma          Telegram / Email
       (历史 + 语义检索)           (推送通知)
```

---

## 🗂 项目结构

```text
Intelligent-Investment-Research-Multi-Agent/
├── main.py                    # 启动入口 / CLI
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── .gitignore
├── init_github.sh             # 自动 git init + GitHub 仓库创建 + push
├── README.md
├── .github/workflows/ci-cd.yml
├── agents/                    # 3 个专业智能体
│   ├── base.py
│   ├── fundamental_agent.py
│   ├── technical_agent.py
│   └── risk_agent.py
├── tools/                     # 数据源封装
│   ├── polygon_tool.py
│   ├── yfinance_tool.py
│   ├── alpha_vantage_tool.py
│   ├── playwright_scraper.py  # 雪球 / 东方财富
│   ├── onchain_tool.py        # CoinGecko 链上数据
│   ├── news_tool.py
│   ├── indicators.py          # 技术 + 风险指标
│   └── rate_limiter.py
├── workflows/
│   ├── research_workflow.py   # LangGraph 编排
│   └── symbol_resolver.py
├── api/
│   ├── app.py                 # FastAPI 应用
│   └── routes.py              # REST 路由
├── models/
│   ├── schemas.py             # Pydantic v2 模型
│   └── database.py            # SQLAlchemy ORM
├── services/
│   ├── notifier.py            # Telegram + SMTP
│   ├── scheduler.py           # APScheduler 日报
│   ├── repository.py          # 报告存储
│   └── vectorstore.py         # Chroma 向量库
├── config/
│   ├── settings.py
│   └── logging.py
├── static/index.html          # Web 面板（单文件）
└── tests/                     # pytest 测试
```

---

## ⚙️ 安装步骤

### 1. 克隆并安装依赖

```bash
git clone https://github.com/<your-handle>/Intelligent-Investment-Research-Multi-Agent.git
cd Intelligent-Investment-Research-Multi-Agent

python -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 首次启用雪球/东财抓取功能时安装 Playwright Chromium
playwright install chromium
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入：
#   OPENAI_API_KEY、POLYGON_API_KEY、ALPHA_VANTAGE_KEY、TELEGRAM_TOKEN 等
```

最少必填：
- `OPENAI_API_KEY`（或同协议的 LLM）
- `POLYGON_API_KEY` / `ALPHA_VANTAGE_KEY`（任一）

### 3. 启动服务

#### 本地运行（开发模式）

```bash
# 启动 FastAPI + 后台调度器
python main.py

# 访问 Web 面板
open http://localhost:8000

# 直接 CLI 调用一次研究
python main.py research "分析苹果、腾讯控股、比特币"

# 立即触发一次「每日日报」并推送
python main.py daily
```

#### Docker 运行（推荐生产部署）

```bash
docker compose up -d --build

# 查看日志
docker compose logs -f research-agent

# 停止
docker compose down
```

---

## 🚀 使用示例

### Web 面板

打开 `http://localhost:8000`，在左侧文本框输入任意中文指令：

```
分析腾讯控股、英伟达和比特币的基本面和风险点，并给出投资建议
```

系统会：
1. 自动识别 `0700.HK` / `NVDA` / `BTC-USD`；
2. 并行调度三个 Agent；
3. 综合后输出执行摘要、评级、目标价、置信度；
4. 持久化存储 + 向量索引，可随时检索。

### REST API

```bash
# 1) 触发研究
curl -X POST http://localhost:8000/api/v1/research \
  -H 'Content-Type: application/json' \
  -d '{"query":"分析腾讯控股", "language":"zh-CN"}'

# 2) 查询历史报告
curl http://localhost:8000/api/v1/reports?limit=10

# 3) 添加股票池
curl -X POST http://localhost:8000/api/v1/watchlist \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"0700.HK","name":"腾讯控股","market":"港股"}'

# 4) 立即跑一次每日日报
curl -X POST http://localhost:8000/api/v1/scheduler/run-now

# 5) 语义搜索过往报告
curl 'http://localhost:8000/api/v1/reports/search/semantic?q=AI+芯片+护城河&n=5'
```

### Python SDK 调用

```python
import asyncio
from models.schemas import ResearchRequest
from workflows.research_workflow import get_workflow

async def main():
    wf = get_workflow()
    reports = await wf.run(ResearchRequest(query="分析特斯拉的财务健康度", language="zh-CN"))
    for r in reports:
        print(r.title, r.recommendation, r.target_price)

asyncio.run(main())
```

---

## 🔬 真实股票分析案例演示（3 只标的）

> 以下为系统输出格式范例（实际数值随当时行情动态生成）。

### 📌 案例 1 ─ AAPL（美股 · 苹果）

```
📄  AAPL 投资研究报告
评级：增持 | 目标价：232.5 | 置信度：0.78

【基本面】公司服务业务收入占比突破 25%，毛利率 46% 维持高位；
TTM PE ≈ 32 略高于 5 年中位数，但 ROE ≈ 160% 体现极强资本效率。

【技术面】价格站上 50/200 日均线，RSI=58 健康偏强，
MACD 金叉延续 3 周。关键支撑 215，压力 240。

【风险】年化波动率约 22%，最大回撤 -12%，整体风险等级 中等；
主要风险：iPhone 出货量增速放缓 + 反垄断诉讼。
```

### 📌 案例 2 ─ 0700.HK（港股 · 腾讯控股）

```
📄  0700.HK 投资研究报告
评级：买入 | 目标价：HK$ 480 | 置信度：0.82

【基本面】游戏业务收入恢复双位数增长，海外游戏占比提升至 ~30%；
微信视频号广告增速强劲，金融科技毛利率改善。
PE ≈ 17 接近近 5 年低位，估值具吸引力。

【技术面】月线级别突破下降趋势线，周线 MACD 多头排列。
建议在 380-400 区间分批建仓，止损 360。

【风险】主要风险来自宏观监管不确定性；波动率 28%，最大回撤 -22%。
```

### 📌 案例 3 ─ BTC-USD（加密 · 比特币）

```
📄  BTC-USD 投资研究报告
评级：持有 | 目标价：- | 置信度：0.55

【基本面】机构 ETF 持续净流入，链上活跃地址 90 日均值上升；
然而矿工抛压和宏观利率仍构成压制。

【技术面】价格反复测试 60K 关键位，
RSI 已脱离超买区间至 52，等待方向性突破。

【风险】波动率 ≈ 60%，单日 95% VaR 约 -5%，风险等级 高，
建议总仓位不超过组合 5%。
```

---

## 📅 每日自动报告使用指南

### 1. 配置股票池

```bash
# 直接通过 .env 设定（最简单）
WATCHLIST=AAPL,0700.HK,NVDA,600519.SS,BTC-USD

# 或动态调用 API
curl -X POST http://localhost:8000/api/v1/watchlist \
  -d '{"symbol":"AAPL","name":"Apple","market":"美股"}' \
  -H 'Content-Type: application/json'
```

### 2. 配置定时表达式（cron）

```bash
# 每个工作日 09:00 (UTC) 推送
DAILY_REPORT_CRON=0 9 * * 1-5

# 每天 21:00 推送
DAILY_REPORT_CRON=0 21 * * *
```

### 3. 配置推送通道

```bash
# Telegram
TELEGRAM_TOKEN=12345:abcdef...
TELEGRAM_CHAT_ID=123456789

# Email (Gmail 应用密码示例)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=you@gmail.com
SMTP_PASSWORD=app-password
EMAIL_FROM=you@gmail.com
EMAIL_TO=team@example.com
```

### 4. 验证 / 立即触发

```bash
python main.py daily                      # 本地立即跑一次
curl -X POST localhost:8000/api/v1/scheduler/run-now   # 通过 API 触发
```

> 触发后会先发送一份「日报摘要」到 Telegram + Email，再逐个标的推送详细报告。

---

## 🧪 测试

```bash
pytest -q
pytest --cov=. --cov-report=term-missing   # 覆盖率
```

CI/CD 已在 `.github/workflows/ci-cd.yml` 配置：每次 push / PR 会自动跑测试 + 构建 Docker 镜像。

---

## 🚢 部署说明

### Docker Compose (推荐)

```bash
docker compose up -d --build
docker compose logs -f
```

### 一键推送到 GitHub

```bash
export GITHUB_USER=<your-handle>
export GITHUB_TOKEN=<personal-access-token>     # 仅在没有 gh CLI 时需要
./init_github.sh
```

脚本会：
1. `git init` 并提交首份 commit；
2. 通过 `gh` CLI 或 REST API 在 GitHub 创建仓库（默认 public）；
3. 添加 origin 并 `push` 到 main 分支。

### 反向代理（Nginx 示例）

```nginx
server {
    listen 80;
    server_name research.example.com;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

---

## 🛡 生产级特性 Checklist

- ✅ 完整 Pydantic v2 类型校验
- ✅ 全异步 IO（httpx + aiosqlite + langgraph.ainvoke）
- ✅ Tenacity 指数退避重试
- ✅ 自研 sliding-window async rate-limiter
- ✅ Loguru 结构化日志 + 按天滚动
- ✅ FastAPI Lifespan 钩子 + Healthcheck
- ✅ Docker 多阶段构建 + Healthcheck
- ✅ Chroma 向量记忆 + SQLite 持久化
- ✅ 中英双语报告
- ✅ 网络抓取容错（Playwright 不可用时自动跳过）

---

## 🔭 下一步路线图

- [ ] 引入 LangGraph 检查点 (Postgres backed) 实现长期会话
- [ ] 增加做空 / 期权策略 Agent
- [ ] 引入实时 WebSocket 推送
- [ ] 多用户 + JWT 鉴权
- [ ] 接入 OpenBB / Tushare Pro / 万得 数据源
- [ ] 训练专属本地小模型作为基本面摘要器

---

## 📝 License

MIT — 详见 LICENSE。

> **免责声明**：本系统输出仅供研究学习，不构成投资建议。投资有风险，决策需谨慎。
