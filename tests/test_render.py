import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import pytest
from logq.parse import Event
from logq.docker import Container
from logq.render import ago, redact, format_event, format_container_alert, format_docker_event, format_repeat, footer
TZ, UTC = ZoneInfo("America/Chicago"), timezone.utc
T = datetime(2026, 11, 8, 18, 4, 31, 220000, tzinfo=UTC)

def ev(**kw):
    return Event(**{**dict(ts=T, container="api-1", service="api", project="p", level=20, msg="m"), **kw})

@pytest.mark.parametrize("secret,text", [
    ("abc.def.ghi", "Authorization: Bearer abc.def.ghi"),
    ("s3cr3tvalue", "token=s3cr3tvalue"),
    ("hunter2", '{"password": "hunter2"}'),
    ("pw123", "postgres://app:pw123@db:5432/x"),
    ("AKIAABCDEFGHIJKLMNOP", "key AKIAABCDEFGHIJKLMNOP"),
    ("sk-ABCDEFGHIJKLMNOPQRSTUV", "sk-ABCDEFGHIJKLMNOPQRSTUV"),
    ("ghp_" + "a" * 36, "ghp_" + "a" * 36),
    ("xoxb-123-456-abc", "slack xoxb-123-456-abc"),
    ("github_pat_11ABCDEFG0123456789_abcdefghijklmnop", "github_pat_11ABCDEFG0123456789_abcdefghijklmnop"),
    ("k3yvalue99", "api_key: k3yvalue99"),
    ("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnX3BhcnQ", "jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnX3BhcnQ"),
])
def test_redact(secret, text):
    out = redact(text)
    assert secret not in out and "[REDACTED]" in out

@pytest.mark.parametrize("text,expected", [
    ("token=s3cr3tvalue other", "token=[REDACTED] other"),
    ("api_key: k3yvalue99 next", "api_key: [REDACTED] next"),
    ('{"password": "hunter2", "user": "bob"}', '{"password": "[REDACTED]", "user": "bob"}'),
    ("GET /cb?token=abc&page=2 ok", "GET /cb?token=[REDACTED]&page=2 ok"),
    ('{"password": "pa\\"ss", "x": 1}', '{"password": "[REDACTED]", "x": 1}'),
    ("db at postgres://app:pw123@db:5432/x up", "db at postgres://app:[REDACTED]@db:5432/x up"),
    ("Authorization: Bearer abc.def.ghi then", "Authorization: [REDACTED] then"),
    ("jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnX3BhcnQ end", "jwt [REDACTED] end"),
    ("token_count=5 secrets: 3 task-queue-processing-worker-1", "token_count=[REDACTED] secrets: 3 task-queue-processing-worker-1"),
])
def test_redact_keeps_surrounding_text(text, expected):
    assert redact(text) == expected
    assert redact(redact(text)) == redact(text)

@pytest.mark.parametrize("secret,text,expected", [
    # Authorization with any scheme word, bare or quoted
    ("abc123", "authorization: Token abc123", "authorization: [REDACTED]"),
    ("abc123", '{"Authorization": "Token abc123"}', '{"Authorization": "[REDACTED]"}'),
    ("gho_16C7e42F292c6912E7710c838347Ae178B4a", "Authorization: token gho_16C7e42F292c6912E7710c838347Ae178B4a", "Authorization: [REDACTED]"),
    ("xyz789", "Authorization: ApiKey xyz789 next=1", "Authorization: [REDACTED] next=1"),
    ("SigPart99", 'headers={"Authorization": "AWS4-HMAC-SHA256 Credential=ID/20260101/s3, SignedHeaders=host, Signature=SigPart99"}', 'headers={"Authorization": "[REDACTED]"}'),
    ("SigPart99", "Authorization: AWS4-HMAC-SHA256 Credential=ID/20260101/s3, SignedHeaders=host;x-amz-date, Signature=SigPart99", "Authorization: [REDACTED]"),
    ("resp0nse", 'Authorization: Digest username="bob", realm="r", response="resp0nse"', "Authorization: [REDACTED]"),
    ("resp0nse", '{"Authorization": "Digest username=\\"bob\\", response=\\"resp0nse\\""}', '{"Authorization": "[REDACTED]"}'),
    # URL credentials: empty user, "@" in the password
    ("s3cretpw", "redis://:s3cretpw@redis:6379/0", "redis://:[REDACTED]@redis:6379/0"),
    ("p@ss", "postgres://app:p@ss@db:5432/x", "postgres://app:[REDACTED]@db:5432/x"),
    # keywords in the middle of the key name
    ("wJalrXUtnFEMI/K7MDENG", "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG ok", "AWS_SECRET_ACCESS_KEY=[REDACTED] ok"),
    ("hunter2", "password1=hunter2&password2=hunter2", "password1=[REDACTED]&password2=[REDACTED]"),
    ("hunter2", "password_confirmation=hunter2", "password_confirmation=[REDACTED]"),
    ("hunter2", 'passwordConfirm: "hunter2"', 'passwordConfirm: "[REDACTED]"'),
    ("hunter2", "SECRET_KEY=hunter2", "SECRET_KEY=[REDACTED]"),
])
def test_redact_leak_probes(secret, text, expected):
    assert redact(text) == expected and secret not in redact(text)
    assert redact(redact(text)) == redact(text)

def test_redact_does_not_touch_plain_urls_and_counters():
    text = "GET http://host:8080/x?mail=a@b.com bypass=1 compass: north"
    assert redact(text) == text
    # a key with a suffix redacts too: over-redaction is the safe failure
    assert redact("token_count=5 password_policy=strict") == "token_count=[REDACTED] password_policy=[REDACTED]"

B64 = "dXNlcjpwYXNzd29yZA=="

@pytest.mark.parametrize("text,expected", [
    # Authorization in header dumps: value in a list or map, prefixed key names
    (f"map[Accept:[*/*] Authorization:[Basic {B64}] X:[1]]", "map[Accept:[*/*] Authorization:[[REDACTED]] X:[1]]"),
    (f'{{"Authorization":["Basic {B64}"]}}', '{"Authorization":["[REDACTED]"]}'),
    (f"{{'Authorization': ['Basic {B64}']}}", "{'Authorization': ['[REDACTED]']}"),
    (f"{{'HTTP_AUTHORIZATION': 'Basic {B64}', 'x': 1}}", "{'HTTP_AUTHORIZATION': '[REDACTED]', 'x': 1}"),
    (f"proxy_authorization: Basic {B64} next", "proxy_authorization: [REDACTED] next"),
    (f'{{"request_Authorization":"Basic {B64}"}}', '{"request_Authorization":"[REDACTED]"}'),
    # cookies: the whole value
    ("Cookie: sessionid=abc123; theme=dark next", "Cookie: [REDACTED] next"),
    ("Set-Cookie: sessionid=abc123; Path=/; HttpOnly", "Set-Cookie: [REDACTED]"),
    ("{'HTTP_COOKIE': 'sessionid=abc123; theme=dark'}", "{'HTTP_COOKIE': '[REDACTED]'}"),
    ("map[Cookie:[sessionid=abc123; theme=dark]]", "map[Cookie:[[REDACTED]]]"),
    # key names with a suffix, and short password names
    ("SECRET_KEY_BASE=abc123", "SECRET_KEY_BASE=[REDACTED]"),
    ("DB_PASS=abc123", "DB_PASS=[REDACTED]"),
    ("MYSQL_PWD=abc123", "MYSQL_PWD=[REDACTED]"),
    ("password_hash: abc123", "password_hash: [REDACTED]"),
    ("api_key_2=abc123", "api_key_2=[REDACTED]"),
    ('{"token_value": "abc123"}', '{"token_value": "[REDACTED]"}'),
    ("passphrase=abc123", "passphrase=[REDACTED]"),
    ("secret-key-base: abc123", "secret-key-base: [REDACTED]"),
])
def test_redact_header_dumps_cookies_and_suffixed_keys(text, expected):
    assert redact(text) == expected
    assert B64 not in redact(text) and "abc123" not in redact(text)
    assert redact(redact(text)) == redact(text)

def test_redact_unterminated_quote_and_long_lines():
    assert redact('{"password": "abc') == '{"password": "[REDACTED]"'
    start = time.perf_counter()
    for s in ("a" * 200_000, "eyJ" * 60_000, 'password="' + "\\" * 5_000, "http://" + "a:" * 30_000, "a://" * 50_000,
              "Authorization: " + "a " * 100_000, "Authorization: X " + "k=v, " * 50_000, "authorization=" * 10_000,
              "token_" * 50_000, "DB_PASS_" * 30_000, "Cookie: a=b;" * 30_000, "Authorization:[" * 20_000):
        redact(s)
    assert time.perf_counter() - start < 2

def test_redact_runs_on_every_returned_line():
    e = ev(msg="login token=s3cr3tvalue", method="GET", route="/cb?secret=zzz", extra=["password=hunter2"])
    out = format_event(e, TZ, full=True)
    assert "s3cr3tvalue" not in out and "zzz" not in out and "hunter2" not in out and out.count("[REDACTED]") == 3

def test_secret_is_redacted_before_truncation():
    out = format_event(ev(msg="x" * 285 + " AKIAABCDEFGHIJKLMNOP"), TZ)
    assert "AKIA" not in out

@pytest.mark.parametrize("secret,kept,visible", [  # `kept` = secret characters that survive before the 300-char cut
    ("postgres://app:supersecretpassword@db:5432/x", 21, "supers"),
    ("sk-" + "A" * 30, 10, "sk-AAAA"),
    ("ghp_" + "b" * 36, 12, "ghp_bbbb"),
    ("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnX3BhcnQ", 30, "eyJ"),
])
def test_repeat_secret_straddling_the_cut_is_redacted(secret, kept, visible):
    out = format_repeat(ev(level=40, msg="x" * (298 - kept) + " " + secret), 2, 30)
    assert visible not in out and "[REDAC" in out  # the marker itself may be cut

def test_request_line():
    e = ev(msg="request finished", method="POST", route="/api/orders", status=500, duration_ms=812, func="create_order", trace="7f3a9c21aabbccdd")
    assert format_event(e, TZ) == "12:04:31.220 api    INFO  POST /api/orders 500 812ms create_order request finished trace=7f3a9c21"

def test_folded_error_and_full():
    e = ev(level=40, msg="Traceback (most recent call last):", error="KeyError: 'sku'", frame="orders/views.py:42 in create_order", extra=[f"l{i}" for i in range(14)], trace="7f3a9c21aabb")
    assert format_event(e, TZ) == "12:04:31.220 api    ERROR KeyError: 'sku' at orders/views.py:42 in create_order (+14 lines) trace=7f3a9c21"
    assert format_event(e, TZ, full=True).splitlines()[1:] == [f"l{i}" for i in range(14)]

def test_full_keeps_blank_extra_lines_and_untruncated_msg():
    out = format_event(ev(msg="x" * 400, extra=["a", "", "b"]), TZ, full=True)
    assert out.split("\n")[1:] == ["a", "", "b"] and out.split("\n")[0].endswith("x" * 400)

def test_msg_kept_beside_error_and_truncation():
    assert "charge failed | ValueError: x" in format_event(ev(level=40, msg="charge failed", error="ValueError: x"), TZ)
    body = format_event(ev(msg="x" * 400), TZ).split("INFO  ")[1]
    assert len(body) == 300 and body.endswith("…")

def test_msg_dropped_when_empty_or_equal_to_error():
    assert format_event(ev(level=40, msg="", error="E: x"), TZ).endswith("ERROR E: x")
    assert format_event(ev(level=40, msg="E: x", error="E: x"), TZ).endswith("ERROR E: x")
    assert format_event(ev(msg=""), TZ) == "12:04:31.220 api    INFO"

def test_footer_variants():
    assert footer(3, 3, ["api", "worker", "db", "web"], "15m", 10, "7f3a9c21aabb", []) == \
        "-- 3 of 3 matches · 4 containers (api, worker, db, web) · 15m · level>=debug · trace=7f3a9c21"
    assert footer(0, 0, ["api", "db"], "15m", 30, None, []) == "-- no matches · 2 containers (api, db) · 15m · level>=warn"
    assert footer(50, 212, ["api"], "15m", 30, None, ["api-1"]) == \
        "-- 50 of 212 matches (oldest dropped) · 1 container (api) · 15m · level>=warn · capped at 50000 lines: api-1"
    assert "9 containers ·" in footer(0, 0, [f"s{i}" for i in range(9)], "15m", 30, None, [])
    assert "(s0" not in footer(0, 0, [f"s{i}" for i in range(9)], "15m", 30, None, [])
    assert "8 containers (s0," in footer(0, 0, [f"s{i}" for i in range(8)], "15m", 30, None, [])

def test_ago():
    assert [ago(timedelta(seconds=s)) for s in (45, 479, 3 * 3600 + 59, 2 * 86400 + 5, -9)] == ["45s", "7m", "3h", "2d", "0s"]

def test_container_alert():
    now = datetime(2026, 11, 8, 2, 20, 0, tzinfo=UTC)
    exited = Container("i", "web-1", "p", "web", None, "exited", None, 137, 0, None, now - timedelta(minutes=2))
    assert format_container_alert(exited, now) == "! web-1 exited(137) 2m ago"
    assert format_container_alert(Container("i", "db-1", "p", "db", None, "running", "unhealthy", 0, 0, now, None), now) == "! db-1 unhealthy"
    assert format_container_alert(Container("i", "db-1", "p", "db", None, "running", "healthy", 0, 0, now, None), now) is None

def test_container_alert_other_states():
    now = datetime(2026, 11, 8, 2, 20, 0, tzinfo=UTC)
    def c(state, **kw):
        return Container(**{**dict(id="i", name="web-1", project="p", service="web", working_dir=None, state=state, health=None, exit_code=0, restarts=0, started_at=None, finished_at=None), **kw})
    assert format_container_alert(c("exited", exit_code=1), now) == "! web-1 exited(1)"
    assert format_container_alert(c("restarting"), now) == "! web-1 restarting"
    assert format_container_alert(c("dead"), now) == "! web-1 dead"
    assert format_container_alert(c("created"), now) is None
    assert format_container_alert(c("exited", health="unhealthy", finished_at=now), now) == "! web-1 exited(0) 0s ago"

def test_docker_events():
    base = {"timeNano": 1762625402114000000, "Actor": {"Attributes": {"com.docker.compose.service": "api", "name": "p-api-1", "exitCode": "137"}}}
    assert format_docker_event({**base, "Action": "die"}, UTC).endswith("! api died exit=137")
    assert format_docker_event({**base, "Action": "oom"}, UTC).endswith("! api oom")
    assert format_docker_event({**base, "Action": "health_status: unhealthy"}, UTC).endswith("! api health: unhealthy")
    assert format_docker_event({**base, "Action": "destroy"}, UTC).endswith("! api removed")
    assert format_docker_event({**base, "Action": "exec_start: sh"}, UTC) is None

def test_docker_event_time_actions_and_name_fallback():
    evt = {"timeNano": 1762625402114000000, "Action": "start", "Actor": {"Attributes": {"name": "p-api-1"}}}
    assert format_docker_event(evt, UTC) == "18:10:02.114 ! p-api-1 started"
    assert format_docker_event({**evt, "Action": "restart"}, UTC).endswith("! p-api-1 restarted")
    assert format_docker_event(evt, TZ).startswith("12:10:02.114 ")

def test_repeat_line():
    assert format_repeat(ev(level=40, error="KeyError: 'sku'"), 39, 30) == "↻ api ERROR KeyError: 'sku' repeated 39x in 30s"
    assert format_repeat(ev(level=30, msg="retry token=abc1"), 3, 30) == "↻ api WARN retry token=[REDACTED] repeated 3x in 30s"

def test_repeat_line_prints_rounded_seconds():
    assert format_repeat(ev(level=40, error="KeyError: 'sku'"), 2, 7.4).endswith("repeated 2x in 7s")

def test_repeat_line_names_the_request():
    e = ev(msg="request finished", method="POST", route="/api/orders", status=500, duration_ms=812, func="create_order")
    assert format_repeat(e, 3, 30) == "↻ api INFO POST /api/orders 500 request finished repeated 3x in 30s"

def test_multi_line_context_shows_without_an_error():
    e = ev(msg="handling request", frame="app/x.py:3 in f", extra=["a", "b"])
    assert format_event(e, TZ).endswith("INFO  handling request at app/x.py:3 in f (+2 lines)")
    assert format_event(ev(msg="warned", extra=["  detail"]), TZ).endswith("INFO  warned (+1 lines)")

def test_java_cause_is_shown():
    from pathlib import Path
    from logq.parse import parse_stream
    java = parse_stream((Path(__file__).parent / "fixtures/stacks.log").read_text().splitlines(), "api-1", "api", "p")[1]
    assert format_event(java, TZ).split("ERROR ", 1)[1] == \
        "ERROR request failed | java.io.IOException: reset at com.acme.Orders.create(Orders.java:88) (+2 lines)"

def test_footer_names_the_project_after_the_containers():
    assert footer(3, 3, ["api"], "15m", 30, None, [], project="p") == "-- 3 of 3 matches · 1 container (api) · project p · 15m · level>=warn"

def test_footer_counts_events_hidden_below_the_default_level():
    assert footer(0, 0, ["api"], "15m", 30, None, [], project="p", below=3) == \
        "-- no matches · 1 container (api) · project p · 15m · level>=warn · 3 more below warn"

SK = "sk_live_" + "4eC39HqLyjWDarjtT1zdp7dc"

@pytest.mark.parametrize("secret,text,expected", [
    # a quoted value inside a cookie does not end the cookie
    ("S3ss", 'Cookie: a="x"; sessionid=S3ss next', "Cookie: [REDACTED] next"),
    # every value of a multi-value header
    ("BBB2", "map[Authorization:[Basic AAA1 Basic BBB2] X:[1]]", "map[Authorization:[[REDACTED]] X:[1]]"),
    ("BBB2", '{"Authorization":["Basic AAA1","Basic BBB2"]}', '{"Authorization":["[REDACTED]"]}'),
    ("S3ss", "map[Set-Cookie:[a=1; Path=/ sid=S3ss]]", "map[Set-Cookie:[[REDACTED]]]"),
    ("BBB2", "Authorization: Basic AAA1, Basic BBB2 next", "Authorization: [REDACTED] next"),
    # cookies joined by commas, also after an Expires date
    ("S3ss", "Cookie: a=1, sessionid=S3ss next", "Cookie: [REDACTED] next"),
    ("S3ss", "Set-Cookie: a=1; Expires=Wed, 21 Oct 2026 07:28:00 GMT, sid=S3ss; Path=/", "Set-Cookie: [REDACTED]"),
    # escaped JSON inside text
    ("AAA1", 'body={\\"Authorization\\":\\"Basic AAA1\\",\\"x\\":1}', 'body={\\"Authorization\\":\\"[REDACTED]\\",\\"x\\":1}'),
    ("hunter2", 'body={\\"password\\":\\"hunter2\\",\\"x\\":1}', 'body={\\"password\\":\\"[REDACTED]\\",\\"x\\":1}'),
    ("S3ss", 'body={\\"Cookie\\":\\"sid=S3ss; a=1\\"}', 'body={\\"Cookie\\":\\"[REDACTED]\\"}'),
    # ASGI header tuples
    ("AAA1", "[(b'host', b'x'), (b'authorization', b'Basic AAA1')]", "[(b'host', b'x'), (b'authorization', b'[REDACTED]')]"),
    ("S3ss", "[(b'cookie', b'sid=S3ss; a=1')]", "[(b'cookie', b'[REDACTED]')]"),
    ("abc123", "[(b'x-api-key', b'abc123')]", "[(b'x-api-key', b'[REDACTED]')]"),
    ("AAA1", "{'Authorization': ('Basic AAA1',)}", "{'Authorization': ('[REDACTED]',)}"),
    # a key whose value is a list (Django's QueryDict)
    ("hunter2", "<QueryDict: {'password': ['hunter2', 'x'], 'next': ['/']}>", "<QueryDict: {'password': ['[REDACTED]'], 'next': ['/']}>"),
    # camelCase and digit key suffixes
    ("abc123", "passwordHash=abc123", "passwordHash=[REDACTED]"),
    ("abc123", '{"tokenValue": "abc123"}', '{"tokenValue": "[REDACTED]"}'),
    ("abc123", "apiKeyId: abc123", "apiKeyId: [REDACTED]"),
    ("abc123", "secretKeyBase=abc123", "secretKeyBase=[REDACTED]"),
    ("abc123", "token2=abc123", "token2=[REDACTED]"),
    # key shapes
    (SK, f"stripe {SK} ok", "stripe [REDACTED] ok"),
    ("rk_live_abcdefghij12", "rk_live_abcdefghij12", "[REDACTED]"),
    ("glpat-xYz123AbC456DeF789gh", "glpat-xYz123AbC456DeF789gh ok", "[REDACTED] ok"),
    ("AIzaSyD-abcdefghijklmnopqrstuvwxyz01234", "key=AIzaSyD-abcdefghijklmnopqrstuvwxyz01234", "key=[REDACTED]"),
    ("gho_" + "c" * 36, "gho_" + "c" * 36, "[REDACTED]"),
    ("ghs_" + "d" * 36, "via ghs_" + "d" * 36, "via [REDACTED]"),
    ("xoxa-2-abc", "slack xoxa-2-abc", "slack [REDACTED]"),
    ("xoxe-1-abc", "slack xoxe-1-abc", "slack [REDACTED]"),
    ("MIIEpAIBAAKCAQEA", "k=-----BEGIN RSA PRIVATE KEY-----\\nMIIEpAIBAAKCAQEA\\n-----END RSA PRIVATE KEY----- ok", "k=[REDACTED] ok"),
    ("MIIEpAIBAAKCAQEA", "-----BEGIN PRIVATE KEY-----\nMIIEpAIBAAKCAQEA\n-----END PRIVATE KEY-----\nok", "[REDACTED]\nok"),
    ("MIIEpAIBAAKCAQEA", "-----BEGIN OPENSSH PRIVATE KEY-----\nMIIEpAIBAAKCAQEA", "[REDACTED]"),  # cut short: to the end
])
def test_redact_follow_up_leak_probes(secret, text, expected):
    assert redact(text) == expected and secret not in redact(text)
    assert redact(redact(text)) == redact(text)

def test_redact_camel_case_needs_a_capital_or_digit():
    assert redact("passenger=2 tokens=5") == "passenger=2 tokens=5"

def test_redact_follow_up_shapes_stay_linear():
    start = time.perf_counter()
    for s in ('Cookie: a="' * 20_000, "Cookie: a=1, " * 20_000, "Set-Cookie: expires=" * 20_000, '\\"' * 50_000,
              'password=\\"' + '\\\\\\"' * 20_000, "(b'authorization', " * 10_000, "-----BEGIN PRIVATE KEY-----" * 5_000,
              "tokenA" * 30_000, 'Authorization:["' * 20_000, "Authorization: a, " * 20_000, "Cookie:[" * 20_000):
        redact(s)
    assert time.perf_counter() - start < 2

def test_full_event_redacts_a_private_key_split_over_lines():
    from logq.parse import parse_stream
    lines = ["-----BEGIN RSA PRIVATE KEY-----", "MIIEpAIBAAKCAQEA", "c2VjcmV0", "-----END RSA PRIVATE KEY-----", "next line"]
    events = parse_stream([f"2026-11-08T18:04:31.{i}Z {ln}" for i, ln in enumerate(lines)], "api-1", "api", "p")
    out = "\n".join(format_event(e, TZ, full=True) for e in events)
    assert "MIIE" not in out and "c2Vj" not in out and "next line" in out
