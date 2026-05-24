#!/usr/bin/env python3
"""标准看门狗脚本 — 监测文件变更 → 跑测试 → 写状态文件

用法: python3 watchdog.py <project_dir> <timeout_minutes> [target_file1 target_file2 ...]

工作模式：
1. 每 30s 监测指定文件的 md5sum 变化
2. 检测到变化后运行测试
3. 结果写入 ~/.hermes/watchdog_status.json
4. stdout 输出结果摘要（notify_on_complete 捕获）
"""

import hashlib
import json
import os
import subprocess
import sys
import time

STATUS_FILE = os.path.expanduser("~/.hermes/watchdog_status.json")
INTERVAL = 30  # 每 30 秒检查一次


def md5(path: str) -> str:
    try:
        return hashlib.md5(open(path, "rb").read()).hexdigest()
    except FileNotFoundError:
        return ""


def run_tests(project_dir: str) -> dict:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=line"],
        capture_output=True, text=True, timeout=60, cwd=project_dir,
    )
    output = result.stdout.strip().split("\n")
    last_line = output[-1].strip() if output else "no output"
    passed = "passed" in last_line
    return {
        "output": last_line,
        "passed": passed,
        "exit_code": result.returncode,
    }


def write_status(task_name: str, status: str, detail: dict):
    data = {
        "task": task_name,
        "status": status,
        "detail": detail,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
    with open(STATUS_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    # Also print for notify_on_complete capture
    print(f"\n=== WATCHDOG RESULT ===")
    print(f"Task: {task_name}")
    print(f"Status: {status}")
    if detail:
        print(f"Detail: {json.dumps(detail, ensure_ascii=False)}")
    print(f"======================\n")


def main():
    if len(sys.argv) < 3:
        print("Usage: watchdog.py <project_dir> <timeout_minutes> [files...]")
        sys.exit(1)

    project_dir = sys.argv[1]
    timeout_min = int(sys.argv[2])
    target_files = sys.argv[3:] if len(sys.argv) > 3 else []

    if not target_files:
        # Default: monitor all changed files via git
        result = subprocess.run(
            ["git", "diff", "--name-only"],
            capture_output=True, text=True, cwd=project_dir, timeout=10,
        )
        target_files = [f.strip() for f in result.stdout.split("\n") if f.strip()]

    if not target_files:
        # If no git changes, monitor key source files
        target_files = [
            "src/traectl/mixins/media_mixin.py",
            "src/traectl/mixins/chat_mixin.py",
            "src/traectl/mixins/model_mixin.py",
            "src/traectl/mixins/task_mixin.py",
            "src/traectl/mixins/editor_mixin.py",
            "src/traectl/mixins/terminal_mixin.py",
            "src/traectl/mixins/git_mixin.py",
            "src/tractl/config.py",
            "src/traectl/cli.py",
            "src/traectl/workspace_manager.py",
        ]

    # Take initial snapshots
    prev = {f: md5(os.path.join(project_dir, f)) for f in target_files}
    cycles = int((timeout_min * 60) / INTERVAL)

    write_status("watchdog", "running", {
        "monitoring": target_files,
        "timeout_min": timeout_min,
        "interval": INTERVAL,
    })

    for cycle in range(1, cycles + 1):
        time.sleep(INTERVAL)

        # Check for changes
        changed = []
        for f in target_files:
            curr = md5(os.path.join(project_dir, f))
            if prev.get(f) and curr != prev.get(f):
                changed.append(f)
            prev[f] = curr

        if not changed:
            continue

        # Changes detected! Run tests
        test_result = run_tests(project_dir)

        if test_result["passed"]:
            write_status("watchdog", "completed", {
                "changed_files": changed,
                "test_result": test_result["output"],
                "cycle": cycle,
            })
            sys.exit(0)
        else:
            # Tests failed — still report but don't exit
            write_status("watchdog", "test_failed", {
                "changed_files": changed,
                "test_result": test_result["output"],
                "cycle": cycle,
            })
            # Update snapshots and continue monitoring
            prev = {f: md5(os.path.join(project_dir, f)) for f in target_files}

    # Timeout reached
    write_status("watchdog", "timeout", {
        "message": f"监测 {timeout_min} 分钟未检测到变更",
        "cycles": cycles,
    })
    sys.exit(1)


if __name__ == "__main__":
    main()
