import json

from traectl.response import StandardResponse, ok, error, dry_run_plan, EXIT_USAGE_ERROR, EXIT_GENERAL_ERROR, EXIT_RETRYABLE


def test_standard_response_success():
    resp = StandardResponse(result="done", message="操作成功", code=0)
    assert resp.code == 0
    assert resp.result == "done"
    assert resp.message == "操作成功"
    assert resp.exit_code == 0
    assert str(resp) == "操作成功"
    assert "StandardResponse" in repr(resp)


def test_standard_response_error():
    resp = StandardResponse(result=None, message="连接失败", code=-1, exit_code=1)
    assert resp.code == -1
    assert resp.result is None
    assert resp.message == "连接失败"
    assert resp.exit_code == 1
    assert str(resp) == "连接失败"


def test_standard_response_with_data():
    data = {"model": "DeepSeek-V4-Pro", "available": 5}
    resp = StandardResponse(result=data, message="模型列表", code=0)
    assert resp.code == 0
    assert resp.result == data
    assert resp.result["model"] == "DeepSeek-V4-Pro"


def test_standard_response_to_dict():
    resp = StandardResponse(result={"key": "value"}, message="测试", code=0)
    d = resp.to_dict()
    assert d == {"result": {"key": "value"}, "message": "测试", "code": 0, "exit_code": 0}


def test_standard_response_to_dict_with_exit_code():
    resp = StandardResponse(result=None, message="失败", code=-1, exit_code=2)
    d = resp.to_dict()
    assert d["exit_code"] == 2


def test_standard_response_to_json():
    resp = StandardResponse(result="hello", message="成功", code=0)
    json_str = resp.to_json()
    parsed = json.loads(json_str)
    assert parsed["result"] == "hello"
    assert parsed["message"] == "成功"
    assert parsed["code"] == 0
    assert parsed["exit_code"] == 0


def test_json_response_ok():
    result = ok({"status": "healthy"}, type_="health.check")
    parsed = json.loads(result)
    assert parsed["ok"] is True
    assert parsed["data"] == {"status": "healthy"}
    assert parsed["type"] == "health.check"
    assert "timestamp" in parsed["metadata"]
    # 成功响应不输出 exit_code 字段（因为为 0）
    assert "exit_code" not in parsed


def test_json_response_ok_with_nonzero_exit_code():
    result = ok({"status": "ok"}, type_="test", exit_code=EXIT_GENERAL_ERROR)
    parsed = json.loads(result)
    assert parsed["ok"] is True
    assert parsed["exit_code"] == 1


def test_json_response_error():
    result = error("timeout", "连接超时", retryable=True, type_="cdp.error")
    parsed = json.loads(result)
    assert parsed["ok"] is False
    assert parsed["error"]["code"] == "timeout"
    assert parsed["error"]["message"] == "连接超时"
    assert parsed["error"]["retryable"] is True
    assert parsed["type"] == "cdp.error"
    assert parsed["exit_code"] == EXIT_RETRYABLE


def test_json_response_error_with_explicit_exit_code():
    result = error("missing_argument", "缺少参数", exit_code=EXIT_USAGE_ERROR)
    parsed = json.loads(result)
    assert parsed["exit_code"] == 2


def test_json_response_dry_run():
    plan = {"action": "switch_model", "model": "DeepSeek-V4-Pro"}
    result = dry_run_plan(plan, "confirm-123", type_="model.switch.dry-run")
    parsed = json.loads(result)
    assert parsed["ok"] is True
    assert parsed["dryRun"] is True
    assert parsed["plan"] == plan
    assert parsed["metadata"]["confirmationId"] == "confirm-123"
    assert parsed["type"] == "model.switch.dry-run"


def test_standard_response_defaults():
    resp = StandardResponse()
    assert resp.result is None
    assert resp.message == ""
    assert resp.code == 0
    assert resp.exit_code == 0
