"""Event filters, spec section 4.3. Field filters exclude events that lack the field."""
import re
from dataclasses import dataclass, field

from logq.parse import LEVELS, Event

_STATUS = re.compile(r"\d{3}|\dxx", re.IGNORECASE)


@dataclass
class Query:
    services: list[str] = field(default_factory=list)
    trace: str | None = None
    level: int = 30
    route: str | None = None
    method: str | None = None
    status: str | None = None  # "500" or a class like "5xx"
    func: str | None = None
    grep: re.Pattern | None = None

    def __post_init__(self):
        if self.status is not None and not _STATUS.fullmatch(self.status):
            raise ValueError(f"bad status filter {self.status!r}, use 500 or 5xx")


def default_level(*filters: str | None) -> int:
    """`debug` when --trace or a field filter is given (they target request lines, which are INFO), else `warn`."""
    return 10 if any(filters) else 30


def parse_level(name: str) -> int:
    try:
        return LEVELS[name.lower()]
    except KeyError:
        raise ValueError(f"unknown level {name!r}, use one of: {', '.join(LEVELS)}") from None


def matches(e: Event, q: Query) -> bool:
    if e.level < q.level or (q.services and e.service not in q.services):
        return False
    if q.trace:
        t = q.trace.lower()
        # JSON events carry the ID in `trace`; plain-text lines (Traefik, nginx) only in the raw text
        if not (e.trace.lower().startswith(t) if e.trace else t in e.raw.lower()):
            return False
    if q.route and not (e.route and q.route in e.route):
        return False
    if q.method and not (e.method and e.method.lower() == q.method.lower()):
        return False
    if q.func and not (e.func and q.func in e.func):
        return False
    if q.status:
        s = q.status.lower()
        if e.status is None or (e.status // 100 != int(s[0]) if s.endswith("xx") else e.status != int(s)):
            return False
    if q.grep and not any(q.grep.search(t) for t in (e.msg, e.error or "", *e.extra)):
        return False
    return True
