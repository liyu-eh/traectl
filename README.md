# traectl — 通过 CDP 控制 Trae CN SOLO 编码代理

基于 Chrome DevTools Protocol 操控 Trae CN SOLO 编码代理的命令行工具。

## 功能

| 类别 | 命令 | 说明 |
|------|------|------|
| 🎯 **任务提交** | `traectl submit` | 向 SOLO Agent 提交编码任务 |
| 💬 **对话** | `traectl chat` | 交互式对话模式 |
| 📊 **状态查询** | `traectl health` | 健康检查 |
| | `traectl status` | 任务执行状态 |
| | `traectl models` | 列出可用模型 |
| 🏗️ **工作区** | `traectl workspace init` | 初始化项目工作区 |
| | `traectl workspace setup-mcp` | 管理 MCP 服务器配置 |
| | `traectl install-skills` | 安装 Agent skills |
| 🔧 **配置** | `traectl config get/set/list` | 配置管理 |

## 安装

```bash
pip install traectl
# 或从源码
pip install -e .
```

## 前置条件

Trae CN 以远程调试模式启动：

```bash
DISPLAY=:99 trae-cn --disable-gpu-sandbox --remote-debugging-port=9222
```

## 快速开始

```bash
# 健康检查
traectl health

# 初始化项目工作区
traectl workspace init --path ./my-project

# 配置 MCP 服务器
traectl workspace setup-mcp add --name filesystem --command "npx" --args "-y,@modelcontextprotocol/server-filesystem,./my-project"

# 提交编码任务
traectl submit "实现一个命令行计算器"

# 交互式对话
traectl chat
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CDP_PORT` | 9222 | Trae CN CDP 调试端口 |
| `CDP_HOST` | localhost | CDP 主机地址 |
| `SOLO_TIMEOUT` | 120 | SOLO 响应超时(秒) |
| `SOLO_STABLE_THRESHOLD` | 3 | 内容稳定判断次数 |

## 开发

```bash
# 安装开发依赖
pip install -e .
pip install pytest

# 运行测试
python -m pytest -q

# 查看命令
traectl --help
traectl workspace --help
traectl config --help
traectl schema --json
```
