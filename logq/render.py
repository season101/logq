"""Output lines for logq: events, container alerts, docker events, repeats, footers (spec sections 4.3, 4.4) and redaction (section 6)."""
import re
from datetime import datetime, timedelta, timezone, tzinfo

from logq.docker import Container
from logq.parse import LEVEL_NAMES, Event

MSG_LIMIT = 300
READ_CAP = 50000  # keep equal to the default cap of docker.read_logs
_B = r"(?<![A-Za-z0-9])"  # not in the middle of a word, so `task-queue-…` is not an sk- key
# `pass`, `passphrase` and `pwd` only as a whole segment (`DB_PASS`, not `bypass`); the others anywhere (`csrftoken`).
# Any `_`/`-` suffix counts (`SECRET_KEY_BASE`, `token_value`), so `token_count` redacts too: over-redaction is the safe failure.
# shortcut: the suffix is capped at 64 characters (possessive, so no backtracking) to stay linear on long words, upgrade if
# real key names are longer.
_KEYS = (r"(?:(?:pass(?:word|wd)(?:\d+|[_-]?confirm(?:ation)?)?|secret(?:[_-]?(?:access[_-]?)?key)?|token|api[_-]?key)"
         r"|(?<![A-Za-z])(?:pass(?:phrase)?|pwd))(?:[_-][\w-]{0,64}+)?")
_QUOTED = r"""(?P<q>["'])(?:\\.|(?!(?P=q))[^\\\n])*(?P=q)?"""  # an unterminated quote runs to end of line
_VAL = r"""(?:"[^"\n]*"|[^\s,"'\[\]]+)"""  # stops at `]`, the end of a Go header list
# The separator, then an optional list or map opener (`Authorization:[Basic …]`, `{"Authorization":["…"]}`); an opener already
# followed by the marker is not taken, so redacting twice changes nothing.
_OPEN = r"""["']?[ \t]*[:=][ \t]*(?:[\[(](?!REDACTED\]))?"""
# Authorization: an optional scheme word (any: Bearer, Token, ApiKey, AWS4-HMAC-SHA256, Digest, ...), then a token or key=value params
# joined by commas (SigV4, Digest). A quoted value is redacted whole. A prefixed key counts (`HTTP_AUTHORIZATION`, `proxy_authorization`).
_AUTH = re.compile(rf"""(?P<k>{_B}authorization{_OPEN})(?:{_QUOTED}|(?:[A-Za-z][\w-]*[ \t]+)?(?:[\w.-]+=)?{_VAL}(?:,[ \t]*[\w.-]+={_VAL})*)""", re.I)
_PAIR = r"""[^\s;,"'\[\]]+"""
_COOKIE = re.compile(rf"""(?P<k>{_B}(?:set-)?cookie{_OPEN})(?:{_QUOTED}|{_PAIR}(?:;[ \t]*{_PAIR})*)""", re.I)  # every pair
# (pattern, replacement); order matters: Bearer before the generic key rule so `token: Bearer x` loses both words.
_RULES = [(re.compile(p, f), r) for p, f, r in [
    (r"(\bbearer[ \t]+)[\w.~+/=-]+", re.I, r"\1[REDACTED]"),
    # Scheme is bounded and the password runs to the last `@` of the token, so `p@ss` is covered. Anchored on `://` to stay linear.
    # shortcut: passwords containing a raw "/" are not redacted (RFC 3986 requires percent-encoding, and allowing "/" would eat
    # `http://host:80/p?mail=a@b.c`), upgrade if real logs show them.
    (r"([a-z][a-z0-9+.-]{0,31}://[^\s:/@]*:)[^\s/]+(?=@)", re.I, r"\1[REDACTED]"),
    (_B + r"eyJ[\w-]+\.[\w-]+\.[\w-]+", 0, "[REDACTED]"),
    (_B + r"(?:AKIA[0-9A-Z]{16}|sk-[\w-]{20,}|ghp_[A-Za-z0-9]{20,}|github_pat_\w{20,}|xox[bp]-[\w-]+)", 0, "[REDACTED]"),
]]
# key=value, key: value and "key": "value"; keeps key, separator and quotes, replaces only the value.
# No alternative overlaps another (bounded scheme above, `[^\\\n]` beside `\\.`), so long lines cannot backtrack badly.
_KV = re.compile(rf"""(?P<k>{_KEYS}["']?[ \t]*[:=][ \t]*)(?:{_QUOTED}|[^\s,;&"']+)""", re.I)


def _keep_quotes(m: re.Match) -> str:
    q = m["q"] or ""
    return f"{m['k']}{q}[REDACTED]{q}"


def redact(text: str) -> str:
    for rx in (_AUTH, _COOKIE):
        text = rx.sub(_keep_quotes, text)
    for rx, repl in _RULES:
        text = rx.sub(repl, text)
    return _KV.sub(_keep_quotes, text)


def ago(delta: timedelta) -> str:
    s = max(0, int(delta.total_seconds()))
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if s >= size:
            return f"{s // size}{unit}"
    return f"{s}s"


def _clock(ts: datetime, tz: tzinfo | None) -> str:
    t = ts.astimezone(tz)
    return f"{t:%H:%M:%S}.{t.microsecond // 1000:03d}"


def _cut(body: str) -> str:
    return body if len(body) <= MSG_LIMIT else body[:MSG_LIMIT - 1] + "…"


def format_event(e: Event, tz: tzinfo | None, full: bool = False) -> str:
    body = e.error or e.msg
    if e.error and e.msg and e.msg != e.error and not e.msg.startswith("Traceback"):
        body = f"{e.msg} | {e.error}"
    body += (f" at {e.frame}" if e.frame else "") + (f" (+{len(e.extra)} lines)" if e.extra and not full else "")  # error or not
    body = redact(body)  # before cutting, so a secret split by the cut cannot slip through
    if not full:
        body = _cut(body)
    http = [e.method, e.route, e.status, None if e.duration_ms is None else f"{round(e.duration_ms)}ms", e.func]
    parts = [_clock(e.ts, tz), f"{e.service:<6}", f"{LEVEL_NAMES[e.level]:<5}"]
    parts += [str(x) for x in http if x is not None] + [body] + ([f"trace={e.trace[:8]}"] if e.trace else [])
    line = redact(" ".join(p for p in parts if p).rstrip())
    return "\n".join([line] + [redact(x) for x in e.extra]) if full else line


def format_container_alert(c: Container, now: datetime) -> str | None:
    if c.state == "exited":
        when = f" {ago(now - c.finished_at)} ago" if c.finished_at else ""
        return redact(f"! {c.name} exited({c.exit_code}){when}")
    if c.state in ("restarting", "dead") or (c.state == "running" and c.health == "unhealthy"):
        return redact(f"! {c.name} {c.health if c.state == 'running' else c.state}")
    return None


def format_docker_event(evt: dict, tz: tzinfo | None) -> str | None:
    a = evt.get("Actor", {}).get("Attributes", {})
    action = evt.get("Action", "")
    what = {"oom": "oom", "start": "started", "restart": "restarted", "destroy": "removed"}.get(action)
    if action == "die":
        what = f"died exit={a.get('exitCode', '?')}"
    elif action.startswith("health_status: "):
        what = f"health: {action.removeprefix('health_status: ')}"
    if what is None:
        return None
    ts = datetime.fromtimestamp(0, timezone.utc) + timedelta(microseconds=evt["timeNano"] // 1000)  # integer math keeps the ms exact
    return redact(f"{_clock(ts, tz)} ! {a.get('com.docker.compose.service') or a.get('name', '?')} {what}")


def format_repeat(e: Event, count: int, seconds: float) -> str:
    head = " ".join([e.service, LEVEL_NAMES[e.level], *(str(x) for x in (e.method, e.route, e.status) if x is not None)])
    return redact(f"↻ {head} {_cut(redact(e.error or e.msg))} repeated {count}x in {round(seconds)}s")  # redact before the cut


def footer(shown: int, matched: int, containers: list[str], window: str, level: int, trace: str | None, capped: list[str],
           project: str | None = None) -> str:
    n = len(containers)
    names = f" ({', '.join(containers)})" if 0 < n <= 8 else ""
    parts = [
        "no matches" if not matched else f"{shown} of {matched} matches" + (" (oldest dropped)" if shown < matched else ""),
        f"{n} container{'s' * (n != 1)}{names}",
        *([f"project {project}"] if project else []),
        window,
        f"level>={LEVEL_NAMES[level].lower()}",
    ]
    if trace:
        parts.append(f"trace={trace[:8]}")
    if capped:
        parts.append(f"capped at {READ_CAP} lines: {', '.join(capped)}")
    return "-- " + " · ".join(parts)
