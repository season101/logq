"""Docker access through the `docker` CLI only (spec sections 4.1, 4.3 and 10). The active context is used; never --context."""
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from logq.parse import split_docker_line

_PROJECT, _SERVICE, _WORKDIR = (f"com.docker.compose.{k}" for k in ("project", "service", "project.working_dir"))
_RELATIVE = re.compile(r"\d+[smh]")
_EPOCH = datetime.min.replace(tzinfo=timezone.utc)
_POPEN = dict(stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1)


@dataclass
class Container:
    id: str
    name: str
    project: str
    service: str
    working_dir: str | None
    state: str
    health: str | None
    exit_code: int
    restarts: int
    started_at: datetime | None
    finished_at: datetime | None


@dataclass
class LogRead:
    lines: list[str]
    capped: bool
    error: str | None


class DockerUnreachable(Exception):
    pass


class UnknownProject(Exception):
    def __init__(self, projects: list[str]):
        super().__init__(f"unknown project; running projects: {', '.join(projects)}")
        self.projects = projects


def _time(value: str) -> datetime | None:
    # Docker writes 0001-01-01T00:00:00Z for a time that was never set
    return None if value.startswith("0001-01-01") else datetime.fromisoformat(value)


def containers_from_inspect(data: list[dict]) -> list[Container]:
    out = []
    for d in data:
        labels = d["Config"].get("Labels") or {}
        state = d["State"]
        name = d["Name"].removeprefix("/")
        out.append(Container(
            d["Id"], name,
            labels.get(_PROJECT, name),  # no compose label: a pseudo-project named after the container
            labels.get(_SERVICE, name),
            labels.get(_WORKDIR),
            state["Status"], state.get("Health", {}).get("Status"), state["ExitCode"], d["RestartCount"],
            _time(state["StartedAt"]), _time(state["FinishedAt"])))
    return out


def _unreachable(detail: str) -> DockerUnreachable:
    try:
        context = subprocess.run(["docker", "context", "show"], capture_output=True, text=True).stdout.strip()
    except OSError:
        context = ""
    return DockerUnreachable(f'docker context "{context or "default"}" is not reachable: {detail}')


def _docker(*args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["docker", *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    except FileNotFoundError:
        raise _unreachable("docker CLI not found") from None


def _first_line(text: str) -> str:
    return (text.strip().splitlines() or [""])[0]


def inspect(ids: list[str]) -> list[Container]:
    r = _docker("inspect", "--type", "container", *ids)
    # a container removed since `docker ps` makes the exit non-zero but the rest is still printed
    if r.returncode and not r.stdout.strip():
        raise _unreachable(_first_line(r.stderr))
    return containers_from_inspect(json.loads(r.stdout))


def list_containers() -> list[Container]:
    r = _docker("ps", "-a", "-q")
    if r.returncode:
        raise _unreachable(_first_line(r.stderr))
    ids = r.stdout.split()
    return inspect(ids) if ids else []


def select_project(containers: list[Container], project: str | None, cwd: Path) -> tuple[str, list[Container]]:
    if project == "all":
        return "all", list(containers)
    if project is None:
        # the project whose working_dir is cwd or a parent of it, deepest first
        near = [c for c in containers if c.working_dir and Path(c.working_dir) in (cwd, *cwd.parents)]
        if near:
            deepest = max(len(Path(c.working_dir).parts) for c in near)
            here = [c for c in near if len(Path(c.working_dir).parts) == deepest]
            # projects can share a folder: prefer one with a running container, then the most recently started
            project = max(here, key=lambda c: (c.state == "running", c.started_at or _EPOCH)).project
            if others := sorted({c.project for c in here} - {project}):
                print(f"logq: also in this folder: {', '.join(others)}; use -p to pick", file=sys.stderr)
    chosen = [c for c in containers if c.project == project]
    if not chosen:
        raise UnknownProject(sorted({c.project for c in containers}))
    return project, chosen


def parse_since(value: str) -> str:
    if not _RELATIVE.fullmatch(value):
        datetime.fromisoformat(value)  # raises ValueError
    return value


def read_logs(c: Container, since: str, until: str | None, cap: int = 50000) -> LogRead:
    cmd = ["docker", "logs", "--timestamps", "--since", since, *(["--until", until] if until else []), "--tail", str(cap), c.id]
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    lines = r.stdout.removesuffix("\n").split("\n") if r.stdout else []
    error = None
    if r.returncode:
        kept = []
        for line in lines:
            try:
                split_docker_line(line)
                kept.append(line)
            except ValueError:
                error = error or line
        lines, error = kept, error or f"docker logs exited with code {r.returncode}"
    return LogRead(lines, len(lines) == cap, error)


def follow_logs(c: Container, since: datetime | None = None) -> subprocess.Popen:
    """New lines only, or with `since` everything from then on (a reader attached after `start` must not miss a crash)."""
    start = ["--since", since.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")] if since else ["--tail", "0"]
    return subprocess.Popen(["docker", "logs", "-f", "--timestamps", *start, c.id], **_POPEN)


def events(project: str, pseudo: bool) -> subprocess.Popen:
    cmd = ["docker", "events", "--format", "{{json .}}", "--filter", "type=container"]
    if pseudo:
        cmd += ["--filter", f"container={project}"]
    elif project != "all":
        cmd += ["--filter", f"label={_PROJECT}={project}"]
    return subprocess.Popen(cmd, **_POPEN)
