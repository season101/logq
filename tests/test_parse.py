from datetime import datetime, timezone
from pathlib import Path
import pytest
from logq.parse import LEVELS, Grouper, parse_payload, parse_stream, split_docker_line

FIX = Path(__file__).parent / "fixtures"
I, W, E = LEVELS["info"], LEVELS["warn"], LEVELS["error"]

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

def events(name):
    return parse_stream(FIX.joinpath(name).read_text().splitlines(), "api-1", "api", "p")

def test_pilot_levels_and_grouping():
    ev = events("pilot_api.log")
    assert [e.level for e in ev] == [I, W, I, W, E, E]
    assert ev[3].extra == ["  decoded = self.decode_complete("]

def test_python_traceback_folds_to_one_event():
    tb = events("pilot_api.log")[4]
    assert tb.error == "KeyError: 'sku'"
    assert tb.frame == "/app/orders/views.py:42 in create_order"
    assert len(tb.extra) == 3

def test_ansi_stripped():
    assert events("pilot_api.log")[5].msg == "ERROR db pool exhausted"

def test_js_and_java_frames():
    js, java = events("stacks.log")
    assert (js.level, js.error, js.frame) == (E, "Error: boom", "handler (/app/src/api.js:10:5)")
    assert java.frame == "com.acme.Orders.create(Orders.java:88)" and len(java.extra) == 2

def test_json_stack_gets_frame():
    line = '2026-11-08T02:20:07.0Z {"level":"error","message":"x","exc_info":"Traceback (most recent call last):\\n  File \\"a.py\\", line 1, in f\\nKeyError: 1"}'
    (e,) = parse_stream([line], "c", "s", "p")
    assert e.frame == "a.py:1 in f"
    assert e.error == "KeyError: 1"  # exc_info only, so error comes from the stack summary

def test_grouper_tracks_last_feed():
    t = iter([5.0])
    g = Grouper("c", "s", "p", clock=lambda: next(t))
    g.feed(*split_docker_line("2026-11-08T02:20:07.0Z ERROR x"))
    assert g.last_feed == 5.0

@pytest.mark.parametrize("p, level", [
    ("[INFO] hi", "info"), ("TRACE x", "debug"), ("WARNING x", "warn"), ("CRITICAL x", "fatal"), ("PANIC x", "fatal"),
    ("ValueError: x", "error"), ("a.b.BarException: x", "error"), ("DeprecationWarning: x", "warn"),
    ("error: lower case is not a level", "info"), ("hello", "info"),
])
def test_plain_text_levels(p, level):
    assert parse_payload(p)["level"] == LEVELS[level]

def test_json_line_with_traceback_text_does_not_swallow_next_line():
    tb = '2026-11-08T02:20:07.0Z {"level":"error","message":"x","exc_info":"Traceback (most recent call last):\\nKeyError: 1"}'
    ev = parse_stream([tb, "2026-11-08T02:20:08.0Z next"], "c", "s", "p")
    assert [e.msg for e in ev] == ["x", "next"]

def test_service_trace_and_raw():
    j = '2026-11-08T02:20:07.0Z {"msg":"m","service":"billing","trace_id":"abc"}'
    a, b = parse_stream([j, "2026-11-08T02:20:08.0Z \x1b[0mtrace abc"], "c-1", "api", "p")
    assert (a.service, a.trace, a.raw) == ("billing", "abc", j.split(" ", 1)[1])
    assert (b.service, b.raw, b.container, b.project) == ("api", "trace abc", "c-1", "p")

def test_untimestamped_lines_skipped_and_newlines_stripped():
    ev = parse_stream(["Error response from daemon: x\n", "2026-11-08T02:20:08.0Z ok\r\n"], "c", "s", "p")
    assert [e.msg for e in ev] == ["ok"]

def line(ms, payload):
    s, ms = divmod(ms, 1000)
    return f"2026-11-08T02:20:{s:02d}.{ms:03d}Z {payload}"

def seq(payloads, start=0):  # Docker timestamps 1 ms apart
    return [line(start + i, p) for i, p in enumerate(payloads)]

def run(lines):
    return parse_stream(lines, "c", "s", "p")

HEAD = "ERROR Internal Server Error: /api/orders"
TB = ["Traceback (most recent call last):", '  File "/app/x.py", line 3, in f', '    sku = data["sku"]', "KeyError: 'sku'"]

def test_traceback_folds_into_preceding_log_line():
    (e,) = run(seq([HEAD, *TB]))
    assert (e.level, e.msg, e.error, e.frame) == (E, HEAD, "KeyError: 'sku'", "/app/x.py:3 in f")

def test_traceback_after_a_gap_is_a_separate_event():
    first, tb = run(seq([HEAD]) + seq(TB, start=2000))
    assert first.frame is None
    assert (tb.level, tb.msg, tb.error) == (E, TB[0], "KeyError: 'sku'")

def test_traceback_header_raises_level_of_info_line():
    (e,) = run(seq(["handling request", *TB]))
    assert (e.level, e.msg) == (E, "handling request")

@pytest.mark.parametrize("link", [
    "During handling of the above exception, another exception occurred:",
    "The above exception was the direct cause of the following exception:",
])
def test_chained_tracebacks_are_one_event(link):
    tb2 = [TB[0], '  File "/app/y.py", line 9, in g', '    raise ValueError("bad")', "ValueError: bad"]
    (e,) = run(seq([*TB, "", link, "", *tb2, ""]))
    assert (e.level, e.msg, e.error, e.frame) == (E, TB[0], "ValueError: bad", "/app/y.py:9 in g")
    assert e.extra[-1] == "ValueError: bad" and "" in e.extra  # trailing blank dropped, inner blanks kept

def test_json_line_inside_traceback_is_its_own_event():
    tb, js = run(seq([*TB[:2], '{"level":"info","msg":"x"}']))
    assert (tb.error, tb.frame, tb.extra) == (None, "/app/x.py:3 in f", [TB[1]])
    assert (js.msg, js.level, js.extra) == ("x", I, [])

def test_blank_line_first_makes_no_event():
    assert [e.msg for e in run(seq(["", "x"]))] == ["x"]
    assert run(seq([""])) == []
