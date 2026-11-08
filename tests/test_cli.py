import io
import os
import sys
import time
from datetime import datetime, timezone

import pytest

from logq import cli, render
from logq.cli import main
from logq.docker import DockerUnreachable
from logq.parse import Event


def test_query_prints_alerts_events_footer(fake_docker, capsys):
    assert main(["query", "-p", "p", "--since", "15m"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("! web-1 exited(1)")
    assert [l.split()[2] for l in out[1:-1]] == ["WARN", "WARN", "ERROR", "ERROR"]
    assert out[-1] == "-- 4 of 4 matches · 2 containers (api, web) · project p · 15m · level>=warn · 2 more below warn"


def test_no_below_hint_when_level_is_given(fake_docker, capsys):
    assert main(["query", "-p", "p", "-l", "warn"]) == 0
    assert capsys.readouterr().out.splitlines()[-1] == "-- 4 of 4 matches · 2 containers (api, web) · project p · 15m · level>=warn"


def test_jaeger_link_when_running(fake_docker_trace, monkeypatch, capsys):
    monkeypatch.setattr("logq.jaeger.status", lambda: "running")
    assert main(["query", "-p", "p", "--trace", "7f3a9c21"]) == 0
    assert capsys.readouterr().out.splitlines()[-1] == \
        "-- view in Jaeger: http://localhost:16686/trace/7f3a9c21aabbccddeeff001122334455"


def test_no_link_without_jaeger(fake_docker_trace, monkeypatch, capsys):
    monkeypatch.setattr("logq.jaeger.status", lambda: None)
    main(["query", "-p", "p", "--trace", "7f3a9c21"])
    assert "view in Jaeger" not in capsys.readouterr().out


def test_no_link_when_jaeger_status_unreachable(fake_docker_trace, monkeypatch, capsys):
    def unreachable():
        raise DockerUnreachable("down")
    monkeypatch.setattr("logq.jaeger.status", unreachable)
    assert main(["query", "-p", "p", "--trace", "7f3a9c21"]) == 0
    assert "view in Jaeger" not in capsys.readouterr().out


def test_no_status_call_without_trace_flag(fake_docker_trace, monkeypatch):
    def boom():
        raise AssertionError("jaeger.status called")
    monkeypatch.setattr("logq.jaeger.status", boom)
    assert main(["query", "-p", "p"]) == 0


def test_limit_keeps_most_recent(fake_docker_lines, capsys):
    main(["query", "-p", "p", "-n", "50"])
    out = capsys.readouterr().out.splitlines()
    assert out[0].endswith("ERROR n=10") and out[-2].endswith("ERROR n=59")
    assert out[-1].startswith("-- 50 of 60 matches (oldest dropped)")


def test_read_error_reported_and_others_continue(fake_docker_read_error, capsys):
    assert main(["query", "-p", "p"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert "! db-1: Error response from daemon: No such container" in out
    assert any(l.endswith("ERROR db pool exhausted") for l in out)


def test_unknown_project_exit_1(fake_docker, capsys):
    assert main(["query", "-p", "nope"]) == 1
    assert capsys.readouterr().err.splitlines() == ["unknown project; running projects:", "p"]


def test_docker_unreachable_exit_2(monkeypatch, capsys):
    def unreachable():
        raise DockerUnreachable('docker context "desktop-linux" is not reachable: x')
    monkeypatch.setattr("logq.docker.list_containers", unreachable)
    assert main(["ps"]) == 2
    assert 'docker context "desktop-linux" is not reachable' in capsys.readouterr().err


def test_short_trace_is_usage_error(fake_docker):
    assert main(["query", "-p", "p", "--trace", "abc"]) == 1


@pytest.mark.parametrize("argv", [
    ["query", "--level", "loud"], ["query", "--since", "2d"], ["query", "--until", "ten"], ["query", "--status", "99"],
    ["query", "--grep", "("], ["query", "--limit", "0"], ["query", "--limit", "x"], ["nope"], [],
])
def test_usage_errors_exit_1(fake_docker, capsys, argv):
    assert main(argv) == 1
    assert capsys.readouterr().err


def test_service_filter_reads_only_selected_but_alerts_on_all(fake_docker, capsys):
    read_calls = fake_docker
    assert main(["query", "-p", "p", "-s", "api"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert read_calls == ["api-1"]
    assert out[0].startswith("! web-1 exited(1)")
    assert out[-1] == "-- 4 of 4 matches · 1 container (api) · project p · 15m · level>=warn · 2 more below warn"


def test_unknown_service_exit_1_before_reading(fake_docker, capsys):
    read_calls = fake_docker
    assert main(["query", "-p", "p", "-s", "apii"]) == 1
    assert capsys.readouterr().err.splitlines() == ["unknown service: apii; services in p: api, web"]
    assert read_calls == []


@pytest.fixture
def chicago():
    old = os.environ.get("TZ")
    os.environ["TZ"] = "America/Chicago"
    time.tzset()
    yield
    os.environ.pop("TZ") if old is None else os.environ.update(TZ=old)
    time.tzset()


@pytest.mark.skipif(not hasattr(time, "tzset"), reason="needs time.tzset")
@pytest.mark.parametrize("ts, shown", [("2026-10-31T20:00:00", "15:00:00.000"), ("2026-11-08T18:00:00", "12:00:00.000")])
def test_local_zone_follows_dst(chicago, ts, shown):
    assert cli.TZ is None
    e = Event(datetime.fromisoformat(ts).replace(tzinfo=timezone.utc), "api-1", "api", "p", 40, "boom")
    assert render.format_event(e, cli.TZ).startswith(shown)


def test_ps_rows(fake_docker, capsys):
    main(["ps"])
    rows = [l.split() for l in capsys.readouterr().out.splitlines()]
    assert rows[0][:5] == ["p", "api", "api-1", "running", "-"]
    assert rows[1][0] == "!" and rows[1][4].startswith("exited")


class _BrokenStdout(io.StringIO):
    def __init__(self, fd, broken):
        super().__init__()
        self.fd, self.broken = fd, broken

    def write(self, s):
        if self.broken == "write":
            raise BrokenPipeError
        return super().write(s)

    def flush(self):  # a short output sits in the buffer until the flush, so the pipe breaks there
        if self.broken == "flush":
            raise BrokenPipeError

    def fileno(self):
        return self.fd


@pytest.mark.parametrize("broken", ["write", "flush"])
def test_broken_pipe_exits_quietly(fake_docker, capsys, tmp_path, broken):
    fd = os.open(tmp_path / "out", os.O_WRONLY | os.O_CREAT)
    old, sys.stdout = sys.stdout, _BrokenStdout(fd, broken)  # swapped by hand: monkeypatch would restore it after capsys
    try:
        rc = main(["query", "-p", "p"])
        quiet = os.path.samestat(os.fstat(fd), os.stat(os.devnull))  # so the flush at interpreter exit cannot fail
    finally:
        sys.stdout = old
        os.close(fd)
    assert rc == 0 and quiet
    assert capsys.readouterr().err == ""


def test_follow_unknown_service_exit_1(fake_docker, capsys):
    assert main(["follow", "-p", "p", "-s", "apii"]) == 1
    assert capsys.readouterr().err.splitlines() == ["unknown service: apii; services in p: api, web"]


@pytest.mark.parametrize("flag", [["--status", "5xx"], ["--route", "/api"], ["--method", "POST"], ["--func", "create"]])
def test_field_filter_without_level_reads_all_levels(fake_docker, capsys, flag):
    assert main(["query", "-p", "p", *flag]) == 0
    assert "level>=debug" in capsys.readouterr().out.splitlines()[-1]
    assert main(["query", "-p", "p", *flag, "-l", "warn"]) == 0
    assert "level>=warn" in capsys.readouterr().out.splitlines()[-1]


def test_follow_reads_selected_services(fake_docker, monkeypatch):
    calls = []
    monkeypatch.setattr("signal.signal", lambda *a: None)
    monkeypatch.setattr("logq.follow.run_follow", lambda project, containers, q, tz, out, stop: calls.append((project, [c.name for c in containers], q.level)) or 0)
    assert main(["follow", "-p", "p", "-s", "api"]) == 0
    assert calls == [("p", ["api-1"], 30)]


def test_follow_exit_code_comes_from_run_follow(fake_docker, monkeypatch):
    monkeypatch.setattr("signal.signal", lambda *a: None)
    monkeypatch.setattr("logq.follow.run_follow", lambda *a, **kw: 2)  # the docker events stream ended
    assert main(["follow", "-p", "p"]) == 2
