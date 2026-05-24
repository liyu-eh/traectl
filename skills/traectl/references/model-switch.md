# 模型切换流程（switch）

**⛔ 切换前必须先执行 `traectl models` 确认当前模型。已是目标模型则跳过切换。**

---

## 标准切换

```bash
traectl switch Kimi-K2.6
```

### 执行链路

| 步骤 | 操作 | 技术 | 耗时 |
|:----|:-----|:-----|:----|
| 1 | 读取当前模型文本 | `eval_js` 读 trigger 显示文本 | ~0.5s |
| 2 | 已是目标模型？ | 模糊匹配（处理 Beta 后缀截断） | 跳过 |
| 3 | 打开模型选择器 | `dispatchEvent(new MouseEvent('mousedown'))` | ~0.5s |
| 4 | 等待列表渲染 | 轮询 17 次 × 0.3s | ~5s |
| 5 | 查找并点击目标模型 | querySelectorAll 遍历匹配 → scrollIntoView → .click() | ~1s |
| 6 | 验证切换结果 | 重新读取当前模型 + `_model_name_match()` | ~1s |
| 7 | 失败兜底 | SQLite 覆写 state.vscdb + 重启 Trae CN | ~10s |

### 返回结构

```json
{
  "ok": true,
  "data": {
    "result": "模型已切换至 Kimi-K2.6",
    "model": "Kimi-K2.6"
  }
}
```

---

## 重要陷阱

### ⚠️ 模型名称大小写敏感

**MUST：** `traectl switch` 严格区分大小写。

| 错误 | 正确 |
|:----|:-----|
| `traectl switch kimi-k2.6` | `traectl switch Kimi-K2.6` |
| `traectl switch deepseek` | `traectl switch DeepSeek-V4-Pro` |

**以 `traectl models` 输出中的名称为准。**

### ⚠️ UI 截断

选择器 trigger 文本可能被 UI 截断。例如选中 "GLM-5.1Beta" 后 trigger 显示 "GLM-5.1"（空间不够）。比较时使用 `startswith()` 而非全等。

### ⚠️ 启动后首次切换

Trae CN 刚启动时 SOLO 面板可能未完全加载，此时 `traectl switch` 可能报「未找到模型选择器 trigger」。

**应对：** 等 CDP 就绪后再等待 10-15 秒再切，或先 `traectl models` 确认选择器已可用。

### ⚠️ CDP 鼠标事件可能被 React 拦截

模型选择器的核心交互依赖于 `dispatchEvent(new MouseEvent('mousedown', {bubbles: true}))`。如果 React 合成事件系统拦截了此事件：

1. 自动重试 3 次
2. 失败后降级为纯 JS 方式重试
3. 最终 fallback：SQLite 直接覆写 + 重启

---

## 多模型切换（cron 调度）

配合系统 cron 实现白天/夜间自动切换：

```bash
# 白天用 Kimi-K2.6（高性能）
0 9 * * * traectl switch Kimi-K2.6 --port 9222

# 夜间切经济模型
0 1 * * * traectl switch GLM-5.1 --port 9222
```

可接受的模型组合参考：
- 白天：`Kimi-K2.6`、`DeepSeek-V4-Pro`
- 夜间：`GLM-5.1`、`DeepSeek-V4-Flash`
