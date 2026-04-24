# GitHub Actions 上线步骤

当前项目已经包含可直接使用的工作流文件：

- [`.github/workflows/daily-briefing.yml`](./.github/workflows/daily-briefing.yml)

要让它每天自动给你发 Telegram，只需要把当前项目上传到 GitHub，并配置仓库 Secrets。

## 1. 创建 GitHub 仓库

在 GitHub 上新建一个仓库，例如：

- `ai-telegram-briefing`

创建时不要勾选自动生成 README，避免和本地文件冲突。

## 2. 把当前项目推上去

如果你的电脑里已经安装 Git，可以在项目目录运行：

```powershell
git init
git branch -M main
git add .
git commit -m "Initial commit"
git remote add origin <你的仓库地址>
git push -u origin main
```

如果这台机器还没装 Git，你可以：

- 先安装 Git 再执行上面的命令
- 或者直接把当前目录压缩后上传到 GitHub 仓库

## 3. 在 GitHub 仓库设置 Secrets

进入：

- `Settings`
- `Secrets and variables`
- `Actions`

新增这些仓库 Secrets：

- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `LLM_BASE_URL`
- `LLM_API_STYLE`
- `LLM_USE_JSON_SCHEMA`
- `LLM_EXTRA_HEADERS_JSON`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

建议填写示例：

```text
OPENAI_API_KEY=你的modelgate_key
OPENAI_MODEL=gpt-5-mini
LLM_BASE_URL=https://mg.aid.pub/v1
LLM_API_STYLE=chat_completions
LLM_USE_JSON_SCHEMA=true
LLM_EXTRA_HEADERS_JSON=
TELEGRAM_BOT_TOKEN=你的telegram_bot_token
TELEGRAM_CHAT_ID=你的telegram_chat_id
```

## 4. 启用 GitHub Actions

推送完成后，进入仓库的 `Actions` 页面：

- 找到 `Daily AI Briefing`
- 先手动点一次 `Run workflow`

这样可以确认：

- Secrets 是否填对
- modelgate 是否可用
- Telegram 是否正常发送

## 5. 定时发送时间

当前工作流里的 cron 是：

```yaml
30 0 * * *
```

这表示每天 `00:30 UTC` 运行，也就是北京时间 `08:30`。

如果你想改成别的时间，可以编辑：

- [`.github/workflows/daily-briefing.yml`](./.github/workflows/daily-briefing.yml)

## 6. 建议的首次检查

首次上线后，建议连续观察 2 到 3 天：

- Telegram 是否每天按时收到
- 简报内容是否仍有噪音
- 某些来源是否太强或太弱

然后再继续微调：

- `config/sources.json`
- `src/ai_briefing/filtering.py`

## 当前已完成的部分

你现在不需要再开发工作流逻辑，项目里这些都已经就位：

- 每日抓取
- 白名单信源
- 企业应用/商业化筛选
- 第三方模型网关调用
- Telegram 发送
- GitHub Actions 工作流

缺的只是：

- 把仓库上传到 GitHub
- 把 Secrets 配进去
