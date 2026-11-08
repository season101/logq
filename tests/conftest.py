from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from logq.docker import Container, LogRead

FIX = Path(__file__).parent / "fixtures"


def _container(name, service, state="running", exit_code=0, finished_ago=None):
    now = datetime.now(timezone.utc)
    finished = now - timedelta(seconds=finished_ago) if finished_ago else None
    return Container(name, name, "p", service, "/w/p", state, None, exit_code, 0, now - timedelta(minutes=7), finished)


def _install(monkeypatch, containers, reads):
    """Never reach real Docker: stub discovery and log reads, pin the zone to UTC and the cwd to /w/p."""
    monkeypatch.setattr("logq.docker.list_containers", lambda: containers)
    monkeypatch.setattr("logq.docker.read_logs", lambda c, since, until, cap=50000: reads[c.name])
    monkeypatch.setattr("logq.cli.TZ", timezone.utc)
    monkeypatch.setattr(Path, "cwd", classmethod(lambda cls: Path("/w/p")))


@pytest.fixture
def fake_docker(monkeypatch):
    api, web = _container("api-1", "api"), _container("web-1", "web", "exited", 1, finished_ago=40)
    reads = {"api-1": LogRead(FIX.joinpath("pilot_api.log").read_text().splitlines(), False, None), "web-1": LogRead([], False, None)}
    _install(monkeypatch, [api, web], reads)


@pytest.fixture
def fake_docker_lines(monkeypatch):
    lines = [f"2026-11-08T02:20:{i:02d}.0Z ERROR n={i}" for i in range(60)]
    _install(monkeypatch, [_container("api-1", "api")], {"api-1": LogRead(lines, False, None)})


@pytest.fixture
def fake_docker_read_error(monkeypatch):
    api, web = _container("api-1", "api"), _container("web-1", "web", "exited", 1, finished_ago=40)
    reads = {
        "api-1": LogRead(FIX.joinpath("pilot_api.log").read_text().splitlines(), False, None),
        "web-1": LogRead([], False, None),
        "db-1": LogRead([], False, "Error response from daemon: No such container"),
    }
    _install(monkeypatch, [api, web, _container("db-1", "db")], reads)
