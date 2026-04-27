# AI 商业资讯 Telegram 简报

这是一个可运行的代码版 MVP：每天从白名单信源抓取 AI 相关新闻，优先筛出应用、产品化、商业化相关内容，再生成一份带来源的 Telegram 简报。

它默认兼容官方 OpenAI，也兼容大多数 OpenAI-compatible 第三方网关，例如 `modelgate` 这类统一转发层。

## 设计目标

- 不靠模型“凭空找新闻”，只对白名单信源做处理
- 每条内容都保留来源、链接、发布时间
- 摘要只允许基于抓到的原始材料生成
- 默认偏应用、商业化、企业落地，不偏深技术
- 兼容第三方 OpenAI-like 模型网关

## 当前流程

1. 读取 `config/sources.json`
2. 拉取 RSS / Atom feed
3. 按关键词和规则给文章打分
4. 对候选文章抓取页面补充摘要证据
5. 去重
6. 调用兼容 OpenAI 协议的 LLM API 生成结构化简报
7. 发到 Telegram
8. 将结果和原始候选项落盘到 `output/`

## 目录结构

```text
config/
  sources.json
src/ai_briefing/
  config.py
  feed_fetcher.py
  filtering.py
  models.py
  openai_client.py
  pipeline.py
  telegram.py
run_daily_briefing.py
```

## 本地运行

1. 准备 Python 3.11+
2. 复制环境变量模板
3. 填入 LLM 和 Telegram 配置
4. 运行主脚本

```powershell
Copy-Item .env.example .env
python run_daily_briefing.py
```

如果你当前没有本地 Python，也可以使用 Codex 桌面环境自带的运行时：

```powershell
C:\Users\pc\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe run_daily_briefing.py
```

## Telegram 配置

1. 在 Telegram 里找到 `@BotFather`
2. 创建机器人，拿到 `TELEGRAM_BOT_TOKEN`
3. 先主动给机器人发一条消息
4. 在浏览器打开：

```text
https://api.telegram.org/bot<你的bot_token>/getUpdates
```

5. 从返回 JSON 里找到你的 `chat.id`
6. 把这个值填入 `TELEGRAM_CHAT_ID`

## 第三方模型网关配置

如果你不是直接调用官方 OpenAI，而是通过 `modelgate` 之类的第三方网关，通常只需要改这些环境变量：

```env
OPENAI_API_KEY=你的网关key
OPENAI_MODEL=你在网关里可用的模型名
LLM_BASE_URL=https://你的网关域名/v1
LLM_API_STYLE=chat_completions
LLM_USE_JSON_SCHEMA=true
```

说明：

- `LLM_BASE_URL` 是网关根路径，代码会自动拼接成 `/chat/completions`
- `LLM_API_STYLE` 默认用 `chat_completions`，兼容性比官方 `responses` 更好
- `LLM_USE_JSON_SCHEMA=true` 时会优先使用结构化输出
- 如果你的网关不支持 `json_schema`，可以设为 `false`，代码会退回到“纯 JSON 文本输出 + 本地解析”
- 如果你的网关要求额外请求头，可以在 `LLM_EXTRA_HEADERS_JSON` 里填 JSON，例如 `{"HTTP-Referer":"https://example.com","X-Title":"AI Briefing"}`

一个示例：

```env
OPENAI_API_KEY=mg_xxx
OPENAI_MODEL=gpt-5.4
LLM_BASE_URL=https://api.modelgate.example/v1
LLM_API_STYLE=chat_completions
LLM_USE_JSON_SCHEMA=false
LLM_EXTRA_HEADERS_JSON={"X-Provider":"modelgate"}
```

## GitHub Actions 定时运行

仓库已附带 [`.github/workflows/daily-briefing.yml`](./.github/workflows/daily-briefing.yml)。

你需要在 GitHub 仓库里设置这些 Secrets：

- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `LLM_BASE_URL`
- `LLM_API_STYLE`
- `LLM_USE_JSON_SCHEMA`
- `LLM_EXTRA_HEADERS_JSON`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Actions 默认每天北京时间 `08:30` 运行一次。你可以自行改 cron。

## 如何调优信源

初版 `config/sources.json` 里混合了：

- 官方动态：OpenAI
- 行业媒体：TechCrunch AI、VentureBeat AI
- Google News 行业查询流：企业应用、融资、agent、copilot

建议你先跑 3 到 5 天，再根据结果做这些动作：

- 删除噪音过高的来源
- 提高高价值来源的 `priority`
- 增加你关心行业的查询流，例如医疗、教育、客服、销售
- 调整 `include_keywords` 和 `exclude_keywords`

## 输出格式

Telegram 简报默认长这样：

```text
AI 商业简报 | 2026-04-24

今日总览：
一句话概括今天的商业化动向

1. 标题
摘要：发生了什么
商业意义：这件事说明什么方向
来源：媒体名 | 时间
原文链接

今日信号：
- 趋势 1
- 趋势 2
- 趋势 3
```

## 真实性约束

代码里做了几层约束：

- 只处理白名单 feed
- 给候选新闻保留原始证据文本
- Prompt 明确要求不得补充输入中不存在的事实
- 支持结构化输出和纯 JSON 双模式，避免被单一供应商特性卡住
- 页面内容太少、证据不足的条目会被丢弃
- 最终每条都强制带 `source_name` 和 `source_url`

## 下一步建议

如果你准备长期用，建议后续迭代这几项：

- 加来源可信度分层
- 加更强的重复事件聚合
- 增加周报 / 月报模式
- 给新闻打“商业价值分”
- 增加行业标签，例如 `sales`、`healthcare`、`finance`
