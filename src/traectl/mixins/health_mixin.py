#!/usr/bin/env python3
"""HealthMixin — 健康检查：返回结构化的健康信息，CLI 层无需访问 _cdp 内部。"""

import os

from ..cdp_client import ConnectionState
from ..response import StandardResponse



class HealthMixin:
    """健康检查 Mixin：封装 CDP 连接状态与 SOLO 面板就绪检测。"""

    async def get_health_info(self) -> StandardResponse:
        """返回结构化的健康检查信息。"""
        cdp = self._cdp
        health_info: dict = {"status_code": 0, "status": "healthy"}
        issues: list[str] = []
        warnings: list[str] = []

        display_env = os.environ.get("DISPLAY", "")
        if not display_env:
            warnings.append("DISPLAY 环境变量未设置")
            health_info["status_code"] = 1
            health_info["status"] = "warning"

        cdp_alive = await cdp.is_alive()
        cdp_connected = cdp.state == ConnectionState.CONNECTED

        if not cdp_connected:
            health_info["status_code"] = 2
            health_info["status"] = "error"
            issues.append("CDP WebSocket 未连接")
        elif not cdp_alive:
            health_info["status_code"] = max(health_info["status_code"], 1)
            health_info["status"] = "error" if health_info["status_code"] >= 2 else "warning"
            warnings.append("CDP WebSocket ping 无响应")

        solo_ready = False
        current_model = "unknown"
        if cdp_connected and cdp_alive:
            try:
                resp = await self.get_solo_status()
                status_data = resp.result
                current_model = status_data.get("currentModel", "unknown") or "unknown"
                solo_ready = bool(
                    current_model
                    and current_model != "unknown"
                    and status_data.get("inputText") is not None
                )
            except Exception as e:
                issues.append(f"SOLO 面板状态查询失败: {e}")
                health_info["status_code"] = 2
                health_info["status"] = "error"

        health_info["cdp"] = {
            "connected": cdp_connected,
            "alive": cdp_alive,
            "host": cdp.host,
            "port": cdp.port,
        }
        health_info["solo"] = {"ready": solo_ready, "current_model": current_model}
        health_info["summary"] = (
            "; ".join(issues) if issues
            else "; ".join(warnings) if warnings
            else "all checks passed"
        )

        return StandardResponse(
            result=health_info, message=health_info["summary"], code=0
        )
