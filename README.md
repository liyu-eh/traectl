<p align="center">
  <img src="https://img.shields.io/badge/python-3.11%2B-blue" alt="Python">
  <img src="https://img.shields.io/github/actions/workflow/status/liyu-eh/traectl/ci.yml?branch=master" alt="CI">
  <img src="https://img.shields.io/github/license/liyu-eh/traectl" alt="License">
  <img src="https://img.shields.io/badge/status-beta-orange" alt="Status">
</p>

<h1 align="center">traectl</h1>
<p align="center"><strong>通过 CDP JavaScript 注入控制 Trae CN SOLO 编码代理的命令行工具</strong></p>

<p align="center">
  AI Agent 原生设计 · JSON 输出 · 全命令自省 · 34 个操作命令
</p>

---

## 概述

`traectl` 让你不用鼠标键盘，直接在终端里操控 [Trae CN](https://trae.cn) SOLO 编码代理。

**核心原理：** 通过 Chrome DevTools Protocol 连接 Trae CN 的调试端口，向浏览器上下文注入 JavaScript，直接调用 DOM API 操控 Trae CN 界面——**比模拟鼠标点击更可靠，能绕过 React 合成事件的拦截**。

**适用场景：**
- 🤖 服务器上无头运行 Trae CN
- ⏰ 定时任务切换模型（配合 cron 白天/夜间自动切）
- 🔄 CI/CD 流水线中自动提交编码任务
- 📊 批量监控多个工作区的 SOLO 状态

---

## 架构

```
┌─────────────────────────────────────────────────────┐
│  CLI 层 (Typer)                                      │
│  submit / switch / health / chat / exec / ...       │
└──────────────────────┬──────────────────────────────┘
                       ↓
┌──────────────────────┴──────────────────────────────┐
│  Controller 层 (7 Mixins)                            │
│  TaskMixin / ChatMixin / ModelMixin / ...           │
└──────────────────────┬──────────────────────────────┘
                       ↓
┌──────────────────────┴──────────────────────────────┐
│  CDP 通信层 (WebSocket + JS 注入)                    │
│  CDPClient.eval_js("document.querySelector()...")   │
│  ← Runtime.evaluate → 直接在浏览器执行 JavaScript    │
└──────────────────────┬──────────────────────────────┘
                       ↓
┌──────────────────────┴──────────────────────────────┐
│  Trae CN (Electron)                                  │
│  接收 JS 操控: 提交任务 / 切模型 / 改文件 / 执行命令  │
└─────────────────────────────────────────────────────┘
```

---

## 安装

```bash
# 从 GitHub 直接安装（推荐）
pip install git+https://github.com/liyu-eh/traectl.git

# 或从源码
git clone https://github.com/liyu-eh/traectl.git
cd traectl
pip install -e .
```

## 前置条件

Trae CN 必须以远程调试模式启动：

```bash
# 无头服务器
DISPLAY=:99 trae-cn --disable-gpu-sandbox --remote-debugging-port=9224 &

# 有桌面环境
trae-cn --remote-debugging-port=9224
```

确认 CDP 端口可访问：

```bash
ss -tlnp | grep 9224
```

---

## 快速开始

```bash
# 健康检查
traectl health --port 9224

# 查看可用模型
traectl models --port 9224

# 切换模型（通过 JS 注入点击选择器，不用模拟鼠标）
traectl switch Kimi-K2.6 --port 9224

# 提交编码任务
traectl submit "用 Python 实现一个命令行计算器" --port 9224

# 查看任务状态
traectl status --port 9224

# 查看聊天记录
traectl chat --port 9224
```

---

## 命令大全

### 🎯 任务管理

| 命令 | 说明 | 高风险 |
|:----|:-----|:------:|
| `submit <task>` | 向 SOLO 提交编码任务 | |
| `send <message>` | 在当前会话发送消息 | |
| `new` | 创建新任务会话 | |
| `status` | 获取当前执行状态 | |
| `chat` | 读取聊天记录 | |
| `action stop` | 停止生成 | ⚠️ |
| `action delete_task` | 删除当前任务 | ⚠️ |
| `action switch_task -i N` | 切换到指定任务 | |
| `action get_tasks` | 列出所有任务 | |
| `regenerate` | 重新生成最后回复 | ⚠️ |
| `plan <json>` | 多 Agent 计划执行 | |

### 📁 文件管理

| 命令 | 说明 |
|:----|:------|
| `file-changes` | 查看 SOLO 提议的变更 |
| `accept [-f <path>]` | 接受文件变更 |
| `reject [-f <path>]` | 拒绝文件变更 |
| `file-status [-d <dir>]` | 监视文件变化状态 |

### 🖥️ 终端操作

| 命令 | 说明 |
|:----|:------|
| `exec <command>` | 在 Trae CN 终端执行命令 |
| `terminal` | 切换终端面板显示/隐藏 |
| `terminal-content` | 获取终端文本内容 |

### 🔧 Git 操作

| 命令 | 说明 |
|:----|:------|
| `git status` | 查看仓库状态 |
| `git diff` | 查看变更差异 |
| `git stage [-f <path>]` | 暂存文件 |
| `git commit -m <msg>` | 提交变更 |
| `git log` | 查看提交历史 |
| `git branch` | 查看分支 |

### 🤖 Agent 管理

| 命令 | 说明 |
|:----|:------|
| `roles` | 列出所有 Agent 角色 |
| `analyze <task>` | 分析任务推荐最佳角色和模型 |
| `close-dialog` | 关闭弹窗 |
| `auto-recover` | 智能识别并处理弹窗 |

### 📸 辅助

| 命令 | 说明 |
|:----|:------|
| `screenshot [-s <path>]` | 截取 Trae CN 界面 |
| `editor` | 查看当前打开的文件 |
| `models` | 列出可用模型 |
| `switch <model>` | 切换模型 |
| `health` | 健康检查 |

### 🏗️ 配置与工作区

| 命令 | 说明 |
|:----|:------|
| `workspace init --path <dir>` | 初始化项目工作区 |
| `install-skills` | 安装 Agent skills |
| `config get/set/list/export` | 配置管理 |

### 🔍 自省

| 命令 | 说明 |
|:----|:------|
| `commands` | 列出所有可用命令 |
| `schema [--command <name>]` | 输出 JSON Schema |
| `categories` | 按类别分组命令 |
| `exit-codes` | 列出退出码说明 |
| `help [command]` | 显示帮助信息 |
| `version` | 输出版本信息 |

---

## 输出格式

所有命令默认输出 JSON，AI Agent 原生友好：

```json
{
  "schemaVersion": 1,
  "type": "health.check",
  "ok": true,
  "data": {
    "connected": true,
    "current_model": "Kimi-K2.6",
    "tasks": 3
  },
  "metadata": {
    "timestamp": "2026-05-24T07:00:00Z"
  }
}
```

| 参数 | 说明 |
|:----|:------|
| `--human` | 人类可读输出（纯文本） |
| `--output ndjson` | 流式 JSON（每行一条） |
| `--output json` | 标准 JSON（默认） |
| `--debug` | 启用调试日志 |

---

## 环境变量

| 变量 | 默认值 | 说明 |
|:-----|:------:|:-----|
| `CDP_PORT` | 9224 | Trae CN CDP 调试端口 |
| `CDP_HOST` | localhost | CDP 主机地址 |
| `SOLO_TIMEOUT` | 120 | SOLO 响应超时（秒） |
| `SOLO_STABLE_THRESHOLD` | 3 | 内容稳定判断次数 |

---

## 场景示例

### 定时切换模型

通过系统 cron 定时切换模型，白天用高性能模型，夜间切经济模型：

```bash
# 白天用 Kimi-K2.6
0 9 * * * traectl switch kimi-k2.6 --port 9224

# 夜间切经济模型
0 1 * * * traectl switch glm-5.1 --port 9224
```

### 自动化任务提交流程

```bash
traectl new --port 9224 &&
traectl submit "修复登录页面的 CSS 样式问题" --port 9224 &&
traectl status --port 9224 --wait &&
traectl file-changes --port 9224 &&
traectl accept --port 9224
```

### 批量监控

```bash
# 查看所有工作区状态
for port in 9224 9225 9226; do
  traectl health --port $port --human
done
```

---

## 安全

- **高风险操作保护**：`delete_task`、`stop`、`regenerate` 需要 `--yes` 确认
- **dry-run 模式**：`submit`、`send`、`accept`、`reject`、`exec`、`git`、`action`、`switch` 支持 `--dry-run` 预览
- **JSON 响应**：所有操作返回标准化的 `ok`/`error` 响应格式

---

## 开发

```bash
# 安装开发依赖
pip install -e .
pip install pytest

# 运行测试
python -m pytest -v

# 查看命令
traectl --human --help
traectl schema --json
```

## 许可证

MIT
