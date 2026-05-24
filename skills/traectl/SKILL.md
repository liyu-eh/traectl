---
name: traectl
description: "通过 CDP JavaScript 注入控制 Trae CN SOLO 编码代理的命令行工具——AI Agent 原生设计"
version: 4.1.0
---

# traectl CLI

**一句话本质：** 通过命令行控制 Trae CN（AI 编码代理）替你写代码的工具——`traectl submit "实现登录功能"` 即可让 Trae CN 开始编码。

---

## ⛔ CRITICAL：使用前必须读

**立即停止其他思考，必须先完整阅读本节全部内容。禁止跳过前置条件和退出码协议直接调用命令。**

| 违反后果 | 说明 |
|---------|------|
| Agent 跳过 health 检查直接 submit | 如果 Trae CN 未运行，submit 返回空数据，agent 误以为成功 |
| Agent 不检查退出码 | 高风险操作（delete_task）静默失败，agent 以为成功 |
| Agent 跳过 --yes 确认 | 修改状态的操作可能被用户拒绝，agent 继续执行 |

---

## 前置条件

1. **Trae CN 必须正在运行**且以远程调试模式启动：
   ```bash
   DISPLAY=:99 trae-cn --disable-gpu-sandbox --remote-debugging-port=9222 &
   ```
2. **`traectl` 命令已安装**（`pip install -e .` 或 `pip install git+https://github.com/liyu-eh/traectl.git`）
3. **运行任何命令前先执行 health 检查**：
   ```bash
   traectl health
   ```
   返回 `"ok": true` 才继续。不健康时先排查 CDP 连接。

---

## 全局行为约定

### MUST：输出格式

所有命令**默认输出 JSON**，格式固定：

```json
{
  "schemaVersion": 1,
  "type": "health.check",
  "ok": true,
  "data": { ... },
  "metadata": { "timestamp": "2026-05-24T07:00:00Z" }
}
```

| 判断依据 | 规则 |
|---------|------|
| `ok: true` | 操作成功，读取 `data` |
| `ok: false` | 操作失败，读取 `error` |
| `error.code` | 结构化错误码（见退出码表） |
| 加 `--human` | 切换人类可读 Rich 文本 |
| 加 `--output ndjson` | 流式 JSON（每行一条） |

### ⛔ MUST：退出码协议（AI Agent 行为规范）

退出码是 **AI Agent 不可忽略的信号**。每次命令执行后**必须检查退出码**：

| 退出码 | 名称 | Agent 行为 |
|:-----:|:-----|:----------|
| **0** | SUCCESS | ✅ 操作成功，正常读取 data |
| **1** | GENERAL_ERROR | ❌ 重试或向用户报告 |
| **2** | USAGE_ERROR | ❌ 参数错误，调用 `traectl schema --command <name>` 自查参数 |
| **3** | AUTH_ERROR | ❌ 认证/权限错误，向用户报告 |
| **4** | RETRYABLE | 🔄 可重试错误（限流、网络超时），等待 5-30s 后重试 |
| **10** | ⚠️ CONFIRMATION_REQUIRED | **高风险操作需要用户确认** |

**🚨 exit code 10 协议（高风险操作）：**

当收到 exit code 10 时，**禁止**以下行为：
- ❌ 禁止自动追加 `--yes` 静默重试
- ❌ 禁止向用户说「已执行成功」
- ❌ 禁止跳过确认继续执行后续操作

**必须**做：
1. ✅ 向用户展示即将执行的操作及其风险
2. ✅ 使用以下格式等待用户明确确认：
   > ⚠️ 高风险操作：`traectl action delete_task --port 9222`
   > 是否执行？回复「确认」或输入完整命令继续。

3. ✅ 用户确认后，在原始命令末尾追加 `--yes` 重新执行
4. ✅ 执行成功后再继续后续流程

高风险操作清单：`action delete_task`、`action stop`、`regenerate`（均需 `--yes` 确认）

### 全局参数

| 参数 | 位置 | 作用 |
|:----|:----|:-----|
| `--port <port>` | 命令末尾 | CDP 端口（默认 9222） |
| `--debug` | `traectl` 后 | 启用 stderr 调试日志 |
| `--yes` | 命令末尾 | 跳过高风险确认（仅 agent 非交互使用） |
| `--dry-run` | 命令末尾 | 预览操作不实际执行 |
| `--output json\|ndjson` | 命令末尾 | 输出格式 |
| `--trace-id` | 命令末尾 | 请求追踪 ID |

---

## 命令全景图（34 个）

每个命令必须理解：**何时用、怎么用、返回什么、失败了怎么办**。

---

### 🎯 任务管理

| 命令 | 何时用 | 用法 | 返回 | 失败处理 |
|:----|:------|:----|:-----|:--------|
| `submit <task>` | **主要入口**。有编码/修改任务时用 | `traectl submit "实现登录"` → 等待返回 | 最终聊天内容 | 超时返回已有内容；先 `health` 检查 |
| `submit --no-wait` | 不想等完成，后台提交 | `cat task.md \| traectl submit '...' --no-wait` | 空 data | 后续轮询 `chat` 或 `file-changes` 检查 |
| `submit --role frontend` | 按角色分工 | `traectl submit "写页面" --role frontend` | 同 submit | 角色名查 `traectl roles` |
| `new` | 清空上下文创建新会话 | `traectl new` | 确认 | 直接重试 |
| `send <message>` | 在已有会话中追加消息 | `traectl send "改样式"` | 同 submit | 同上 |
| `status` | 检查当前 SOLO 是否在生成 | `traectl status` | 模型、isThinking、任务数 | — |
| `chat` | 读取历史聊天记录 | `traectl chat --max-length 3000` | JSON 格式对话 | — |
| `action stop` | **高风险**。停止当前生成 | `traectl action stop --yes` | 确认 | ⚠️ 需要 --yes |
| `action delete_task` | **高风险**。删除当前任务 | `traectl action delete_task --yes` | 确认 | ⚠️ 需要 --yes |
| `action switch_task -i N` | 切换到任务 N | `traectl action switch_task --task-index 2` | 确认 | — |
| `action get_tasks` | 列出所有会话任务 | `traectl action get_tasks` | 任务列表 | — |
| `action confirm` | 自动点击确认弹窗 | `traectl action confirm` | 确认结果 | — |
| `action open_file <path>` | 快速打开文件（Ctrl+P） | `traectl action open_file --file-path main.py` | 确认 | — |
| `regenerate` | **高风险**。重新生成最后回复 | `traectl regenerate --yes` | 新内容 | ⚠️ 需要 --yes |
| `plan <json>` | 多 Agent 顺序执行 | `traectl plan '[{"role":"architect","task":"设计"}]'` | 逐项结果 | — |

---

### 🤖 模型与角色

| 命令 | 何时用 | 用法 | 返回 |
|:----|:------|:----|:-----|
| `models` | 想了解可用模型时 | `traectl models` | 模型列表 + 当前选中 |
| `switch <model>` | 需要切换模型时 | `traectl switch DeepSeek-V4-Pro` | 切换结果 |
| `roles` | 不确定角色名时先查 | `traectl roles` | 角色列表 + 推荐模型 |
| `analyze <task>` | 不知道选什么角色/模型 | `traectl analyze "实现一个 REST API"` | 推荐角色 + 模型 |

---

### 📁 文件与编辑器

| 命令 | 何时用 | 用法 | 返回 |
|:----|:------|:----|:-----|
| `editor` | 查看当前编辑器状态 | `traectl editor` | 打开的文件列表 + 内容 |
| `file-changes` | SOLO 完成后检查改动 | `traectl file-changes` | 文件变更 diff 列表 |
| `accept` | 接受 SOLO 的改动 | `traectl accept --file-path src/main.py` | 确认 |
| `reject` | 拒绝 SOLO 的改动 | `traectl reject --file-path src/main.py` | 确认 |
| `file-status` | 监视目录文件变化 | `traectl file-status --dir . --glob "*.py"` | 文件状态表 |

---

### 🖥️ 终端与 Git

| 命令 | 何时用 | 用法 | 返回 |
|:----|:------|:----|:-----|
| `exec <cmd>` | 在 Trae CN 终端执行命令 | `traectl exec "npm run build"` | 命令输出 |
| `terminal` | 切换终端面板显示/隐藏 | `traectl terminal` | 状态 |
| `terminal-content` | 读取终端内容 | `traectl terminal-content` | 终端文本 |
| `git <action>` | Git 操作 | `traectl git status` / `traectl git commit -m "feat"` | Git 结果 |

---

### 🏗️ 工作区与配置

| 命令 | 何时用 | 用法 | 返回 |
|:----|:------|:----|:-----|
| `workspace init --path <dir>` | 新项目初始化 | `traectl workspace init --path ./my-proj` | 创建的项目结构 |
| `install-skills` | 安装 Agent skills | `traectl install-skills --target ./skills` | 安装结果 |
| `config get <key>` | 读取配置 | `traectl config get cdp_port` | 配置值 |
| `config set <key> <val>` | 设置配置 | `traectl config set solo_timeout 600` | 确认 |
| `config list` | 列出所有配置 | `traectl config list` | 配置表 |

---

### 🔌 连接与自省

| 命令 | 何时用 | 用法 |
|:----|:------|:-----|
| `health` | **每次操作前必须先执行** | `traectl health` |
| `version` | 确认版本 | `traectl version` |
| `commands` | 列出所有可用命令 | `traectl commands` |
| `help <cmd>` | 查看命令详细帮助 | `traectl help submit` |
| `schema --command <name>` | **参数不确定时先查** | `traectl schema --command submit` |
| `categories` | 按分组浏览命令 | `traectl categories` |
| `exit-codes` | 查看退出码说明 | `traectl exit-codes` |

**🔄 参数不确定时的标准流程：**
1. `traectl commands` 确认命令存在
2. `traectl schema --command <name>` 查看参数结构
3. `traectl help <name>` 查看详细用法
4. 再执行实际命令

---

## 典型工作流

### 1️⃣ 日常编码任务（最常用）

```
traectl health                           # 1. 先健康检查
traectl submit "实现用户登录功能"          # 2. 提交任务（自动等待）
traectl file-changes                     # 3. 查看改动
traectl accept                           # 4. 接受改动
traectl git status                       # 5. 确认 Git 状态
traectl git commit -m "feat: 登录功能"    # 6. 提交
```

### 2️⃣ 后台提交 + 轮询（适合长时间任务）

```bash
traectl health
traectl new                              # 清空上下文
cat task.md | traectl submit '请读取任务描述并执行' --no-wait   # 后台提交
sleep 120                                # 等 2 分钟
traectl chat --max-length 5000           # 读取结果
traectl file-changes                     # 检查变更
```

### 3️⃣ 角色分工流水线（多 Agent）

```bash
# 架构师
traectl submit "设计系统架构" --role architect --wait
# 后端
traectl new && traectl submit "实现 API" --role backend --wait
# 前端
traectl new && traectl submit "实现页面" --role frontend --wait
# 审查
traectl new && traectl submit "审查代码" --role reviewer --wait
```

**每步之间必须：** `git add -A && git commit -m 'step log'` 保存进度，再开始下一步。

### 4️⃣ 批量简单任务

当多个不冲突的新增任务时（不涉及修改核心逻辑、不修改同一文件）：

```bash
traectl submit "请实现以下功能：\n1. version 子命令\n2. config 子命令组\n3. help 子命令"
```

**判断标准：** 每个功能 1-2 句话能说清、不涉及现有逻辑改动、标准样板代码。

### 5️⃣ 模型切换调度

```bash
# 先确认当前模型
traectl models
# 切换
traectl switch Kimi-K2.6
# 验证
traectl health
```

**大小写敏感：** `traectl switch kimi-k2.6` 失败，必须 `Kimi-K2.6`。以 `traectl models` 输出为准。

### 6️⃣ 新项目初始化

```bash
traectl workspace init --path ./my-project --type python --skills "github/github-issues"
```

---

## 错误处理协议

| 错误表现 | 原因 | Agent 行为 |
|:--------|:-----|:----------|
| `health` 返回 `ok: false` | CDP 未就绪 | 报告用户：Trae CN 可能未运行，启动后重试 |
| `submit` 60s 超时 | 默认等待超时 | 检查 `chat` 是否已有内容；用 `--no-wait` 模式重试+轮询 |
| exit code 4 | 可重试错误 | 等待 5s → 重试，最多 3 次 |
| exit code 10 | 高风险未确认 | ⛔ 禁止自动 --yes，必须向用户展示操作 |
| `action delete_task` 失败 | 无任务可删 | 用 `action get_tasks` 先确认 |
| `switch` 无响应 | 选择器未加载 | 等 5-10s 重试，或先 `traectl models` 确认模型已选中 |
| CDP 连接丢失 | Trae CN 崩溃 | 终止当前流程，向用户报告 |
| 弹窗阻塞操作 | 确认/排队弹窗 | 用 `action confirm` 或 `close-dialog` 处理 |

---

## ⚠️ 重要限制

| 限制 | 说明 |
|:----|:-----|
| **串行任务** | 一次只能有一个任务在活动。`submit --no-wait` 后需等上一个完成再提新任务 |
| **超时机制** | `submit --wait` 默认 60s 超时。长时间任务用 `--no-wait` + 轮询 |
| **模型名大小写** | `traectl switch` 严格区分大小写。始终以 `traectl models` 输出为准 |
| **CDP 端口** | 默认 9222（Trae CN 标准端口）。多个实例用 `--port` 区分 |
| **弹窗干扰** | 切换模型或操作时可能弹出确认框，用 `auto-recover` 或 `action confirm` 处理 |

---

## 最佳实践总结

| 场景 | 做法 |
|:----|:-----|
| **不确定命令参数** | `traectl schema --command <name>` |
| **不确定可用命令** | `traectl commands` |
| **不确定退出码含义** | `traectl exit-codes` |
| **想预览操作** | 加 `--dry-run` |
| **跳过交互确认** | 加 `--yes`（仅非交互 agent 用） |
| **读聊天记录** | `traectl chat --max-length 5000` |
| **监视文件变化** | `traectl file-status --dir . --glob "*.py"` |
| **safe-first** | 每次操作前先 `traectl health` |

---

## 参考文件

| 文件 | 内容 | 优先级 |
|:----|:-----|:------|
| [`references/submit-workflow.md`](references/submit-workflow.md) | 任务提交流程详解（标准/后台/角色化/超时处理） | 🔴 必读 |
| [`references/model-switch.md`](references/model-switch.md) | 模型切换步骤、陷阱、cron 调度 | 🟡 常用 |
| [`references/dialog-handling.md`](references/dialog-handling.md) | 8 种弹窗分类及处理方式 | 🟡 遇到弹窗时读 |
| [`references/exit-code-protocol.md`](references/exit-code-protocol.md) | 退出码 10 协议的详细规范 | 🔴 必读 |
| [`references/batch-submit.md`](references/batch-submit.md) | 批量/并发提交的策略与禁忌 | 🟢 优化性能时读 |
