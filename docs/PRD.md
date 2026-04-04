# WHOOP 健康推送系统 — 产品需求文档（PRD）

**版本**：v1.0  
**最后更新**：2026-04-02  
**状态**：已上线，稳定运行

---

## 一、项目背景与目标

### 背景

用户戴 WHOOP 手环收集日常健康数据（睡眠、恢复、运动、HRV 等），但 WHOOP 官方 App 的数据呈现较为原始，缺乏个性化解读和主动推送。用户是跑步爱好者，每周跑 2-3 次，对健康数据是新手，希望通过自然语言的方式了解自己的身体状态。

### 核心目标

1. **每天早上自动收到**一份基于真实 WHOOP 数据的健康晨报，无需手动触发
2. **随时可以提问**，获得结合个人健康数据的 AI 解读
3. **完全自动化**，关掉电脑、出门在外都能正常运转
4. **不依赖 Claude/Anthropic**，不消耗用户的 Claude 额度

---

## 二、核心功能

### 2.1 每日健康晨报

- **触发时间**：北京时间 08:00（含兜底机制，见第四章）
- **推送渠道**：飞书群消息
- **内容结构**：
  - ⚡ 今日一句话（身体状态 + 最该做的一件事）
  - 😴 昨晚睡眠（时长达标 / 深睡REM占比 / 睡眠干扰 / 今晚改善建议）
  - 💚 今天的身体（恢复分 / HRV / 静息心率，均对比7天均值）
  - 🏃 运动建议（结合近期运动记录，给出具体强度和时长）
  - 🧠 精力与压力（工作节奏建议 + 减压行动）
  - 📈 本周趋势（恢复/睡眠/HRV 是在变好还是变差）
- **附带图表**：7天四宫格趋势图（恢复分 / HRV / 睡眠时长 / 压力负荷）
- **数据说明**：WHOOP 恢复分有约1天延迟，报告使用最新已有恢复数据（不强制等待当天数据）

### 2.2 飞书机器人实时问答

- **触发方式**：在飞书群内直接发消息
- **响应延迟**：GitHub Actions 调度间隔（通常 30-60 分钟内响应）
- **上下文**：基于最近 7 天 WHOOP 健康数据
- **典型问题类型**：
  - 运动决策："今天能跑步吗？这周练了多少？"
  - 身体状态："我最近状态怎么样？为什么今天觉得累？"
  - 睡眠诊断："昨晚睡得怎么样？我该几点睡？"
- **过滤规则**：机器人自己发的消息不会触发回复

### 2.3 数据沉淀

- **SQLite 数据库**（`data/whoop_data.db`）：存储每日健康数据 + 运动记录
- **Excel 文件**（`data/whoop_health.xlsx`）：供用户手动查阅的可视化表格
- **自动同步**：每次运行晨报时从 WHOOP API 拉取最新 10 天数据并更新

---

## 三、技术架构

### 3.1 整体架构图

```
WHOOP 手环（采集数据）
    ↓
WHOOP API（数据接口）
    ↓
GitHub Actions（云端调度，无需本地运行）
    ├── 每日晨报 workflow（0 0 * * * UTC）
    │       ↓
    │   MiniMax M2.7 API（AI 生成报告）
    │       ↓
    │   飞书 API（推送消息 + 图表）
    │
    └── Bot Poll workflow（*/1 * * * *，实际约30-60分钟一次）
            ↓
        检查飞书新消息
            ↓（有新消息）
        MiniMax M2.7 API（AI 回复）
            ↓
        飞书 API（发送回复）
```

### 3.2 技术栈

| 组件 | 技术选型 | 说明 |
|------|---------|------|
| 调度平台 | GitHub Actions | 免费，无需服务器，公开仓库无限额 |
| 语言 | Python 3.11 | 主要业务逻辑 |
| AI 模型 | MiniMax M2.7 | 晨报生成 + 实时问答 |
| 数据源 | WHOOP API | 健康数据（恢复、睡眠、运动、HRV） |
| 推送渠道 | 飞书开放平台 | 消息推送 + 机器人问答 |
| 本地存储 | SQLite | 健康数据持久化 |
| 数据备份 | Excel（openpyxl） | 可视化数据表 |
| 图表 | matplotlib + Noto Sans SC | 7天趋势图 |

### 3.3 核心文件结构

```
├── .github/workflows/
│   ├── daily-report.yml     # 每日晨报 workflow
│   └── bot-poll.yml         # 机器人轮询 workflow
├── src/
│   ├── config.py            # 统一配置（环境变量读取）
│   ├── whoop_client.py      # WHOOP API 封装
│   ├── feishu_client.py     # 飞书 API 封装
│   ├── minimax_client.py    # MiniMax API 封装
│   ├── database.py          # SQLite 操作
│   ├── report_daily.py      # 每日晨报逻辑
│   ├── bot_poll.py          # 机器人轮询 + 兜底推送逻辑
│   ├── excel_manager.py     # Excel 生成
│   ├── charts.py            # 趋势图生成
│   └── github_secrets.py    # Token 自动轮换
├── data/
│   ├── whoop_data.db        # SQLite 数据库
│   ├── whoop_health.xlsx    # Excel 数据表
│   ├── bot_state.json       # 机器人状态（含 last_report_date）
│   └── weekly_chart.png     # 最新趋势图
└── scripts/
    └── auth_whoop.py        # 初始 WHOOP OAuth 授权脚本
```

### 3.4 WHOOP Token 自动轮换

WHOOP 的 access token 有效期有限，系统在每次晨报运行时自动检查是否需要刷新，并通过 GitHub API 将新 token 写回 Repository Secrets，无需手动干预。

---

## 四、可靠性设计（关键）

### 4.1 问题根因

GitHub Actions 的 `schedule` cron 触发不保证准时，延迟 2-4 小时是常态，高峰期甚至更长。依赖 cron 单一触发会导致晨报时间不稳定或当天未发。

### 4.2 双保险机制

```
主触发：daily-report.yml cron（0 0 * * * UTC = 北京 08:00）
              ↓ 可能延迟
兜底触发：bot-poll.yml（每分钟运行）
              ├── 读取 bot_state.json 中的 last_report_date
              ├── 若 last_report_date != 今天 且 当前时间 >= 08:00 北京
              └── 立即调用 report_daily.run() 补发
```

- `report_daily.run()` 成功发送后会将 `last_report_date` 写入 `bot_state.json`
- 防止重复发送：当天无论由哪个 workflow 触发，只发一次

### 4.3 数据兜底策略

WHOOP 睡眠数据约有 1 天延迟（当晚数据要次日才完整）。`_find_best_today` 函数的策略：
- 只要有恢复分（recovery_score）即使用该天数据
- 不强制要求睡眠数据同时存在（睡眠字段缺失显示"暂无"）
- 确保报告始终基于最新已处理数据，不回退到前一天

---

## 五、配置要求（迁移时需准备）

### 5.1 必需的环境变量 / GitHub Secrets

| 变量名 | 来源 | 说明 |
|--------|------|------|
| `WHOOP_CLIENT_ID` | WHOOP 开发者平台 | OAuth App 的 Client ID |
| `WHOOP_CLIENT_SECRET` | WHOOP 开发者平台 | OAuth App 的 Client Secret |
| `WHOOP_ACCESS_TOKEN` | 首次授权后获取 | 访问令牌（系统自动轮换） |
| `WHOOP_REFRESH_TOKEN` | 首次授权后获取 | 刷新令牌（系统自动轮换） |
| `WHOOP_TOKEN_SAVED_AT` | 系统自动管理 | Token 保存时间戳 |
| `MINIMAX_API_KEY` | MiniMax 控制台 | AI 接口密钥 |
| `FEISHU_APP_ID` | 飞书开放平台 | 机器人 App ID |
| `FEISHU_APP_SECRET` | 飞书开放平台 | 机器人 App Secret |
| `FEISHU_CHAT_ID` | 飞书群设置 | 目标群的 Chat ID |
| `FEISHU_BOT_OPEN_ID` | 飞书开放平台 | 机器人自身的 Open ID（用于过滤自己的消息） |
| `GH_PAT` | GitHub 个人设置 | Personal Access Token（用于写回 Secrets 做 Token 轮换） |

### 5.2 Python 依赖（requirements.txt）

```
requests
openpyxl
matplotlib
```

### 5.3 GitHub Actions 权限要求

- `contents: write`（用于提交 bot_state.json 和数据文件）
- Repository Secrets 写入权限（通过 GH_PAT）

---

## 六、AI 提示词设计

### 6.1 晨报 System Prompt 核心原则

- 用户画像：跑步爱好者（每周 2-3 次），WHOOP 新手，关注运动/精力/睡眠/压力
- 输出要求：400-600 字，手机一屏半内读完，每个结论必须引用具体数值
- 禁止：编造数据、过度解读正常波动、使用晦涩术语（首次出现需解释）
- 数据预处理：报告前对原始数据做预计算（百分比变化、异常标记、趋势方向），减少 AI 计算负担

### 6.2 机器人问答 System Prompt 核心原则

- 上下文：最近 7 天完整健康数据
- 回复要求：200 字以内，简洁专业
- 必须引用具体数值，给出可执行建议（不说"适当运动"）
- 对无法测量的内容诚实说明（"这个 WHOOP 没法测"）

---

## 七、已知限制与决策记录

| 限制 | 原因 | 处理方式 |
|------|------|---------|
| 晨报数据延迟1天 | WHOOP 恢复分处理需要前一晚睡眠完整数据 | 接受延迟，使用最新已有数据，不回退 |
| 机器人响应最长1小时 | GitHub Actions cron 最小间隔1分钟，实际不保证 | 接受限制，场景为异步健康咨询不需要实时 |
| 仅支持飞书 | 推送渠道设计为单一 | 需迁移时可扩展 feishu_client 为其他渠道 |
| SQLite 无法跨 workflow 共享 | GitHub Actions 每次 checkout 是干净环境 | 数据存入 git 仓库（data/ 目录），每次 commit 同步 |

---

## 八、费用估算

| 服务 | 费用 |
|------|------|
| GitHub Actions | 免费（公开仓库无限额） |
| WHOOP API | 免费（随手环附带） |
| 飞书开放平台 | 免费 |
| MiniMax M2.7 | 按 token 计费（晨报约 4000 tokens/次，问答约 600 tokens/次） |
| Claude / Anthropic | **不使用，零费用** |

---

## 九、迁移指引

如需将本系统迁移到新的 GitHub 仓库或其他平台：

1. Fork 或克隆仓库代码
2. 在新仓库的 Settings → Secrets and variables → Actions 中配置第五章的 11 个变量
3. 确保两个 workflow 文件（`daily-report.yml` 和 `bot-poll.yml`）存在且已启用
4. 飞书机器人需重新配置群权限，将机器人加入目标群
5. 首次运行前通过 `scripts/auth_whoop.py` 重新授权 WHOOP（如 token 已过期）
6. 手动触发一次 `Daily Health Report` 验证端到端流程

---

## 十、版本历史

| 日期 | 变更 |
|------|------|
| 2026-03-28 | 项目初始化，实现基础晨报推送 |
| 2026-03-29 | 加入机器人实时问答 |
| 2026-03-30 | 加入7天趋势图、Excel数据表、WHOOP Token自动轮换 |
| 2026-03-31 | 精简为只保留每日晨报（删除周报/月报） |
| 2026-04-02 | **修复可靠性问题**：bot_poll 兜底推送机制 + 数据日期不回退修复 |
