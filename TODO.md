# TraeCLI 待修复列表

## 已知问题

### 1. cli.py StandardResponse 适配未完成
- **状态：** ✅ 已重启 Trae CN + 已重新提交任务，正在生成中
- **描述：** Trae CN 子代理在执行任务时连续两次服务端错误，已重启 + 提交新任务
- **进度：** controller.py 已全部改完（33/33 ✅）并已 commit（`57de4a0`）；cli.py 已改 submit/models/switch/chat/status 并已 commit；新任务从 health 开始继续
- **根因：** 子代理并发操作过多导致 Trae CN 服务端不稳定
- **待处理：** 看门狗盯梢中，等待新任务完成剩余命令 + test_cli.py + CONSTANTS

### 2. Trae CN 子代理服务端错误 (2000000)
- **状态：** 已重启 Trae CN，新任务已提交，正在观察
- **描述：** 子代理执行 `Update cli.py for StandardResponse` 时连续两次报错：
  - 第一次：`服务端异常，请稍后重试 (-1)`
  - 第二次：`系统未知错误，请尝试新建任务或者重启 TRAE (2000000)`
- **根因：** 可能是子代理并发操作过多导致 Trae CN 服务端不稳定
- **处理：** 已重启 Trae CN + 提交新任务（清理状态重新开始），当前新任务正常生成中

### 3. VNC 显示异常
- **状态：** 待观察
- **描述：** VNC 连接 Trae CN 界面显示异常（可能重启后可恢复）
- **待处理：** 确认是否与 Trae CN 服务端异常有关

---

## 已完成

### Phase 1: StandardResponse 统一 (controller.py)
- 33 个 public 方法全部从 `-> str` 改为 `-> StandardResponse`
- 私有方法保持 `-> str`，由 public 方法包装
- 测试全部通过（21/21）

### Trae CN 看门狗 Skill
- `software-development/trae-task-watchdog` 已安装
- 内含 `watchdog.sh` 脚本模板和完整流程规范
