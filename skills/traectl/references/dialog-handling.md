# 弹窗处理（auto-recover / close-dialog）

**⛔ 当操作被弹窗阻塞时，不要反复重试命令。先处理弹窗再继续。**

---

## 快速处理

```bash
# 方法 1：智能自动处理（推荐）
traectl auto-recover

# 方法 2：关闭当前弹窗
traectl close-dialog

# 方法 3：确认弹窗（确定/运行/确认）
traectl action confirm
```

---

## 8 种弹窗分类

auto-recover 自动扫描页面，通过 DIALOG_PATTERNS 正则匹配树分类（匹配 pattern 最多的类型胜出）：

| 类型 | 触发场景 | 处理方式 | 最多重试 |
|:----|:---------|:--------|:--------|
| `server_error` | 服务端异常 / 未知错误 | 点击「继续」 | 3 次 |
| `error_2000000` | 系统未知错误 2000000 | 同样点击「继续」 | 3 次 |
| `update_dialog` | 版本更新提醒 | 点击「忽略」/「稍后」 | 1 次 |
| `queue_reminder` | 排在第 N 位 | 读取位置号，仅报告不操作 | — |
| `confirm_dialog` | 「运行」/「确认」/「确定」 | 自动点击「运行」按钮 | 1 次 |
| `permission_dialog` | 权限申请 / 授权 | 针对性处理 | 1 次 |
| `resource_warning` | 资源不足 / 内存不足 | 针对性处理 | 1 次 |
| `retry_dialog` | 重试 / 重新连接 | 点击重试 | 1 次 |

---

## 失败兜底

如果 auto-recover 无法识别弹窗类型：

```
close-dialog 退路：
  1. JS 查找并点击关闭按钮（.close, [class*=close], [aria-label*=关闭]）
  2. 发送 Escape 键（dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape'}))）
  3. CDP Input.dispatchKeyEvent Escape

如果仍无法关闭：
  1. traectl screenshot 截图看弹窗内容
  2. 手动判断弹窗类型
  3. 针对性处理
```

---

## 已知影响操作的弹窗

| 场景 | 弹窗 | 处理建议 |
|:----|:-----|:--------|
| 切换模型 | 「是否确认切换模型？」 | `action confirm` |
| 删除任务 | 「确认删除当前任务？」 | `action delete_task --yes` |
| 执行命令 | 「允许终端执行命令？」 | `action confirm` |
| 网络错误 | 「连接断开，重试？」 | `auto-recover` |
