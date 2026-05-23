#!/usr/bin/env python3
"""项目工作区自动配置管理：技能推荐、MCP Server 配置、项目类型检测。"""

import json
import logging
from pathlib import Path
from typing import Optional

try:
    import yaml
except ImportError:
    yaml = None

from .response import StandardResponse

logger = logging.getLogger("traectl.workspace")


def _sr(result=None, message: str = "", code: int = 0) -> StandardResponse:
    """快捷构造 StandardResponse。"""
    return StandardResponse(result=result, message=message, code=code)


class WorkspaceManager:
    """管理项目工作区配置。"""

    TRAE_CONFIG_PATH = Path.home() / ".config" / "Trae CN" / "User" / "traectl.yaml"
    TRAE_MCP_GLOBAL_PATH = Path.home() / ".config" / "Trae CN" / "User" / "mcp.json"
    SKILLS_DIR = Path.home() / ".hermes" / "skills"

    PROJECT_TYPE_SKILLS: dict[str, list[str]] = {
        "python": ["github/github-issues", "productivity/linear"],
        "nodejs": ["github/github-issues", "productivity/linear"],
        "react": ["github/github-issues", "creative/design-md"],
        "vue": ["github/github-issues", "creative/design-md"],
        "go": ["github/github-issues", "productivity/linear"],
        "rust": ["github/github-issues", "productivity/linear"],
        "mlops": ["mlops/inference/vllm", "mlops/training/axolotl", "mlops/research/dspy"],
        "data-science": ["data-science"],
        "devops": ["devops/gui-automation"],
        "mobile": ["github/github-issues", "creative/design-md"],
        "game": ["gaming/pokemon-player", "creative/manim-video"],
        "default": ["github/github-issues"],
    }

    # 每个指示文件的权重：更特异的文件权重更高
    INDICATOR_WEIGHTS: dict[str, int] = {
        "pyproject.toml": 3, "setup.py": 2, "requirements.txt": 1, "Pipfile": 2,
        "package.json": 2, "Cargo.toml": 3, "go.mod": 3,
        "vite.config.ts": 3, "vite.config.js": 2, "next.config.js": 2, "next.config.ts": 3,
        "src/App.tsx": 2, "src/App.jsx": 1,
        "vue.config.js": 2, "nuxt.config.ts": 3, "src/App.vue": 2,
        "train.py": 2, "model.py": 1, "config.yaml": 1, "notebooks": 1,
        "Dockerfile": 2, "docker-compose.yml": 2, ".github/workflows": 1, "kubernetes": 1,
        "ios": 1, "android": 1, "pubspec.yaml": 2,
        "Unity": 1, "Assets": 1, "Packages/manifest.json": 2,
    }

    PROJECT_DETECTION_RULES: list[tuple[list[str], str]] = [
        (["requirements.txt", "setup.py", "pyproject.toml", "Pipfile"], "python"),
        (["package.json"], "nodejs"),
        (["Cargo.toml"], "rust"),
        (["go.mod"], "go"),
        (["src/App.tsx", "src/App.jsx", "vite.config.ts", "vite.config.js",
          "next.config.js", "next.config.ts"], "react"),
        (["vue.config.js", "nuxt.config.ts", "src/App.vue"], "vue"),
        (["train.py", "model.py", "config.yaml", "notebooks"], "mlops"),
        (["Dockerfile", "docker-compose.yml", ".github/workflows", "kubernetes"], "devops"),
        (["ios", "android", "pubspec.yaml"], "mobile"),
        (["Unity", "Assets", "Packages/manifest.json"], "game"),
    ]

    def __init__(self, config_path: Optional[Path] = None, mcp_path: Optional[Path] = None):
        self._config_path = config_path or self.TRAE_CONFIG_PATH
        self._mcp_path = mcp_path
        self._config_cache: Optional[dict] = None

    def _load_config(self) -> dict:
        """读取配置。"""
        if self._config_cache is not None:
            return self._config_cache
        if not self._config_path.exists():
            return {}
        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) if yaml else {}
            if config is None:
                config = {}
            self._config_cache = config
            return config
        except Exception as e:
            logger.warning(f"读取配置失败: {e}")
            return {}

    def _save_config(self, config: dict) -> None:
        """保存配置。yaml 不可用时回退到 JSON。"""
        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            if yaml:
                with open(self._config_path, "w", encoding="utf-8") as f:
                    yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
            else:
                json_path = self._config_path.with_suffix(".json")
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(config, f, ensure_ascii=False, indent=2)
            self._config_cache = config
        except Exception as e:
            logger.warning(f"保存配置失败: {e}")
            raise

    def _save_yaml(self, path: Path, data: dict) -> None:
        """保存数据到 YAML 文件，yaml 不可用时回退到 JSON。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if yaml:
                with open(path, "w", encoding="utf-8") as f:
                    yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
            else:
                json_path = path.with_suffix(".json")
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"保存配置失败: {e}")
            raise

    def _list_installed_skills(self, workspace_path: Path) -> list[str]:
        """列出工作区 .trae/skills/ 下已安装的 skill。"""
        skills_dir = workspace_path / ".trae" / "skills"
        if not skills_dir.exists():
            return []
        return [d.name for d in skills_dir.iterdir() if d.is_dir()]

    def _find_skill_source(self, skill_name: str) -> Optional[Path]:
        """在 ~/.hermes/skills/ 中查找 skill 源目录。"""
        parts = skill_name.split("/")
        if len(parts) == 2:
            path = self.SKILLS_DIR / parts[0] / parts[1]
            if path.is_dir():
                return path
        if self.SKILLS_DIR.exists():
            for category_dir in self.SKILLS_DIR.iterdir():
                if not category_dir.is_dir():
                    continue
                target = category_dir / parts[-1]
                if target.is_dir():
                    return target
        return None

    def _invalidate_cache(self) -> None:
        self._config_cache = None

    def _list_available_skills(self) -> list[dict]:
        """扫描 ~/.hermes/skills 目录。"""
        skills = []
        if not self.SKILLS_DIR.exists():
            return skills
        for category_dir in self.SKILLS_DIR.iterdir():
            if not category_dir.is_dir():
                continue
            for skill_dir in category_dir.iterdir():
                if not skill_dir.is_dir():
                    continue
                skill_md = skill_dir / "SKILL.md"
                description = ""
                if skill_md.exists():
                    try:
                        content = skill_md.read_text(encoding="utf-8", errors="ignore")
                        for line in content.splitlines():
                            stripped = line.strip()
                            if stripped:
                                description = stripped.lstrip("# ").strip()
                                break
                    except Exception:
                        pass
                skills.append({
                    "name": f"{category_dir.name}/{skill_dir.name}",
                    "category": category_dir.name,
                    "skill_name": skill_dir.name,
                    "path": str(skill_dir),
                    "description": description,
                })
        return skills

    def _detect_project_type(self, workspace_path: str) -> str:
        """根据工作区文件自动检测项目类型，使用加权 best_score 评分。"""
        path = Path(workspace_path)
        if not path.exists():
            return "default"

        best_type = "default"
        best_score = 0
        scores: dict[str, int] = {}

        for indicators, ptype in self.PROJECT_DETECTION_RULES:
            for indicator in indicators:
                if (path / indicator).exists():
                    weight = self.INDICATOR_WEIGHTS.get(indicator, 1)
                    scores[ptype] = scores.get(ptype, 0) + weight

        if scores:
            best_type = max(scores, key=lambda k: scores[k])
            best_score = scores[best_type]

        logger.debug(f"项目类型检测: scores={scores}, best={best_type} (score={best_score})")
        return best_type

    def _get_recommended_skills(self, project_type: str) -> list[str]:
        return self.PROJECT_TYPE_SKILLS.get(project_type, self.PROJECT_TYPE_SKILLS["default"])

    def _trae_mcp_path(self, workspace_path: str) -> Path:
        if self._mcp_path:
            return self._mcp_path
        # 默认使用工作区级别的 .trae/mcp.json
        return Path(workspace_path) / ".trae" / "mcp.json"

    def _load_mcp_json(self, workspace_path: str) -> dict:
        path = self._trae_mcp_path(workspace_path)
        if not path.exists():
            return {"servers": {}}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"servers": {}}

    def _save_mcp_json(self, workspace_path: str, data: dict) -> None:
        path = self._trae_mcp_path(workspace_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")

    def _get_mcp_servers(self, workspace_path: str) -> dict[str, dict]:
        data = self._load_mcp_json(workspace_path)
        return data.get("servers", {}) or {}

    def _set_mcp_server(self, workspace_path: str, name: str, server_config: dict) -> None:
        data = self._load_mcp_json(workspace_path)
        servers = data.get("servers", {}) or {}
        servers[name] = server_config
        data["servers"] = servers
        self._save_mcp_json(workspace_path, data)

    def _delete_mcp_server(self, workspace_path: str, name: str) -> bool:
        data = self._load_mcp_json(workspace_path)
        servers = data.get("servers", {}) or {}
        if name in servers:
            del servers[name]
            data["servers"] = servers
            self._save_mcp_json(workspace_path, data)
            return True
        return False

    def setup_workspace(
        self,
        workspace_path: str,
        project_type: Optional[str] = None,
        skills: Optional[list[str]] = None,
        mcp_servers: Optional[dict[str, dict]] = None,
    ) -> StandardResponse:
        """初始化项目工作区配置。返回 StandardResponse。"""
        self._invalidate_cache()

        # 创建基础项目目录
        ws_path = Path(workspace_path)
        dirs_to_create = ["src", "tests", "docs", ".trae"]
        for d in dirs_to_create:
            (ws_path / d).mkdir(parents=True, exist_ok=True)

        detected_type = self._detect_project_type(workspace_path)
        actual_type = project_type or detected_type
        recommended = self._get_recommended_skills(actual_type)
        all_skills = recommended + (skills or [])
        # 去重
        unique_skills = list(dict.fromkeys(all_skills))

        # 写入 .trae/config.yaml
        trae_config_path = ws_path / ".trae" / "config.yaml"
        trae_config = {
            "project_type": actual_type,
            "recommended_skills": recommended,
            "configured_skills": unique_skills,
        }
        self._save_yaml(trae_config_path, trae_config)

        added_mcp = []
        if mcp_servers:
            for name, cfg in mcp_servers.items():
                self._set_mcp_server(workspace_path, name, cfg)
                added_mcp.append(name)

        configured_mcp = list(self._get_mcp_servers(workspace_path).keys())

        result = {
            "workspace_path": workspace_path,
            "detected_project_type": detected_type,
            "configured_project_type": actual_type,
            "recommended_skills": recommended,
            "added_skills": list(dict.fromkeys(skills or [])),
            "configured_skills": unique_skills,
            "added_mcp_servers": added_mcp,
            "configured_mcp_servers": configured_mcp,
            "config_path": str(trae_config_path),
        }
        return _sr(result=result, message=f"工作区配置完成: {actual_type}")

    def manage_skills(
        self,
        action: str,
        skill_name: Optional[str] = None,
        search_query: Optional[str] = None,
        workspace_path: Optional[str] = None,
    ) -> StandardResponse:
        """管理 Skills：列出/安装/删除/搜索推荐。返回 StandardResponse。"""
        ws_path = Path(workspace_path) if workspace_path else Path.cwd()

        if action == "list":
            installed = self._list_installed_skills(ws_path)
            available = self._list_available_skills()
            result = {
                "action": "list",
                "installed_skills": installed,
                "available_skills": [
                    {"name": s["name"], "category": s["category"], "description": s["description"]}
                    for s in available
                ],
                "total_available": len(available),
            }
            return _sr(result=result, message=f"技能列表: {len(available)} 个可用, {len(installed)} 个已安装")

        elif action == "add":
            if not skill_name:
                return _sr(result=None, message="添加 skill 需要提供 skill_name", code=-1)
            src = self._find_skill_source(skill_name)
            if not src:
                return _sr(result=None, message=f"Skill '{skill_name}' 未找到", code=-1)
            dest = ws_path / ".trae" / "skills" / skill_name.split("/")[-1]
            if dest.exists():
                return _sr(result={"action": "add", "skill": skill_name, "status": "already_exists"}, message=f"Skill '{skill_name}' 已安装")
            import shutil
            shutil.copytree(src, dest)
            return _sr(result={"action": "add", "skill": skill_name, "status": "added", "path": str(dest)}, message=f"Skill '{skill_name}' 已安装")

        elif action == "remove":
            if not skill_name:
                return _sr(result=None, message="删除 skill 需要提供 skill_name", code=-1)
            skill_dir = ws_path / ".trae" / "skills" / skill_name.split("/")[-1]
            if not skill_dir.exists():
                return _sr(result=None, message=f"Skill '{skill_name}' 未安装", code=-1)
            import shutil
            shutil.rmtree(skill_dir)
            return _sr(result={"action": "remove", "skill": skill_name, "status": "removed"}, message=f"Skill '{skill_name}' 已删除")

        elif action == "search":
            query = (search_query or "").lower()
            available = self._list_available_skills()
            matched = [
                {"name": s["name"], "category": s["category"], "description": s["description"]}
                for s in available
                if query in s["name"].lower() or query in s["category"].lower() or query in s["description"].lower()
            ]
            return _sr(result={"action": "search", "query": search_query, "results": matched, "total": len(matched)}, message=f"搜索完成: {len(matched)} 个匹配")

        elif action == "recommend":
            cwd = str(ws_path)
            ptype = self._detect_project_type(cwd)
            return _sr(result={"action": "recommend", "project_type": ptype, "workspace_path": cwd, "recommended_skills": self._get_recommended_skills(ptype)}, message=f"推荐技能: {ptype}")

        return _sr(result=None, message=f"未知的 action: {action}。支持: list, add, remove, search, recommend", code=-1)

    def manage_mcp(
        self,
        workspace_path: str,
        action: str,
        server_name: Optional[str] = None,
        server_config: Optional[dict] = None,
    ) -> StandardResponse:
        """管理 MCP Server 配置。返回 StandardResponse。"""
        if action == "list":
            servers = self._get_mcp_servers(workspace_path)
            result = {
                "action": "list",
                "workspace_path": workspace_path,
                "mcp_servers": [
                    {"name": name, "command": cfg.get("command", ""), "args": cfg.get("args", [])}
                    for name, cfg in servers.items()
                ],
                "total": len(servers),
            }
            return _sr(result=result, message=f"MCP 列表: {len(servers)} 个服务器")

        elif action == "add":
            if not server_name or not server_config:
                return _sr(result=None, message="添加 MCP server 需要提供 server_name 和 server_config", code=-1)
            existing = self._get_mcp_servers(workspace_path)
            self._set_mcp_server(workspace_path, server_name, server_config)
            status = "updated" if server_name in existing else "added"
            return _sr(
                result={"action": "add", "server_name": server_name, "workspace_path": workspace_path, "status": status, "config": server_config},
                message=f"MCP server '{server_name}' 已{'更新' if status == 'updated' else '添加'}",
            )

        elif action == "update":
            if not server_name or not server_config:
                return _sr(result=None, message="更新 MCP server 需要提供 server_name 和 server_config", code=-1)
            existing = self._get_mcp_servers(workspace_path)
            if server_name not in existing:
                return _sr(result=None, message=f"MCP server '{server_name}' 不存在，请先添加", code=-1)
            merged = {**existing[server_name], **server_config}
            self._set_mcp_server(workspace_path, server_name, merged)
            return _sr(
                result={"action": "update", "server_name": server_name, "workspace_path": workspace_path, "status": "updated", "config": merged},
                message=f"MCP server '{server_name}' 已更新",
            )

        elif action == "remove":
            if not server_name:
                return _sr(result=None, message="删除 MCP server 需要提供 server_name", code=-1)
            removed = self._delete_mcp_server(workspace_path, server_name)
            status = "removed" if removed else "not_found"
            return _sr(
                result={"action": "remove", "server_name": server_name, "workspace_path": workspace_path, "status": status},
                message=f"MCP server '{server_name}': {status}",
            )

        return _sr(result=None, message=f"未知的 action: {action}。支持: list, add, update, remove", code=-1)
