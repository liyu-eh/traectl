# 退出码协议

**⛔ 退出码是 AI Agent 不可忽略的信号。每次命令执行后必须检查退出码。禁止在未读退出码的情况下继续执行后续操作。**

---

## 退出码总表

| 退出码 | 名称 | 含义 | Agent 行为 |
|:-----:|:-----|:-----|:----------|
| **0** | `EXIT_SUCCESS` | 操作成功 | ✅ 正常读取 `data`，继续流程 |
| **1** | `EXIT_GENERAL_ERROR` | 未指定的一般错误 | ❌ 读取 `error.message`，向用户报告或终止 |
| **2** | `EXIT_USAGE_ERROR` | 参数/用法错误 | ❌ 调用 `traectl schema --command <name>` 自查参数 |
| **3** | `EXIT_AUTH_ERROR` | 认证/权限错误 | ❌ 向用户报告，不要重试 |
| **4** | `EXIT_RETRYABLE` | 可重试错误（限流、网络超时） | 🔄 等待 5-30s 后重试，最多 3 次 |
| **10** | `EXIT_CONFIRMATION_REQUIRED` | ⚠️ **高风险操作待确认** | **见下方专用协议** |

---

## 🚨 exit code 10 协议

### 触发命令

| 命令 | 风险 | 说明 |
|:----|:----:|:-----|
| `action delete_task` | ⚠️ 高 | 删除当前任务会话 |
| `action stop` | ⚠️ 高 | 停止生成中的代码 |
| `regenerate` | ⚠️ 高 | 重新生成最后回复 |

### 禁止行为（MUST NOT）

- ❌ **禁止**对 exit 10 的命令自动追加 `--yes`
- ❌ **禁止**向用户报告「操作已执行」
- ❌ **禁止**跳过确认继续执行后续流程
- ❌ **禁止**把 exit 10 当作普通 `ok: false` 处理

### 强制行为（MUST）

1. ✅ 立即停止当前执行链
2. ✅ 提取操作详情（命令 + 参数 + 影响范围）
3. ✅ 向用户展示以下格式的确认请求：
   > ⚠️ 高风险操作确认
   > 命令：`traectl action delete_task --port 9222`
   > 影响：删除当前任务会话
   > 请回复「确认」继续，或「取消」中止。
4. ✅ 等待用户明确回应
5. ✅ 用户确认后，在原命令后追加 `--yes` 执行：

   ```bash
   traectl action delete_task --port 9222 --yes
   ```
6. ✅ 执行成功后再继续后续流程

### 自动化场景

在非交互式脚本/CI/CD 中，调用高风险命令时直接带 `--yes`：

```bash
traectl action stop --port 9222 --yes
traectl action delete_task --port 9222 --yes
```

但**仅限**确认用户已明确授权自动化执行的场景。

---

## exit code 4（可重试）处理

```python
# Python 脚本中的重试逻辑
max_retries = 3
for attempt in range(max_retries):
    result = run("traectl submit ...")
    if result.exit_code == 4:
        wait = min(5 * (2 ** attempt), 30)  # 5s, 10s, 20s
        print(f"🔄 可重试错误，等待 {wait}s 后重试...")
        sleep(wait)
        continue
    elif result.exit_code == 0:
        break
```

---

## exit code 2（参数错误）处理

```bash
# 先查 schema
traectl schema --command submit

# 再查 help
traectl help submit

# 确认参数后再执行
cat task.md | traectl submit '请读取 stdin 中的任务描述并执行。'
```
