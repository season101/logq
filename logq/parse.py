"""Docker log line -> Event fields. JSON payloads are mapped through spec section 5.1."""
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

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
        return {"level": LEVELS["info"], "msg": payload, "error": None, "stack": [],
                **dict.fromkeys(_ALIASES)}
    stack = _first(flat, _STACK_KEYS)
    return {
        "level": _level(_first(flat, _LEVEL_KEYS)),
        "msg": _cast(_first(flat, _MSG_KEYS), str) or "",
        "error": _error(flat),
        "stack": stack.splitlines() if isinstance(stack, str) else [],
        **{f: _cast(_first(flat, keys), _CAST.get(f, str)) for f, keys in _ALIASES.items()},
    }
