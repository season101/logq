from datetime import datetime, timezone
import pytest
from logq.parse import LEVELS, split_docker_line, parse_payload

def test_split_docker_line_nanoseconds():
    ts, payload = split_docker_line("2026-11-08T02:20:07.123456789Z hello world")
    assert ts == datetime(2026, 11, 8, 2, 20, 7, 123456, tzinfo=timezone.utc)
    assert payload == "hello world"

def test_split_docker_line_rejects_untimestamped():
    with pytest.raises(ValueError):
        split_docker_line("Error response from daemon: No such container")

def test_split_docker_line_rejects_naive_date():
    with pytest.raises(ValueError):
        split_docker_line("2026-11-08 server started")

def test_otel_fields():
    f = parse_payload('{"severity_text":"ERROR","body":"boom","trace_id":"7f3a9c21aa","span_id":"01","http.request.method":"POST","http.route":"/api/orders","http.response.status_code":500,"duration_ms":812,"code.function":"create_order","service.name":"api"}')
    assert (f["level"], f["msg"], f["trace"], f["span"]) == (LEVELS["error"], "boom", "7f3a9c21aa", "01")
    assert (f["method"], f["route"], f["status"], f["duration_ms"], f["func"], f["service"]) == ("POST", "/api/orders", 500, 812, "create_order", "api")

def test_pino_numeric_level_and_nested_req():
    f = parse_payload('{"level":40,"msg":"slow","req":{"method":"GET","url":"/x"},"res":{"statusCode":200},"responseTime":12}')
    assert (f["level"], f["method"], f["route"], f["status"], f["duration_ms"]) == (LEVELS["warn"], "GET", "/x", 200, 12)

def test_structlog_and_otel_python_correlation():
    f = parse_payload('{"event":"done","level":"warning","otelTraceID":"abc12345ff","funcName":"create_order"}')
    assert (f["msg"], f["level"], f["trace"], f["func"]) == ("done", LEVELS["warn"], "abc12345ff", "create_order")

def test_level_words():
    assert parse_payload('{"levelname":"CRITICAL","message":"x"}')["level"] == LEVELS["fatal"]
    assert parse_payload('{"log.level":"Warn","message":"x"}')["level"] == LEVELS["warn"]

def test_exception_fields():
    f = parse_payload('{"level":"error","message":"x","exception.type":"KeyError","exception.message":"\'sku\'","exception.stacktrace":"Traceback (most recent call last):\\n  File \\"a.py\\", line 1, in f\\nKeyError: \'sku\'"}')
    assert f["error"] == "KeyError: 'sku'"
    assert f["stack"] == ["Traceback (most recent call last):", '  File "a.py", line 1, in f', "KeyError: 'sku'"]

@pytest.mark.parametrize("p", ['["a"]', '"str"', "123", "{bad json"])
def test_non_object_json_is_plain_text(p):
    f = parse_payload(p)
    assert (f["msg"], f["level"]) == (p, LEVELS["info"])

def test_odd_level_value_becomes_info():
    assert parse_payload('{"level": ["x"], "msg": "m"}')["level"] == LEVELS["info"]

def test_uncastable_numbers_and_nulls_are_none():
    f = parse_payload('{"msg":"m","status":"ok","duration":"fast","trace_id":null,"requestId":"r1"}')
    assert (f["status"], f["duration_ms"], f["trace"]) == (None, None, "r1")

def test_pathologically_nested_json_is_plain_text():
    p = "{" * 100_000
    assert parse_payload(p)["msg"] == p
