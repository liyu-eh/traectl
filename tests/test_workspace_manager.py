"""workspace_manager.py 测试：best_score 评分、StandardResponse 返回、角色技能映射。"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from traectl.workspace_manager import WorkspaceManager, _sr as wm_sr
from traectl.project_manager import ProjectManager, _sr as pm_sr

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

    @pytest.mark.parametrize("task,expected_role", [
        ("开发后端 API 接口", "backend"),
        ("实现前端组件",       "frontend"),
        ("写测试用例 test",    "tester"),
        ("代码审查 review",    "reviewer"),
        ("修复 bug",          "debugger"),
        ("系统架构设计",       "architect"),
        ("重构代码",          "reviewer"),
        ("随便做点什么",      "backend"),
    ])
    def test_keyword_to_role(self, task, expected_role):
        resp = self.pm.analyze_task(task)
        assert resp.result["role"] == expected_role

    def test_best_score_prefers_longer_keyword(self):
        """更长关键词应获得更高分数。"""
        resp = self.pm.analyze_task("写 integration test")
        assert resp.result["role"] == "tester"
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

    @pytest.mark.parametrize("role_key,expected_name", [
        ("backend",   "backend"),
        ("frontend",  "frontend"),
        ("tester",    "tester"),
        ("reviewer",  "reviewer"),
        ("debugger",  "debugger"),
        ("architect", "architect"),
        ("unknown-role", "backend"),
    ])
    def test_returns_skill_for_role(self, role_key, expected_name):
        skill = self.pm._recommend_agent_skill("generic task", role_key)
        assert skill["name"] == expected_name
        assert isinstance(skill, dict)
        assert "name" in skill
        assert "description" in skill
        assert "capabilities" in skill

    def test_all_agent_roles_have_fallback(self):
        for role_key in AGENT_ROLES:
            skill = self.pm._recommend_agent_skill("generic task", role_key)
            assert isinstance(skill, dict), f"Role {role_key} has no skill fallback"
            assert "name" in skill


# ── ProjectManager.plan_subtasks ───────────────────────────────

class TestPlanSubtasks:
    def setup_method(self):
        self.mock_solo = MagicMock()
        self.pm = ProjectManager(self.mock_solo)

    def test_returns_standard_response_with_subtask(self):
        resp = self.pm.plan_subtasks("写一个 API")
        assert isinstance(resp, StandardResponse)
        assert resp.code == 0
        assert isinstance(resp.result, list)
        assert len(resp.result) == 1

    def test_subtask_has_required_keys(self):
        resp = self.pm.plan_subtasks("写一个 API")
        subtask = resp.result[0]
        for key in ["step", "role", "role_name", "model", "prompt", "description"]:
            assert key in subtask
        assert subtask["prompt"] == "写一个 API"


# ── WorkspaceManager._detect_project_type (best_score) ─────────

class TestDetectProjectType:
    def setup_method(self):
        self.wm = WorkspaceManager()

    def test_nonexistent_path_returns_default(self):
        assert self.wm._detect_project_type("/nonexistent/path") == "default"

    @pytest.mark.parametrize("file_spec,expected_type", [
        ([("pyproject.toml", None)],          "python"),
        ([("package.json", None)],            "nodejs"),
        ([("Cargo.toml", None)],              "rust"),
        ([("go.mod", None)],                  "go"),
        ([("vite.config.ts", None)],           "react"),
        ([("src", "App.vue")],                "vue"),
        # 空目录
        ([],                                  "default"),
    ])
    def test_single_indicator_detection(self, file_spec, expected_type):
        with tempfile.TemporaryDirectory() as tmp:
            for fname, subpath in file_spec:
                if subpath:
                    Path(tmp, fname, subpath).parent.mkdir(parents=True, exist_ok=True)
                    Path(tmp, fname, subpath).touch()
                else:
                    Path(tmp, fname).touch()
            assert self.wm._detect_project_type(tmp) == expected_type

    def test_weighted_scoring_higher_weight_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "requirements.txt").touch()
            assert self.wm._detect_project_type(tmp) == "python"
            Path(tmp, "go.mod").touch()
            assert self.wm._detect_project_type(tmp) == "go"

    def test_multiple_indicators_accumulate(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "pyproject.toml").touch()
            Path(tmp, "setup.py").touch()
            Path(tmp, "package.json").touch()
            assert self.wm._detect_project_type(tmp) == "python"

    def test_indicator_weights_defined_for_all_indicators(self):
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
        with tempfile.TemporaryDirectory() as tmp:
            fake_skills_dir = Path(tmp) / "fake_hermes" / "skills"
            fake_skills_dir.mkdir(parents=True)
            src_skill = fake_skills_dir / "github" / "github-issues"
            src_skill.mkdir(parents=True)
            (src_skill / "SKILL.md").write_text("# GitHub Issues Skill")
            self.wm.SKILLS_DIR = fake_skills_dir

            ws_dir = Path(tmp) / "workspace"
            ws_dir.mkdir()
            resp = self.wm.manage_skills("add", skill_name="github/github-issues", workspace_path=str(ws_dir))
            assert resp.code == 0
            assert resp.result["status"] == "added"
            assert (ws_dir / ".trae" / "skills" / "github-issues").exists()

    def test_add_existing_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
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
        assert config1 == {}
        config2 = self.wm._load_config()
        assert config2 == {}


# ── WorkspaceManager.PROJECT_TYPE_SKILLS 结构验证 ──────────────

class TestProjectTypeSkillsStructure:
    def test_all_detection_rules_have_skills(self):
        for _, ptype in WorkspaceManager.PROJECT_DETECTION_RULES:
            assert ptype in WorkspaceManager.PROJECT_TYPE_SKILLS, (
                f"Project type '{ptype}' detected but has no skills mapping"
            )

    def test_default_skills_exist(self):
        assert "default" in WorkspaceManager.PROJECT_TYPE_SKILLS


# ── workspace init CLI 集成测试 ────────────────────────────────

class TestWorkspaceInitCLI:
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
        config_path = tmp_path / ".trae" / "config.yaml"
        assert config_path.exists()

    def test_init_with_skills(self, tmp_path):
        from typer.testing import CliRunner
        from traectl.cli import app
        runner = CliRunner()
        result = runner.invoke(app, ["workspace", "init", "--path", str(tmp_path), "--skills", "github/github-issues"])
        assert result.exit_code == 0
