"""Command line entry point: `ps`, `query` and `follow` (spec section 4)."""
import argparse
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from logq import docker, filter as flt, parse, render

TZ = datetime.now().astimezone().tzinfo  # tests override this


class _Parser(argparse.ArgumentParser):
    def exit(self, status=0, message=None):
        super().exit(1 if status else 0, message)  # exit code 2 is reserved for "Docker unreachable"


def _selection_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("-p", "--project")
    p.add_argument("-s", "--service", action="append")
    p.add_argument("-t", "--trace")
    p.add_argument("-l", "--level")
    p.add_argument("--route")
    p.add_argument("--method")
    p.add_argument("--status")
    p.add_argument("--func")
    p.add_argument("-g", "--grep")


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="logq", description="Filtered, redacted Docker container logs.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    ps = sub.add_parser("ps", help="list containers")
    ps.add_argument("-p", "--project")
    ps.set_defaults(run=_ps)
    q = sub.add_parser("query", help="print matching events from the recent past")
    _selection_args(q)
    q.add_argument("--since", default="15m")
    q.add_argument("--until")
    q.add_argument("-n", "--limit", type=int, default=50)
    q.add_argument("--full", action="store_true")
    q.set_defaults(run=_query)
    f = sub.add_parser("follow", help="stream matching events live")
    _selection_args(f)
    f.set_defaults(run=_follow)
    return parser


def _build_query(args) -> flt.Query:
    """Validate the filter flags; raises ValueError or re.error with a message fit for stderr."""
    if args.trace and len(args.trace) < 8:
        raise ValueError("--trace needs at least 8 characters")
    level = flt.parse_level(args.level) if args.level else flt.default_level(args.trace)
    return flt.Query(args.service or [], args.trace, level, args.route, args.method, args.status, args.func,
                     re.compile(args.grep) if args.grep else None)


def _check_window(args) -> None:
    if args.limit < 1:
        raise ValueError("--limit must be at least 1")
    for flag in ("since", "until"):
        value = getattr(args, flag)
        if value:
            try:
                docker.parse_since(value)
            except ValueError:
                raise ValueError(f"bad --{flag} {value!r}, use 10m, 2h or an ISO timestamp") from None


def _ps(args) -> int:
    containers = docker.list_containers()
    if args.project:
        containers = docker.select_project(containers, args.project, Path.cwd())[1]
    now = datetime.now(timezone.utc)
    rows, marks = [], []
    for c in sorted(containers, key=lambda c: (c.project, c.service, c.name)):
        state = f"{c.state}({c.exit_code})" if c.state == "exited" else c.state
        if c.state == "running" and c.started_at:
            when = f"up {render.ago(now - c.started_at)}"
        elif c.state != "running" and c.finished_at:
            when = f"{render.ago(now - c.finished_at)} ago"
        else:
            when = "-"
        mark = "! " if render.format_container_alert(c, now) else "  "  # two characters, so the columns stay aligned
        rows.append([c.project, c.service, c.name, state, c.health or "-", when, f"restarts={c.restarts}"])
        marks.append(mark)
    widths = [max(map(len, col)) for col in zip(*rows)]
    for mark, r in zip(marks, rows):
        print(mark + "  ".join(v.ljust(w) for v, w in zip(r, widths)).rstrip())
    return 0


def _query(args) -> int:
    try:
        q = _build_query(args)
        _check_window(args)
    except (ValueError, re.error) as e:
        print(f"logq: {e}", file=sys.stderr)
        return 1
    _, selected = docker.select_project(docker.list_containers(), args.project, Path.cwd())
    with ThreadPoolExecutor(max_workers=8) as pool:
        reads = list(pool.map(lambda c: docker.read_logs(c, args.since, args.until), selected))
    now = datetime.now(timezone.utc)
    alerts = [a for c in selected if (a := render.format_container_alert(c, now))]
    alerts += [render.redact(f"! {c.name}: {r.error}") for c, r in zip(selected, reads) if r.error]
    events = [e for c, r in zip(selected, reads) for e in parse.parse_stream(r.lines, c.name, c.service, c.project) if flt.matches(e, q)]
    events.sort(key=lambda e: e.ts)  # stable: equal timestamps keep their per-container order
    shown = events[-args.limit:]
    window = args.since + (f"..{args.until}" if args.until else "")
    capped = [c.name for c, r in zip(selected, reads) if r.capped]
    lines = alerts + [render.format_event(e, TZ, args.full) for e in shown]
    lines.append(render.footer(len(shown), len(events), [c.service for c in selected], window, q.level, args.trace, capped))
    print("\n".join(lines))
    return 0


def _follow(args) -> int:
    print("follow: not implemented yet", file=sys.stderr)  # Task 7
    return 1


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as e:  # argparse usage error (already printed) or --help
        return e.code
    try:
        return args.run(args)
    except docker.UnknownProject as e:
        print("unknown project; running projects:", *e.projects, sep="\n", file=sys.stderr)
        return 1
    except docker.DockerUnreachable as e:
        print(e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
