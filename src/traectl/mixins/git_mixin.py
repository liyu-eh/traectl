#!/usr/bin/env python3
"""GitMixin — Git 操作：status、stage、commit、统一入口。"""

import asyncio
import os
import subprocess

from ..response import StandardResponse



class GitMixin:
    """Git 操作 Mixin：本地 Git 命令执行。"""

    def _detect_git_dir(self) -> str:
        """自动检测 Git 根目录（向上查找 .git 目录）。"""
        cwd = self._workspace_root
        # 如果 workspace_root 本身就是 git 仓库根目录
        git_dir = os.path.join(cwd, ".git")
        if os.path.isdir(git_dir):
            return cwd
        # 向上查找
        parent = os.path.dirname(cwd)
        while parent and parent != cwd:
            if os.path.isdir(os.path.join(parent, ".git")):
                return parent
            cwd = parent
            parent = os.path.dirname(cwd)
        return self._workspace_root

    async def git_status(self) -> StandardResponse:
        """获取 Git 工作树状态（本地执行，不经过终端）。"""
        try:
            git_dir = self._detect_git_dir()
            if not os.path.isdir(os.path.join(git_dir, ".git")):
                return StandardResponse(result={"error": "未找到 Git 仓库"}, message="Git 仓库未找到", code=-1)
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    ["git", "status", "--short"],
                    capture_output=True, text=True, cwd=git_dir, timeout=15,
                ),
            )
            output = result.stdout.strip() or result.stderr.strip()
            data = {
                "git_dir": git_dir,
                "output": output,
                "exit_code": result.returncode,
            }
            return StandardResponse(result=data, message="Git 状态", code=0)
        except Exception as e:
            return StandardResponse(result=None, message=f"Git 状态失败: {e}", code=-1)

    async def git_stage(self, file_path: str = "") -> StandardResponse:
        """暂存 Git 变更（本地执行）。如果指定 file_path 则暂存该文件，否则暂存全部。"""
        try:
            git_dir = self._detect_git_dir()
            cmd = ["git", "add", file_path] if file_path else ["git", "add", "-A"]
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(cmd, capture_output=True, text=True, cwd=git_dir, timeout=15),
            )
            data = {
                "action": "stage",
                "file_path": file_path or "all",
                "git_dir": git_dir,
                "output": (result.stdout or result.stderr).strip(),
                "exit_code": result.returncode,
            }
            return StandardResponse(result=data, message="Git 暂存", code=0)
        except Exception as e:
            return StandardResponse(result=None, message=f"Git 暂存失败: {e}", code=-1)

    async def git_commit(self, message: str) -> StandardResponse:
        """提交暂存的变更（本地执行）。"""
        try:
            git_dir = self._detect_git_dir()
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    ["git", "commit", "-m", message],
                    capture_output=True, text=True, cwd=git_dir, timeout=15,
                ),
            )
            data = {
                "action": "commit",
                "message": message,
                "git_dir": git_dir,
                "output": (result.stdout or result.stderr).strip(),
                "exit_code": result.returncode,
            }
            return StandardResponse(result=data, message="Git 提交", code=0)
        except Exception as e:
            return StandardResponse(result=None, message=f"Git 提交失败: {e}", code=-1)

    async def git(self, action: str, file_path: str = "", message: str = "") -> StandardResponse:
        """统一的 Git 操作入口。action: status|stage|commit|diff|log|branch"""
        try:
            git_dir = self._detect_git_dir()
            cmd_map = {
                "status": ["git", "status", "--short"],
                "diff": ["git", "diff", "--stat"],
                "log": ["git", "log", "--oneline", "-10"],
                "branch": ["git", "branch"],
            }
            if action == "stage":
                cmd = ["git", "add", file_path] if file_path else ["git", "add", "-A"]
            elif action == "commit":
                if not message:
                    return StandardResponse(result=None, message="commit 需要 message 参数", code=-1)
                cmd = ["git", "commit", "-m", message]
            else:
                cmd = cmd_map.get(action)
                if not cmd:
                    return StandardResponse(result=None, message=f"未知 action: {action}，支持: status|stage|commit|diff|log|branch", code=-1)

            loop = asyncio.get_event_loop()
            try:
                result = await loop.run_in_executor(
                    None,
                    lambda: subprocess.run(cmd, capture_output=True, text=True, cwd=git_dir, timeout=15),
                )
                output = (result.stdout or result.stderr).strip()
                return StandardResponse(result=output, message=f"Git {action}", code=0)
            except subprocess.TimeoutExpired:
                return StandardResponse(result=None, message=f"Git {action} 超时", code=-1)
        except Exception as e:
            return StandardResponse(result=None, message=f"Git 操作失败 ({action}): {e}", code=-1)
