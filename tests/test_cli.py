import pytest

from logq.cli import main
from logq.docker import DockerUnreachable


def test_query_prints_alerts_events_footer(fake_docker, capsys):
    assert main(["query", "-p", "p", "--since", "15m"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("! web-1 exited(1)")
    assert [l.split()[2] for l in out[1:-1]] == ["WARN", "WARN", "ERROR", "ERROR"]
    assert out[-1] == "-- 4 of 4 matches · 2 containers (api, web) · 15m · level>=warn"


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


def test_ps_rows(fake_docker, capsys):
    main(["ps"])
    rows = [l.split() for l in capsys.readouterr().out.splitlines()]
    assert rows[0][:5] == ["p", "api", "api-1", "running", "-"]
    assert rows[1][0] == "!" and rows[1][4].startswith("exited")
