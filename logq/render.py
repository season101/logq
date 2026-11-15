"""Output lines for logq: events, container alerts, docker events, repeats, footers (spec sections 4.3, 4.4) and redaction (section 6)."""
import re
from datetime import datetime, timedelta, timezone, tzinfo

from logq.docker import Container
from logq.parse import LEVEL_NAMES, Event

MSG_LIMIT = 300
READ_CAP = 50000  # keep equal to the default cap of docker.read_logs
_B = r"(?<![A-Za-z0-9])"  # not in the middle of a word, so `task-queue-…` is not an sk- key
# `pass`, `passphrase` and `pwd` only as a whole segment (`DB_PASS`, not `bypass`); the others anywhere (`csrftoken`).
# Any `_`/`-`, capital or digit suffix counts (`SECRET_KEY_BASE`, `tokenValue`, `token2`), so `token_count` redacts too:
# over-redaction is the safe failure. A lower-case one does not (`passenger`, `tokens`).
# shortcut: the suffix is capped at 64 characters (possessive, so no backtracking) to stay linear on long words, upgrade if
# real key names are longer.
_KEYS = (r"(?:(?:pass(?:word|wd)(?:confirm(?:ation)?)?|secret(?:[_-]?(?:access[_-]?)?key)?|token|api[_-]?key)"
         r"|(?<![A-Za-z])(?:pass(?:phrase)?|pwd))(?:(?:[_-]|(?-i:[A-Z0-9]))[\w-]{0,64}+)?")
# An opening quote, also escaped (`\"` in JSON inside a string). An escaped quote of the inner JSON (`\\\"`) does not close it.
_QUOTED = r"""(?P<q>\\?["'])(?:\\\\\\.|(?!(?P=q))(?:\\.|[^\\\n]))*+(?P=q)?"""  # an unterminated quote runs to end of line
_VAL = r"""(?:"[^"\n]*"|[^\s,"'\[\]]+)"""  # stops at `]`, the end of a Go header list
# `key: v`, `"key": v`, `\"key\": v` and tuples `(b'key', b'v')`, then a bytes prefix.
_SEP = r"""(?:\\?["']?[ \t]*[:=]|\\?["'][ \t]*,)[ \t]*(?:b(?=["']))?"""
# A value that already starts with the marker (`[REDACTED]`, `["[REDACTED]"]`) is not taken, so redacting twice changes nothing.
_DONE = r"""(?!\[\\?["']?\[?REDACTED\])"""
# The separator, then a list (`Authorization:[Basic …]`, `{"Authorization":["…"]}`), redacted whole to its `]` so a second
# value goes too, or a tuple opener.
_OPEN = rf"""{_SEP}{_DONE}(?:(?P<l>\[)|\()?(?:b(?=["']))?"""
_LIST = r"""(?P<lq>\\?["'])?[^\]\n]*"""
# Authorization: an optional scheme word (any: Bearer, Token, ApiKey, AWS4-HMAC-SHA256, Digest, ...), then a token or key=value params
# joined by commas (SigV4, Digest), or a second credential (`Basic a, Basic b`). A quoted value is redacted whole. A prefixed key
# counts (`HTTP_AUTHORIZATION`, `proxy_authorization`).
_CRED = rf"""(?:[A-Za-z][\w-]*[ \t]+)?(?:[\w.-]+=)?{_VAL}"""
_AUTH = re.compile(rf"""(?P<k>{_B}authorization{_OPEN})(?(l){_LIST}|(?:{_QUOTED}|{_CRED}(?:,[ \t]*{_CRED})*))""", re.I)
# Pairs joined by `;` or `,` (headers merged into one line), a quoted value inside a pair, an Expires date with its comma.
_PAIR = r"""(?:expires=[^;\n]*|(?:[^\s;,"'\[\]]|"[^"\n]*"?)++)"""
_COOKIE = re.compile(rf"""(?P<k>{_B}(?:set-)?cookie{_OPEN})(?(l){_LIST}|(?:{_QUOTED}|{_PAIR}(?:[;,][ \t]*{_PAIR})*+))""", re.I)
# (pattern, replacement); order matters: Bearer before the generic key rule so `token: Bearer x` loses both words.
_RULES = [(re.compile(p, f), r) for p, f, r in [
    # A private key to its END line, or to the end of the text if cut short; spans lines (`\n` in JSON, or a multi-line event).
    (r"-----BEGIN [A-Z ]{0,32}PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]{0,32}PRIVATE KEY-----|\Z)", 0, "[REDACTED]"),
    (r"(\bbearer[ \t]+)[\w.~+/=-]+", re.I, r"\1[REDACTED]"),
    # Scheme is bounded and the password runs to the last `@` of the token, so `p@ss` is covered. Anchored on `://` to stay linear.
    # shortcut: passwords containing a raw "/" are not redacted (RFC 3986 requires percent-encoding, and allowing "/" would eat
    # `http://host:80/p?mail=a@b.c`), upgrade if real logs show them.
    (r"([a-z][a-z0-9+.-]{0,31}://[^\s:/@]*:)[^\s/]+(?=@)", re.I, r"\1[REDACTED]"),
    (_B + r"eyJ[\w-]+\.[\w-]+\.[\w-]+", 0, "[REDACTED]"),
    (_B + r"(?:AKIA[0-9A-Z]{16}|[sr]k_(?:live|test)_[A-Za-z0-9]{10,}|sk-[\w-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_\w{20,}"
          r"|glpat-[\w-]{20,}|AIza[\w-]{35}|xox[abeprs]-[\w-]+)", 0, "[REDACTED]"),
]]
# key=value, key: value, "key": "value" and "key": ["…"]; keeps key, separator and quotes, replaces only the value.
# No alternative overlaps another (bounded scheme above, `[^\\\n]` beside `\\.`), so long lines cannot backtrack badly.
_KV = re.compile(rf"""(?P<k>{_KEYS}{_OPEN})(?(l){_LIST}|(?:{_QUOTED}|[^\s,;&"']+))""", re.I)


def _keep_quotes(m: re.Match) -> str:
    q = m.groupdict().get("lq") or m["q"] or ""
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
    if not full:
        body = _cut(redact(body))  # redact before cutting, so a secret split by the cut cannot slip through
    http = [e.method, e.route, e.status, None if e.duration_ms is None else f"{round(e.duration_ms)}ms", e.func]
    parts = [_clock(e.ts, tz), f"{e.service:<6}", f"{LEVEL_NAMES[e.level]:<5}"]
    parts += [str(x) for x in http if x is not None] + [body] + ([f"trace={e.trace[:8]}"] if e.trace else [])
    line = " ".join(p for p in parts if p).rstrip()
    return redact("\n".join([line, *e.extra])) if full else redact(line)  # as one text, so a private key over lines goes whole


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
           project: str | None = None, below: int = 0) -> str:
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
    if below:  # matched every filter but the default level: a quiet `level>=warn` is not "nothing happened"
        parts.append(f"{below} more below {LEVEL_NAMES[level].lower()}")
    return "-- " + " · ".join(parts)
