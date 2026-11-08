import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import pytest
from logq.docker import Container, UnknownProject, containers_from_inspect, follow_logs, select_project, parse_since
FIX = Path(__file__).parent / "fixtures"

def test_containers_from_inspect():
    api, pg = containers_from_inspect(json.loads(FIX.joinpath("inspect.json").read_text()))
    assert (api.name, api.project, api.service, api.working_dir, api.state, api.health) == (
        "para-dashboard-app-v01-api-1", "para-dashboard-app-v01", "api", "/home/u/para", "running", None)
    assert (pg.project, pg.service, pg.state, pg.exit_code, pg.started_at) == ("chat-pr1-pg", "chat-pr1-pg", "exited", 137, None)
    assert api.started_at == datetime(2026, 11, 8, 2, 11, 3, 123456, tzinfo=timezone.utc) and api.finished_at is None
    assert pg.finished_at == datetime(2026, 11, 8, 2, 18, 0, 500000, tzinfo=timezone.utc) and pg.working_dir is None

def c(name, project, wd):
    return Container(name, name, project, name, wd, "running", None, 0, 0, None, None)

def test_select_project_deepest_working_dir():
    cs = [c("a-1", "a", "/w/a"), c("b-1", "b", "/w/a/b")]
    assert select_project(cs, None, Path("/w/a/b/src")) == ("b", [cs[1]])

def test_select_project_explicit_all_and_unknown():
    cs = [c("a-1", "a", "/w/a"), c("b-1", "b", "/w/b")]
    assert select_project(cs, "a", Path("/")) == ("a", [cs[0]])
    assert select_project(cs, "all", Path("/"))[1] == cs
    with pytest.raises(UnknownProject) as err:
        select_project(cs, None, Path("/elsewhere"))
    assert err.value.projects == ["a", "b"]

@pytest.mark.parametrize("ok", ["10m", "2h", "30s", "2026-11-08T02:00:00"])
def test_parse_since_ok(ok):
    assert parse_since(ok) == ok

@pytest.mark.parametrize("bad", ["2d", "ten", ""])
def test_parse_since_bad(bad):
    with pytest.raises(ValueError):
        parse_since(bad)

def test_follow_logs_args(monkeypatch):
    argv = []
    monkeypatch.setattr("subprocess.Popen", lambda cmd, **kw: argv.append(cmd))
    follow_logs(c("api-1", "p", "/w/p"))
    follow_logs(c("api-1", "p", "/w/p"), since=datetime(2026, 11, 8, 12, 0, 0, 123456, tzinfo=ZoneInfo("America/Chicago")))
    assert argv == [["docker", "logs", "-f", "--timestamps", "--tail", "0", "api-1"],
                    ["docker", "logs", "-f", "--timestamps", "--since", "2026-11-08T18:00:00.123456Z", "api-1"]]


def at(name, project, state, started_h):
    return Container(name, name, project, name, "/w/t", state, None, 0, 0, datetime(2026, 11, 8, started_h, tzinfo=timezone.utc), None)

def test_shared_working_dir_prefers_running_then_newest(capsys):
    old, verify, walk = at("old-1", "old", "running", 1), at("verify-1", "verify", "exited", 9), at("walk-1", "walk", "running", 5)
    assert select_project([old, verify, walk], None, Path("/w/t"))[0] == "walk"
    assert capsys.readouterr().err == "logq: also in this folder: old, verify; use -p to pick\n"
    assert select_project([verify, old], None, Path("/w/t"))[0] == "old"
    select_project([old], None, Path("/w/t"))
    assert capsys.readouterr().err == "logq: also in this folder: verify; use -p to pick\n"  # a lone project adds no note
