# 任务提交流程（submit）

**提交前必须先执行 `traectl health` 确认 CDP 就绪。**

---

## 标准提交（自动等待）

```bash
traectl submit "实现用户登录功能"
```

| 阶段 | 发生什么 | 时长 |
|:----|:---------|:----|
| 1 | ensure_idle：检测上一个任务是否完成 | ~2s |
| 2 | start_new_task：JS 点击新任务按钮 | ~1s |
| 3 | type_message：CDP Input.insertText 输入 prompt | ~1s |
| 4 | send_message：JS 点击发送按钮 | ~1s |
| 5 | ResponseWaiter：状态机轮询（排队→生成→hash 稳定→完成） | 10-300s |
| 6 | 返回 JSON：`{ok, data, type, metadata}` | — |

**返回 data 结构：**
```json
{
  "content": "SOLO 生成的聊天内容...",
  "taskId": "task_xxx",
  "model": "Kimi-K2.6",
  "hasChanges": true,
  "fileChanges": ["src/main.py", "src/utils.py"]
}
```

---

## 后台提交（不等待）

当任务预计超过 60s 时用：

```bash
cat task.md | traectl submit '请读取任务描述并执行。' --no-wait
```

提交后不等待完成，需自行轮询检查：

```bash
# 1. 等一段时间
sleep 120

# 2. 检查聊天内容
traectl chat --max-length 5000

# 3. 检查文件变更
traectl file-changes

# 4. 接受改动
traectl accept
```

---

## 角色化提交

当需要指定 Agent 角色时：

```bash
traectl submit "设计数据库 Schema" --role architect
traectl submit "实现 CRUD API" --role backend --model Kimi-K2.6
```

`submit_task_with_role()` 自动执行：
1. 查 AGENT_ROLES 获取角色 prompt 模板
2. 若指定了 `--model` 先 `switch_model()` 切换
3. 角色 prompt + 用户任务描述 拼接后提交

可用角色：`architect`、`frontend`、`backend`、`tester`、`reviewer`、`debugger`

---

## Dry-run 预览

```bash
traectl submit "实现功能" --dry-run
```

返回 JSON 化的执行计划，不实际操作：

```json
{
  "ok": true,
  "dryRun": true,
  "plan": {
    "action": "submit_task",
    "role": "backend",
    "model": "Kimi-K2.6",
    "prompt": "实现功能"
  },
  "metadata": { "confirmationId": "abc123" }
}
```

---

## 超时处理

| 超时类型 | 表现 | 处理 |
|:--------|:-----|:-----|
| submit --wait 60s 默认超时 | 返回已有内容 | 用 `--no-wait` 重新提交 + 轮询 |
| SOLO 思考超时 | ResponseWaiter 返回半成品 | 检查 `file-changes` 是否有已写入文件；用 `_salvage_editor_content()` 捞取编辑器内容 |
| 排队超长 | Status: 排第 N 位 | 每 30s 重查一次排队位置 |

**超时后的最佳实践：**
1. `traectl chat --max-length 5000` 检查已有内容
2. `traectl file-changes` 检查是否有已写入的文件
3. 若已有部分内容，`traectl send "继续完成"` 追加指令
4. 若无内容，`traectl new` 清空后重新提交
