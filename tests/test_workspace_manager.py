"""workspace_manager.py 测试：best_score 评分、StandardResponse 返回、角色技能映射。"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from traectl.workspace_manager import WorkspaceManager, _sr as wm_sr
from traectl.project_manager import ProjectManager, _sr as pm_sr

# _sr 在两个模块中实现相同，测试中统一使用一个
_sr = wm_sr
from traectl.response import StandardResponse
from traectl.config import AGENT_ROLES, TASK_TYPE_ROLE_MAP


# ── _sr 辅助函数 ──────────────────────────────────────────────

class TestSrHelper:
    def test_sr_returns_standard_response(self):
        resp = _sr(result="data", message="ok", code=0)
        assert isinstance(resp, StandardResponse)
        assert resp.result == "data"
        assert resp.message == "ok"
        assert resp.code == 0

    def test_sr_defaults(self):
        resp = _sr()
        assert resp.result is None
        assert resp.message == ""
        assert resp.code == 0

    def test_sr_error(self):
        resp = _sr(result=None, message="失败", code=-1)
        assert resp.code == -1
        assert resp.result is None


# ── ProjectManager.analyze_task ────────────────────────────────

class TestAnalyzeTask:
    def setup_method(self):
        self.mock_solo = MagicMock()
        self.pm = ProjectManager(self.mock_solo)

    def test_returns_standard_response(self):
        resp = self.pm.analyze_task("写一个 API 接口")
        assert isinstance(resp, StandardResponse)
        assert resp.code == 0

    def test_backend_keyword(self):
        resp = self.pm.analyze_task("开发后端 API 接口")
        assert resp.result["role"] == "backend"

    def test_frontend_keyword(self):
        resp = self.pm.analyze_task("实现前端组件")
        assert resp.result["role"] == "frontend"

    def test_tester_keyword(self):
        resp = self.pm.analyze_task("写测试用例 test")
        assert resp.result["role"] == "tester"

    def test_reviewer_keyword(self):
        resp = self.pm.analyze_task("代码审查 review")
        assert resp.result["role"] == "reviewer"

    def test_debugger_keyword(self):
        resp = self.pm.analyze_task("修复 bug")
        assert resp.result["role"] == "debugger"

    def test_architect_keyword(self):
        resp = self.pm.analyze_task("系统架构设计")
        assert resp.result["role"] == "architect"

    def test_default_role_is_backend(self):
        resp = self.pm.analyze_task("随便做点什么")
        assert resp.result["role"] == "backend"

    def test_best_score_prefers_longer_keyword(self):
        """更长关键词应获得更高分数。"""
        # "integration test" (len=16) > "test" (len=4)
        resp = self.pm.analyze_task("写 integration test")
        assert resp.result["role"] == "tester"
        # message 包含 score
        assert "score=" in resp.message

    def test_result_contains_all_keys(self):
        resp = self.pm.analyze_task("写 API")
        result = resp.result
        for key in ["task", "role", "role_name", "recommended_model", "description", "prompt_prefix", "agent_skill"]:
            assert key in result

    def test_result_role_matches_agent_roles(self):
        resp = self.pm.analyze_task("调试 debug")
        role = resp.result["role"]
        assert role in AGENT_ROLES
        assert resp.result["role_name"] == AGENT_ROLES[role]["name"]
        assert resp.result["recommended_model"] == AGENT_ROLES[role]["recommended_models"][0]

    def test_chinese_keywords(self):
        resp = self.pm.analyze_task("重构代码")
        assert resp.result["role"] == "reviewer"

    def test_agent_skill_is_dict(self):
        resp = self.pm.analyze_task("写测试")
        skill = resp.result["agent_skill"]
        assert isinstance(skill, dict)
        assert "name" in skill
        assert "description" in skill
        assert "capabilities" in skill


# ── ProjectManager._recommend_agent_skill ──────────────────────

class TestRecommendAgentSkill:
    def setup_method(self):
        self.mock_solo = MagicMock()
        self.pm = ProjectManager(self.mock_solo)

    def test_returns_role_as_name(self):
        skill = self.pm._recommend_agent_skill("write unit test", "backend")
        assert skill["name"] == "backend"

    def test_returns_role_description(self):
        skill = self.pm._recommend_agent_skill("code review", "reviewer")
        assert skill["description"] == AGENT_ROLES["reviewer"]["description"]

    def test_returns_capabilities(self):
        skill = self.pm._recommend_agent_skill("generic task", "frontend")
        assert "capabilities" in skill
        assert isinstance(skill["capabilities"], list)

    def test_role_based_fallback_architect(self):
        skill = self.pm._recommend_agent_skill("generic task", "architect")
        assert skill["name"] == "architect"

    def test_role_based_fallback_frontend(self):
        skill = self.pm._recommend_agent_skill("generic task", "frontend")
        assert skill["name"] == "frontend"

    def test_role_based_fallback_tester(self):
        skill = self.pm._recommend_agent_skill("generic task", "tester")
        assert skill["name"] == "tester"

    def test_role_based_fallback_reviewer(self):
        skill = self.pm._recommend_agent_skill("generic task", "reviewer")
        assert skill["name"] == "reviewer"

    def test_role_based_fallback_debugger(self):
        skill = self.pm._recommend_agent_skill("generic task", "debugger")
        assert skill["name"] == "debugger"

    def test_role_based_fallback_unknown_defaults_to_backend(self):
        skill = self.pm._recommend_agent_skill("generic task", "unknown-role")
        assert skill["name"] == "backend"

    def test_all_agent_roles_have_fallback(self):
        """AGENT_ROLES 中每个角色都应有对应的技能回退。"""
        for role_key in AGENT_ROLES:
            skill = self.pm._recommend_agent_skill("generic task", role_key)
            assert isinstance(skill, dict), f"Role {role_key} has no skill fallback"
            assert "name" in skill


# ── ProjectManager.plan_subtasks ───────────────────────────────

class TestPlanSubtasks:
    def setup_method(self):
        self.mock_solo = MagicMock()
        self.pm = ProjectManager(self.mock_solo)

    def test_returns_standard_response(self):
        resp = self.pm.plan_subtasks("写一个 API")
        assert isinstance(resp, StandardResponse)
        assert resp.code == 0

    def test_result_is_list(self):
        resp = self.pm.plan_subtasks("写一个 API")
        assert isinstance(resp.result, list)
        assert len(resp.result) == 1

    def test_subtask_has_required_keys(self):
        resp = self.pm.plan_subtasks("写一个 API")
        subtask = resp.result[0]
        for key in ["step", "role", "role_name", "model", "prompt", "description"]:
            assert key in subtask

    def test_subtask_prompt_matches_input(self):
        resp = self.pm.plan_subtasks("写一个 API")
        assert resp.result[0]["prompt"] == "写一个 API"


# ── WorkspaceManager._detect_project_type (best_score) ─────────

class TestDetectProjectType:
    def setup_method(self):
        self.wm = WorkspaceManager()

    def test_nonexistent_path_returns_default(self):
        assert self.wm._detect_project_type("/nonexistent/path") == "default"

    def test_python_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "pyproject.toml").touch()
            assert self.wm._detect_project_type(tmp) == "python"

    def test_nodejs_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "package.json").touch()
            assert self.wm._detect_project_type(tmp) == "nodejs"

    def test_rust_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "Cargo.toml").touch()
            assert self.wm._detect_project_type(tmp) == "rust"

    def test_go_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "go.mod").touch()
            assert self.wm._detect_project_type(tmp) == "go"

    def test_react_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "vite.config.ts").touch()
            assert self.wm._detect_project_type(tmp) == "react"

    def test_vue_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "src").mkdir()
            Path(tmp, "src", "App.vue").touch()
            assert self.wm._detect_project_type(tmp) == "vue"

    def test_empty_dir_returns_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            assert self.wm._detect_project_type(tmp) == "default"

    def test_weighted_scoring_higher_weight_wins(self):
        """pyproject.toml (weight=3) 应比 requirements.txt (weight=1) 更有影响力。"""
        with tempfile.TemporaryDirectory() as tmp:
            # 只有 requirements.txt -> python (weight=1)
            Path(tmp, "requirements.txt").touch()
            result1 = self.wm._detect_project_type(tmp)

            # 加上 go.mod (weight=3) -> go 应胜出
            Path(tmp, "go.mod").touch()
            result2 = self.wm._detect_project_type(tmp)

            assert result1 == "python"
            assert result2 == "go"

    def test_multiple_indicators_accumulate(self):
        """多个指示文件应累加权重。"""
        with tempfile.TemporaryDirectory() as tmp:
            # python: pyproject.toml(3) + setup.py(2) = 5
            Path(tmp, "pyproject.toml").touch()
            Path(tmp, "setup.py").touch()
            # nodejs: package.json(2)
            Path(tmp, "package.json").touch()
            # python 应胜出 (5 > 2)
            assert self.wm._detect_project_type(tmp) == "python"

    def test_indicator_weights_defined_for_all_indicators(self):
        """PROJECT_DETECTION_RULES 中的每个指示文件都应有对应权重。"""
        for indicators, _ in WorkspaceManager.PROJECT_DETECTION_RULES:
            for indicator in indicators:
                assert indicator in WorkspaceManager.INDICATOR_WEIGHTS, (
                    f"Indicator '{indicator}' missing from INDICATOR_WEIGHTS"
                )


# ── WorkspaceManager.setup_workspace ───────────────────────────

class TestSetupWorkspace:
    def setup_method(self):
        self.wm = WorkspaceManager()

    def test_returns_standard_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            resp = self.wm.setup_workspace(tmp)
            assert isinstance(resp, StandardResponse)
            assert resp.code == 0

    def test_detects_project_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "pyproject.toml").touch()
            resp = self.wm.setup_workspace(tmp)
            assert resp.result["detected_project_type"] == "python"

    def test_override_project_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            resp = self.wm.setup_workspace(tmp, project_type="rust")
            assert resp.result["detected_project_type"] == "default"
            assert resp.result["configured_project_type"] == "rust"

    def test_adds_recommended_skills(self):
        with tempfile.TemporaryDirectory() as tmp:
            resp = self.wm.setup_workspace(tmp, project_type="python")
            configured = resp.result["configured_skills"]
            assert "github/github-issues" in configured
            assert "productivity/linear" in configured

    def test_does_not_duplicate_skills(self):
        with tempfile.TemporaryDirectory() as tmp:
            resp = self.wm.setup_workspace(tmp, project_type="python", skills=["github/github-issues"])
            configured = resp.result["configured_skills"]
            assert configured.count("github/github-issues") == 1

    def test_adds_extra_skills(self):
        with tempfile.TemporaryDirectory() as tmp:
            resp = self.wm.setup_workspace(tmp, skills=["custom/skill"])
            assert "custom/skill" in resp.result["added_skills"]
            assert "custom/skill" in resp.result["configured_skills"]

    def test_message_contains_project_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            resp = self.wm.setup_workspace(tmp, project_type="rust")
            assert "rust" in resp.message

    def test_creates_trae_config_yaml(self):
        with tempfile.TemporaryDirectory() as tmp:
            resp = self.wm.setup_workspace(tmp, project_type="python")
            config_path = Path(resp.result["config_path"])
            assert config_path.exists()
            assert config_path.name == "config.yaml"
            assert config_path.parent.name == ".trae"

    def test_trae_config_yaml_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.wm.setup_workspace(tmp, project_type="python", skills=["custom/skill"])
            config_path = Path(tmp) / ".trae" / "config.yaml"
            import yaml as _yaml
            if _yaml:
                with open(config_path) as f:
                    data = _yaml.safe_load(f)
                assert data["project_type"] == "python"
                assert "github/github-issues" in data["recommended_skills"]
                assert "custom/skill" in data["configured_skills"]


# ── WorkspaceManager.manage_skills ─────────────────────────────

class TestManageSkills:
    def setup_method(self):
        self.wm = WorkspaceManager()

    def test_list_returns_standard_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            resp = self.wm.manage_skills("list", workspace_path=tmp)
            assert isinstance(resp, StandardResponse)
            assert resp.code == 0
            assert resp.result["action"] == "list"
            assert "installed_skills" in resp.result

    def test_add_skill_not_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            resp = self.wm.manage_skills("add", skill_name="nonexistent/skill", workspace_path=tmp)
            assert resp.code == -1

    def test_add_without_name_returns_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            resp = self.wm.manage_skills("add", workspace_path=tmp)
            assert resp.code == -1
            assert resp.result is None

    def test_add_skill_from_source(self):
        """模拟 ~/.hermes/skills/ 下有 skill 源目录，测试 add 操作。"""
        with tempfile.TemporaryDirectory() as tmp:
            # 创建模拟的 skill 源目录
            fake_skills_dir = Path(tmp) / "fake_hermes" / "skills"
            fake_skills_dir.mkdir(parents=True)
            src_skill = fake_skills_dir / "github" / "github-issues"
            src_skill.mkdir(parents=True)
            (src_skill / "SKILL.md").write_text("# GitHub Issues Skill")

            # 替换 SKILLS_DIR
            self.wm.SKILLS_DIR = fake_skills_dir

            ws_dir = Path(tmp) / "workspace"
            ws_dir.mkdir()
            resp = self.wm.manage_skills("add", skill_name="github/github-issues", workspace_path=str(ws_dir))
            assert resp.code == 0
            assert resp.result["status"] == "added"
            assert (ws_dir / ".trae" / "skills" / "github-issues").exists()

    def test_add_existing_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            # 创建已存在的 skill 目录
            ws_dir = Path(tmp) / "workspace"
            ws_dir.mkdir()
            existing = ws_dir / ".trae" / "skills" / "github-issues"
            existing.mkdir(parents=True)

            resp = self.wm.manage_skills("add", skill_name="github/github-issues", workspace_path=str(ws_dir))
            assert resp.result["status"] == "already_exists"

    def test_remove_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws_dir = Path(tmp) / "workspace"
            ws_dir.mkdir()
            skill_dir = ws_dir / ".trae" / "skills" / "my-skill"
            skill_dir.mkdir(parents=True)

            resp = self.wm.manage_skills("remove", skill_name="my-skill", workspace_path=str(ws_dir))
            assert resp.code == 0
            assert resp.result["status"] == "removed"
            assert not skill_dir.exists()

    def test_remove_not_installed(self):
        with tempfile.TemporaryDirectory() as tmp:
            resp = self.wm.manage_skills("remove", skill_name="no-skill", workspace_path=tmp)
            assert resp.code == -1

    def test_remove_without_name_returns_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            resp = self.wm.manage_skills("remove", workspace_path=tmp)
            assert resp.code == -1

    @patch.object(WorkspaceManager, "_list_available_skills", return_value=[])
    def test_search_returns_standard_response(self, mock_list):
        with tempfile.TemporaryDirectory() as tmp:
            resp = self.wm.manage_skills("search", search_query="github", workspace_path=tmp)
            assert isinstance(resp, StandardResponse)
            assert resp.code == 0
            assert resp.result["action"] == "search"

    def test_recommend_returns_standard_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            resp = self.wm.manage_skills("recommend", workspace_path=tmp)
            assert isinstance(resp, StandardResponse)
            assert resp.code == 0
            assert resp.result["action"] == "recommend"
            assert "project_type" in resp.result

    def test_unknown_action_returns_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            resp = self.wm.manage_skills("invalid", workspace_path=tmp)
            assert resp.code == -1
            assert "未知" in resp.message


# ── WorkspaceManager._get_recommended_skills ───────────────────

class TestGetRecommendedSkills:
    def setup_method(self):
        self.wm = WorkspaceManager()

    def test_python_skills(self):
        skills = self.wm._get_recommended_skills("python")
        assert "github/github-issues" in skills

    def test_unknown_type_returns_default(self):
        skills = self.wm._get_recommended_skills("unknown-type")
        assert skills == WorkspaceManager.PROJECT_TYPE_SKILLS["default"]

    def test_all_project_types_have_skills(self):
        for ptype in WorkspaceManager.PROJECT_TYPE_SKILLS:
            skills = self.wm._get_recommended_skills(ptype)
            assert isinstance(skills, list)
            assert len(skills) > 0


# ── WorkspaceManager config caching ────────────────────────────

class TestConfigCaching:
    def setup_method(self):
        self.wm = WorkspaceManager()

    def test_invalidate_cache(self):
        self.wm._config_cache = {"test": True}
        self.wm._invalidate_cache()
        assert self.wm._config_cache is None

    def test_load_config_caches(self):
        self.wm._config_path = Path("/nonexistent")
        self.wm._invalidate_cache()
        config1 = self.wm._load_config()
        # 文件不存在时返回空 dict，但不缓存
        assert config1 == {}
        # 缓存为 None，第二次调用仍走同一逻辑
        config2 = self.wm._load_config()
        assert config2 == {}


# ── WorkspaceManager.PROJECT_TYPE_SKILLS 结构验证 ──────────────

class TestProjectTypeSkillsStructure:
    def test_all_detection_rules_have_skills(self):
        """每种可检测的项目类型都应有推荐技能。"""
        for _, ptype in WorkspaceManager.PROJECT_DETECTION_RULES:
            assert ptype in WorkspaceManager.PROJECT_TYPE_SKILLS, (
                f"Project type '{ptype}' detected but has no skills mapping"
            )

    def test_default_skills_exist(self):
        assert "default" in WorkspaceManager.PROJECT_TYPE_SKILLS


# ── workspace init CLI 集成测试 ────────────────────────────────

class TestWorkspaceInitCLI:
    """测试 workspace init 命令行入口。"""

    def test_init_creates_dirs(self, tmp_path):
        from typer.testing import CliRunner
        from traectl.cli import app
        runner = CliRunner()
        result = runner.invoke(app, ["workspace", "init", "--path", str(tmp_path)])
        assert result.exit_code == 0
        assert (tmp_path / "src").is_dir()
        assert (tmp_path / "tests").is_dir()
        assert (tmp_path / "docs").is_dir()
        assert (tmp_path / ".trae").is_dir()

    def test_init_with_type(self, tmp_path):
        from typer.testing import CliRunner
        from traectl.cli import app
        runner = CliRunner()
        result = runner.invoke(app, ["workspace", "init", "--path", str(tmp_path), "--type", "python"])
        assert result.exit_code == 0
        # Check .trae/config.yaml exists
        config_path = tmp_path / ".trae" / "config.yaml"
        assert config_path.exists()

    def test_init_with_skills(self, tmp_path):
        from typer.testing import CliRunner
        from traectl.cli import app
        runner = CliRunner()
        result = runner.invoke(app, ["workspace", "init", "--path", str(tmp_path), "--skills", "github/github-issues"])
        assert result.exit_code == 0
