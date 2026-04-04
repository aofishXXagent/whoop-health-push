# WHOOP 健康推送系统

基于 WHOOP 手环数据的全自动健康分析与推送系统。通过 GitHub Actions 云端运行，**无需本地电脑在线**，每天自动获取健康数据，调用 AI 生成深度分析报告，推送至飞书群。

```
WHOOP 手环 → WHOOP API → GitHub Actions → MiniMax AI → 飞书推送
                              ↓
                     SQLite + Excel 数据沉淀
```

---

## 功能

### 每日健康晨报（北京时间 08:00）
- ⚡ 今日一句话：身体状态 + 最该做的一件事
- 😴 睡眠分析：时长 / 深睡REM占比 / 干扰次数 / 今晚改善建议
- 💚 身体状态：恢复分 / HRV / 静息心率（均与7天均值对比）
- 🏃 运动建议：结合近期训练记录，给出具体强度和时长
- 🧠 精力与压力：工作节奏建议 + 减压行动
- 📈 本周趋势：恢复/睡眠/HRV 是在变好还是变差
- 7 天趋势图表（恢复分 / HRV / 睡眠时长 / 压力负荷）

### 飞书机器人实时问答
- 在飞书群内直接提问，基于最近 7 天真实数据回答
- 支持："今天能跑步吗？"、"昨晚睡得怎么样？"、"我这周状态如何？"

### 可靠性保障
- **双保险机制**：daily-report cron 为主触发，bot-poll 每次运行时兜底检查今日晨报是否已发，超过 08:00 未发则自动补发
- **Token 自动轮换**：WHOOP access token 到期时自动刷新并写回 GitHub Secrets，无需人工干预

---

## 技术架构

| 组件 | 技术 |
|------|------|
| 调度平台 | GitHub Actions（免费，无需服务器） |
| AI 模型 | MiniMax M2.7 |
| 数据源 | WHOOP API（OAuth2） |
| 推送渠道 | 飞书开放平台 |
| 数据存储 | SQLite + Excel |
| 图表 | matplotlib |

### 文件结构

```
├── .github/workflows/
│   ├── daily-report.yml     # 每日晨报 workflow
│   └── bot-poll.yml         # 机器人轮询 + 兜底推送
├── src/
│   ├── config.py            # 统一配置（环境变量）
│   ├── whoop_client.py      # WHOOP API 封装
│   ├── feishu_client.py     # 飞书 API 封装
│   ├── minimax_client.py    # MiniMax API 封装
│   ├── database.py          # SQLite 操作
│   ├── report_daily.py      # 晨报逻辑 + 预计算引擎
│   ├── bot_poll.py          # 机器人问答 + 兜底推送逻辑
│   ├── excel_manager.py     # Excel 生成
│   ├── charts.py            # 趋势图生成
│   └── github_secrets.py    # Token 自动轮换
├── scripts/
│   └── auth_whoop.py        # 首次 WHOOP OAuth 授权
├── data/                    # 运行时数据（DB / Excel / 图表 / 机器人状态）
└── docs/
    └── PRD.md               # 产品需求文档（完整方案说明）
```

---

## 部署

### 前置条件

需要准备以下 4 个平台的凭证：

| 平台 | 需要的凭证 |
|------|-----------|
| WHOOP 开发者平台 | Client ID、Client Secret、Access Token、Refresh Token |
| 飞书开放平台 | App ID、App Secret、Chat ID、Bot Open ID |
| MiniMax | API Key |
| GitHub | Personal Access Token（用于 Token 自动轮换） |

### 步骤

1. **Fork 本仓库**

2. **首次 WHOOP 授权**（本地运行一次）
   ```bash
   pip install requests
   python scripts/auth_whoop.py
   ```
   按提示完成 OAuth 授权，记录输出的三个 token 值。

3. **配置 GitHub Secrets**
   进入仓库 Settings → Secrets and variables → Actions，添加以下 11 个 Secret：

   | 名称 | 说明 |
   |------|------|
   | `WHOOP_CLIENT_ID` | WHOOP 开发者后台 |
   | `WHOOP_CLIENT_SECRET` | WHOOP 开发者后台 |
   | `WHOOP_ACCESS_TOKEN` | 授权脚本输出 |
   | `WHOOP_REFRESH_TOKEN` | 授权脚本输出 |
   | `WHOOP_TOKEN_SAVED_AT` | 授权脚本输出 |
   | `MINIMAX_API_KEY` | MiniMax 控制台 |
   | `FEISHU_APP_ID` | 飞书应用凭证页 |
   | `FEISHU_APP_SECRET` | 飞书应用凭证页 |
   | `FEISHU_CHAT_ID` | 飞书目标群 ID |
   | `FEISHU_BOT_OPEN_ID` | 飞书机器人 Open ID |
   | `GH_PAT` | GitHub Personal Access Token |

4. **启用 Actions**
   进入仓库 Actions 页面，点击启用 workflows。

5. **验证**
   手动触发一次 Daily Health Report，确认飞书群收到推送。

### 排查常见问题

| 现象 | 原因 |
|------|------|
| Actions 报 `EnvironmentError` | Secret 名称拼写错误或漏填 |
| 飞书未收到消息 | 机器人未加入群，或 `FEISHU_CHAT_ID` 不对 |
| WHOOP 数据为空 | 手环未同步到手机 App |
| AI 报告未生成 | `MINIMAX_API_KEY` 有误或余额不足 |

---

## 自定义

| 想改什么 | 改哪里 |
|---------|--------|
| 晨报触发时间 | `daily-report.yml` 的 cron 表达式 |
| 报告风格和字数 | `src/report_daily.py` 的 `DAILY_SYSTEM_PROMPT` |
| 机器人回复风格 | `src/bot_poll.py` 的 `BOT_SYSTEM_PROMPT` |
| 兜底推送时间（默认08:00） | `src/bot_poll.py` 的 `REPORT_HOUR_BEIJING` |
| 换其他 AI 模型 | `src/minimax_client.py`（接口兼容 OpenAI 格式） |
| 换其他推送渠道 | `src/feishu_client.py` |

---

## 安全

- 所有密钥存储在 GitHub Secrets，代码中零硬编码
- WHOOP Token 全自动轮换，无需人工维护
- `.gitignore` 排除所有本地敏感文件

---

## License

MIT
