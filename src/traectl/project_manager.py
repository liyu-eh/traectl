#!/usr/bin/env python3
"""项目总经理：分析任务，分配给合适的 Agent，协调执行。"""

import logging
from typing import Optional

from .config import AGENT_ROLES, TASK_TYPE_ROLE_MAP
from .response import StandardResponse

logger = logging.getLogger("traectl.project")


def _sr(result=None, message: str = "", code: int = 0) -> StandardResponse:
    """快捷构造 StandardResponse。"""
    return StandardResponse(result=result, message=message, code=code)


class ProjectManager:
    """项目总经理：分析任务，分配给合适的 Agent，协调执行。"""

    def __init__(self, solo):
        self._solo = solo

    def analyze_task(self, task: str) -> StandardResponse:
        """分析任务，推荐角色、模型和技能。返回 StandardResponse。"""
        task_lower = task.lower()
        best_role = "backend"
        best_score = 0
        for keyword, role in TASK_TYPE_ROLE_MAP.items():
            if keyword in task_lower:
                # 更长关键词得分更高，避免短关键词误匹配
                score = len(keyword)
                if score > best_score:
                    best_role = role
                    best_score = score

        role_config = AGENT_ROLES[best_role]

        # 根据任务类型推荐 agent skill
        agent_skill = self._recommend_agent_skill(task_lower, best_role)

        result = {
            "task": task,
            "role": best_role,
            "role_name": role_config["name"],
            "recommended_model": role_config["recommended_models"][0],
            "description": role_config["description"],
            "prompt_prefix": role_config["prompt_prefix"],
            "agent_skill": agent_skill,
        }
        return _sr(result=result, message=f"任务分析完成: {best_role} (score={best_score})")

    def _recommend_agent_skill(self, task_lower: str, role: str) -> dict:
        """根据任务内容和角色推荐配置。返回角色信息和推荐能力。"""
        role_config = AGENT_ROLES.get(role, AGENT_ROLES["backend"])
        effective_role = role if role in AGENT_ROLES else "backend"
        return {
            "name": effective_role,
            "description": role_config["description"],
            "capabilities": role_config.get("capabilities", [role_config["name"]]),
        }

    def plan_subtasks(self, task: str, max_steps: int = 5) -> StandardResponse:
        """将复杂任务分解为子任务序列。返回 StandardResponse。"""
        analysis_resp = self.analyze_task(task)
        analysis = analysis_resp.result

        # 简单启发式分解：按句子/分号/换行分割
        separators = ["；", ";", "。", ".", "\n"]
        chunks = [task]
        for sep in separators:
            parts = [p.strip() for p in task.split(sep) if p.strip()]
            if len(parts) > 1:
                chunks = parts
                break

        # 限制最大步数
        chunks = chunks[:max_steps]

        # 为每步分配角色（首步用推荐角色，其余轮换）
        primary_role = analysis["role"]

        subtasks = []
        for i, chunk in enumerate(chunks):
            if i == 0:
                role = primary_role
            else:
                role = self._infer_role_from_text(chunk, primary_role)

            role_config = AGENT_ROLES[role]
            subtasks.append({
                "step": i + 1,
                "role": role,
                "role_name": role_config["name"],
                "model": role_config["recommended_models"][0],
                "prompt": chunk,
                "description": role_config["description"],
            })

        return _sr(result=subtasks, message=f"子任务规划完成: {len(subtasks)} 步")

    @staticmethod
    def _infer_role_from_text(text: str, default_role: str) -> str:
        """根据文本内容推断合适的角色。"""
        text_lower = text.lower()
        role_hints = {
            "test": ["test", "测试", "unittest", "pytest"],
            "frontend": ["ui", "界面", "css", "style", "组件"],
            "architect": ["设计", "架构", "design", "architecture"],
            "reviewer": ["review", "审查", "检查"],
            "debugger": ["debug", "调试", "修复", "fix", "bug"],
        }
        for role, keywords in role_hints.items():
            if any(kw in text_lower for kw in keywords):
                return role
        return default_role

    async def execute_plan(
        self, subtasks: list[dict], timeout_per_task: Optional[int] = None
    ) -> StandardResponse:
        """按顺序执行子任务列表。返回 StandardResponse。"""
        from .config import SOLO_TIMEOUT

        results = []
        for i, subtask in enumerate(subtasks, 1):
            logger.info(
                f"执行子任务 {i}/{len(subtasks)}: [{subtask['role_name']}] {subtask['prompt'][:60]}..."
            )
            result = await self._solo.submit_task(
                prompt=subtask["prompt"],
                wait_for_response=True,
                timeout=timeout_per_task or SOLO_TIMEOUT,
            )
            # 兼容 StandardResponse 和 str 两种返回
            result_text = result.result if isinstance(result, StandardResponse) else result
            results.append({
                "step": i,
                "role": subtask["role_name"],
                "model": subtask.get("model", "auto"),
                "prompt_summary": subtask["prompt"][:80],
                "result": (result_text or "")[:2000],
            })

        data = {
            "total_steps": len(subtasks),
            "results": results,
        }
        return _sr(result=data, message=f"执行完成: {len(subtasks)} 步")
