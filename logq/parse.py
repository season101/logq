"""Docker log line -> Event. JSON payloads follow spec section 5.1, plain text and grouping section 5.2."""
import json
import re
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

LEVELS = {"debug": 10, "info": 20, "warn": 30, "error": 40, "fatal": 50}
LEVEL_NAMES = {v: k.upper() for k, v in LEVELS.items()}

_WORDS = {"trace": 10, "debug": 10, "info": 20, "warn": 30, "warning": 30,
          "error": 40, "critical": 50, "fatal": 50, "panic": 50}
_PINO = {10: 10, 20: 10, 30: 20, 40: 30, 50: 40, 60: 50}

_LEVEL_KEYS = ("severity_text", "level", "levelname", "log.level", "severity")
_MSG_KEYS = ("body", "message", "msg", "event")
_STACK_KEYS = ("exception.stacktrace", "err.stack", "exc_info")
_ALIASES = {
    "trace": ("trace_id", "otelTraceID", "traceId", "trace.id", "request_id", "requestId", "correlation_id"),
    "span": ("span_id", "otelSpanID", "spanId", "span.id"),
    "service": ("service.name", "service"),
    "method": ("http.request.method", "method", "req.method"),
    "route": ("http.route", "route", "url.path", "path", "req.url"),
    "status": ("http.response.status_code", "status_code", "status", "res.statusCode"),
    "duration_ms": ("duration_ms", "duration", "responseTime", "elapsed_ms"),
    "func": ("code.function", "funcName", "function"),
}
_CAST = {"status": int, "duration_ms": float}  # everything else is str

_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_LEVEL_WORD = re.compile(r"\b(TRACE|DEBUG|INFO|WARN|WARNING|ERROR|CRITICAL|FATAL|PANIC)\b")
_ERR = re.compile(r"\b[\w.]*(?:Error|Exception):")
_WARN = re.compile(r"\b[\w.]*Warning:")
_TB = "Traceback (most recent call last):"
_CONTINUATION = ("Caused by:", "During handling of the above exception", "The above exception was the direct cause")
_TB_JOIN = timedelta(milliseconds=100)  # a traceback header this close to the previous line belongs to it
_PY_FRAME = re.compile(r'File "(.+)", line (\d+), in (\S+)')
_AT_FRAME = re.compile(r"\s+at (.+)")


@dataclass
class Event:
    ts: datetime
    container: str
    service: str
    project: str
    level: int
    msg: str
    trace: str | None = None
    span: str | None = None
    method: str | None = None
    route: str | None = None
    status: int | None = None
    duration_ms: float | None = None
    func: str | None = None
    error: str | None = None
    frame: str | None = None
    extra: list[str] = field(default_factory=list)
    raw: str = ""


def split_docker_line(line: str) -> tuple[datetime, str]:
    head, _, payload = line.partition(" ")
    ts = datetime.fromisoformat(head)  # raises ValueError if not a timestamp
    if ts.tzinfo is None:  # a bare date like "2026-11-08" is not a Docker timestamp
        raise ValueError("Docker timestamp has no timezone")
    return ts.astimezone(timezone.utc), payload


def _flatten(obj: dict, prefix: str = "") -> dict:
    flat = {}
    for k, v in obj.items():
        if isinstance(v, dict):
            flat.update(_flatten(v, f"{prefix}{k}."))
        else:
            flat[f"{prefix}{k}"] = v
    return flat


def _first(flat: dict, keys: tuple):
    return next((flat[k] for k in keys if flat.get(k) is not None), None)  # null counts as absent


def _cast(v, fn):
    try:
        return None if v is None else fn(v)
    except (TypeError, ValueError, OverflowError):
        return None


def _level(v) -> int:
    if isinstance(v, str):
        return _WORDS.get(v.strip().lower(), LEVELS["info"])
    if isinstance(v, int) and not isinstance(v, bool):
        return _PINO.get(v, LEVELS["info"])
    return LEVELS["info"]


def _plain_level(s: str) -> int:
    if m := _LEVEL_WORD.search(s):
        return _WORDS[m[1].lower()]
    if s.startswith(_TB) or _ERR.search(s):
        return LEVELS["error"]
    return LEVELS["warn"] if _WARN.search(s) else LEVELS["info"]


def _error(flat: dict) -> str | None:
    for p in ("exception", "err"):
        parts = [str(flat[k]) for k in (f"{p}.type", f"{p}.message") if flat.get(k) is not None]
        if parts:
            return ": ".join(parts)
    return _cast(flat.get("error"), str)


def parse_payload(payload: str) -> dict:
    try:
        obj = json.loads(payload) if payload.startswith("{") else None
        flat = _flatten(obj) if isinstance(obj, dict) else None
    except (ValueError, RecursionError):
        flat = None
    if flat is None:
        text = _ANSI.sub("", payload)
        return {"level": _plain_level(text), "msg": text, "error": None, "stack": [],
                **dict.fromkeys(_ALIASES)}
    stack = _first(flat, _STACK_KEYS)
    return {
        "level": _level(_first(flat, _LEVEL_KEYS)),
        "msg": _cast(_first(flat, _MSG_KEYS), str) or "",
        "error": _error(flat),
        "stack": stack.splitlines() if isinstance(stack, str) else [],
        **{f: _cast(_first(flat, keys), _CAST.get(f, str)) for f, keys in _ALIASES.items()},
    }


def _summary(lines: list[str]) -> str | None:
    """Error summary: the line ending the last Python traceback, else the first line if it looks like an error."""
    tb = [i for i, ln in enumerate(lines) if ln.startswith(_TB)]
    if tb and (end := next((ln for ln in lines[tb[-1] + 1:] if ln and not ln[0].isspace()), None)):
        return end
    return lines[0] if _ERR.search(lines[0]) else None


def _frame(lines: list[str]) -> str | None:
    """Innermost frame: the last Python `File` line, else the first JS/Java `at ...` line."""
    py = [m for ln in lines if (m := _PY_FRAME.search(ln))]
    if py:
        return f"{py[-1][1]}:{py[-1][2]} in {py[-1][3]}"
    return next((m[1].strip() for ln in lines if (m := _AT_FRAME.match(ln))), None)


def _finish(ev: Event) -> Event:
    while ev.extra and not ev.extra[-1]:  # blank lines join an event but do not belong to it at the end
        ev.extra.pop()
    lines = [ev.msg, *ev.extra]
    ev.frame = _frame(lines)
    ev.error = ev.error or _summary(lines)
    return ev


class Grouper:
    """Folds the lines of one container into Events (spec 5.2). An event is held until a line starts the next one."""

    def __init__(self, container: str, service: str, project: str, clock: Callable[[], float] = time.monotonic):
        self.container, self.service, self.project, self.clock = container, service, project, clock
        self.last_feed: float | None = None
        self._cur: Event | None = None
        self._last_ts: datetime | None = None  # Docker timestamp of the held event's last line
        self._in_tb = False  # between a traceback header and its summary line

    def feed(self, ts: datetime, payload: str) -> list[Event]:
        self.last_feed = self.clock()
        payload = _ANSI.sub("", payload)
        cur = self._cur
        if cur is None and not payload:  # a blank line has nothing to continue
            return []
        indented = not payload or payload[0].isspace()  # a blank line continues the previous event too
        tb_header = cur is not None and payload.startswith(_TB) and ts - self._last_ts <= _TB_JOIN
        joins = self._in_tb or indented or tb_header or payload.startswith(_CONTINUATION)
        if cur and joins and not payload.startswith("{"):  # a JSON line always starts its own event
            cur.extra.append(payload)
            cur.level = max(cur.level, _plain_level(payload))
            self._last_ts = ts
            self._in_tb = tb_header or (self._in_tb and indented)
            return []
        done = self.flush()
        f = parse_payload(payload)
        stack = f.pop("stack")
        f["service"] = f["service"] or self.service
        self._cur = Event(ts=ts, container=self.container, project=self.project, extra=stack, raw=payload, **f)
        self._last_ts, self._in_tb = ts, payload.startswith(_TB)
        return done

    def flush(self) -> list[Event]:
        ev, self._cur, self._in_tb = self._cur, None, False
        return [_finish(ev)] if ev else []


def parse_stream(lines: Iterable[str], container: str, service: str, project: str) -> list[Event]:
    g, events = Grouper(container, service, project), []
    for line in lines:
        try:
            ts, payload = split_docker_line(line.rstrip("\r\n"))
        except ValueError:
            continue
        events += g.feed(ts, payload)
    return events + g.flush()
