import subprocess
import pytest
from logq import jaeger
from logq.docker import DockerUnreachable
from logq.cli import main

def fake_docker(monkeypatch, replies):
    calls = []
    def run(*args):
        calls.append(list(args))
        rc, out, err = replies.get(args[0], (0, "", ""))
        return subprocess.CompletedProcess(args, rc, out, err)
    monkeypatch.setattr(jaeger, "_docker", run)
    return calls

def test_up_runs_missing_container(monkeypatch):
    calls = fake_docker(monkeypatch, {"inspect": (1, "", "Error: No such object: logq-jaeger")})
    jaeger.up(probe=lambda: True)
    assert calls[1] == ["run", "-d", "--name", "logq-jaeger", "-p", "127.0.0.1:16686:16686",
                        "-p", "127.0.0.1:4318:4318", jaeger.IMAGE]

def test_up_starts_stopped_and_skips_running(monkeypatch):
    calls = fake_docker(monkeypatch, {"inspect": (0, "exited\n", "")})
    jaeger.up(probe=lambda: True)
    assert calls[1] == ["start", "logq-jaeger"]
    calls = fake_docker(monkeypatch, {"inspect": (0, "running\n", "")})
    jaeger.up(probe=lambda: True)
    assert len(calls) == 1

def test_port_conflict_names_port(monkeypatch):
    fake_docker(monkeypatch, {"inspect": (1, "", "No such object"),
                              "run": (125, "", "Bind for 127.0.0.1:16686 failed: port is already allocated")})
    with pytest.raises(jaeger.JaegerError, match="port 16686 is already in use"):
        jaeger.up(probe=lambda: True)

def test_readiness_timeout(monkeypatch):
    fake_docker(monkeypatch, {"inspect": (0, "running\n", "")})
    t = iter(range(100))
    with pytest.raises(jaeger.JaegerError, match="did not answer on http://127.0.0.1:16686/ within 20s"):
        jaeger.up(probe=lambda: False, sleep=lambda s: None, clock=lambda: next(t))

def test_cli_ui_prints_urls_and_env(monkeypatch, capsys):
    monkeypatch.setattr(jaeger, "up", lambda: None)
    assert main(["ui"]) == 0
    out = capsys.readouterr().out
    assert jaeger.UI_URL in out and f"claude mcp add --transport http --scope user jaeger {jaeger.MCP_URL}" in out
    for line in ["OTEL_TRACES_EXPORTER=otlp", "OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf",
                 "OTEL_EXPORTER_OTLP_ENDPOINT=http://host.docker.internal:4318"]:
        assert line in out

def test_cli_ui_error_exit_1(monkeypatch, capsys):
    def boom():
        raise jaeger.JaegerError("port 16686 is already in use")
    monkeypatch.setattr(jaeger, "up", boom)
    assert main(["ui"]) == 1
    assert "port 16686 is already in use" in capsys.readouterr().err

def test_cli_ui_stop(monkeypatch):
    called = []
    monkeypatch.setattr(jaeger, "down", lambda: called.append(True))
    assert main(["ui", "--stop"]) == 0 and called

def test_unreachable_docker_exits_2(monkeypatch, capsys):
    fake_docker(monkeypatch, {"inspect": (1, "", "Cannot connect to the Docker daemon at unix:///x.sock")})
    assert main(["ui", "--status"]) == 2
    assert "is not reachable: Cannot connect to the Docker daemon" in capsys.readouterr().err

def test_down_removes_and_reports_unreachable(monkeypatch):
    calls = fake_docker(monkeypatch, {})
    jaeger.down()
    assert calls == [["rm", "-f", "logq-jaeger"]]
    fake_docker(monkeypatch, {"rm": (1, "", "Cannot connect to the Docker daemon")})
    with pytest.raises(DockerUnreachable):
        jaeger.down()
