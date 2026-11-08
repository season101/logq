import io
import json
import threading
from datetime import datetime, timezone

from logq.docker import Container
from logq.filter import Query
from logq.follow import Collapser, run_follow
from logq.parse import Event, Grouper, split_docker_line

UTC = timezone.utc
T = datetime(2026, 11, 8, 18, 4, 31, 220000, tzinfo=UTC)
API = Container("id1", "api-1", "p", "api", "/w/p", "running", None, 0, 0, None, None)
STARTED = datetime(2026, 11, 8, 2, 20, 8, 500000, tzinfo=UTC)


def ev(**kw):
    return Event(**{**dict(ts=T, container="api-1", service="api", project="p", level=20, msg="m"), **kw})


class FakeProc:
    def __init__(self, lines):
        self.stdout = (line + "\n" for line in lines)
        self.terminated = self.waited = False

    def terminate(self):
        self.terminated = True

    def wait(self):
        self.waited = True


def docker_event(action, cid="id1", service="api"):
    return json.dumps({"Action": action, "id": cid, "timeNano": 1762625402114000000,
                       "Actor": {"ID": cid, "Attributes": {"com.docker.compose.service": service}}})


def test_collapser_window():
    now = [0.0]
    col = Collapser(30, clock=lambda: now[0])
    e = ev(level=40, error="KeyError: 'sku'")
    assert col.offer(e) is True
    for i in range(39):
        now[0] = i * 0.25
        assert col.offer(e) is False
    now[0] = 31
    assert col.due() == [(e, 39)]
    assert col.offer(e) is True

def test_collapser_key_ignores_numbers_and_ids():
    col = Collapser(30, clock=lambda: 0.0)
    assert col.offer(ev(msg="retry 1 of 5 id=7f3a9c21aa")) is True
    assert col.offer(ev(msg="retry 2 of 5 id=99bb00cc11")) is False

def test_collapser_key_includes_http_fields():
    col = Collapser(30, clock=lambda: 0.0)
    assert col.offer(ev(msg="request finished", method="POST", route="/api/orders", status=500)) is True
    assert col.offer(ev(msg="request finished", method="POST", route="/api/orders", status=200)) is True
    assert col.offer(ev(msg="request finished", method="GET", route="/api/orders", status=500)) is True
    assert col.offer(ev(msg="request finished", method="POST", route="/api/users", status=500)) is True
    assert col.offer(ev(msg="request finished", method="POST", route="/api/orders", status=500)) is False

def test_collapser_keeps_count_of_window_closed_before_due():
    now = [0.0]
    col = Collapser(30, clock=lambda: now[0])
    e = ev(level=40, msg="boom")
    col.offer(e); col.offer(e)
    now[0] = 31
    assert col.offer(e) is True  # a new window opens before due() ran
    assert col.due() == [(e, 1)]

def test_flush_stale():
    now = [0.0]
    g = Grouper("c", "s", "p", clock=lambda: now[0])
    g.feed(*split_docker_line("2026-11-08T02:20:07.0Z ERROR boom"))
    now[0] = 0.4; assert g.flush_stale() == []
    now[0] = 0.6; assert [e.msg for e in g.flush_stale()] == ["ERROR boom"]

def test_run_follow_with_fake_sources():
    logs = {"api-1": ["2026-11-08T02:20:07.0Z INFO ok", "2026-11-08T02:20:08.0Z ERROR boom"]}
    evts = ['{"Action":"die","timeNano":1762625402114000000,"Actor":{"Attributes":{"com.docker.compose.service":"api","exitCode":"1"}}}']
    out = io.StringIO()
    run_follow("p", [API], Query(), UTC, out=out,
               open_logs=lambda c, since=None: FakeProc(logs[c.name]), open_events=lambda p, pseudo: FakeProc(evts))
    text = out.getvalue()
    assert text.splitlines()[0] == "-- following api · level>=warn"
    assert "ERROR boom" in text and "! api died exit=1" in text and "INFO ok" not in text

def test_run_follow_attaches_recreated_container(monkeypatch):
    new = Container("id2", "api-2", "p", "api", "/w/p", "running", None, 0, 0, None, None)
    monkeypatch.setattr("logq.docker.inspect", lambda ids: [new] if ids == ["id2"] else [])
    evts = ['{"Action":"start","id":"id2","timeNano":1762625402114000000,"Actor":{"ID":"id2","Attributes":{"com.docker.compose.service":"api"}}}']
    logs = {"api-1": [], "api-2": ["2026-11-08T02:20:09.0Z ERROR after recreate"]}
    out = io.StringIO()
    run_follow("p", [API], Query(), UTC, out=out,
               open_logs=lambda c, since=None: FakeProc(logs[c.name]), open_events=lambda p, pseudo: FakeProc(evts))
    assert "! api started" in out.getvalue() and "ERROR after recreate" in out.getvalue()

def test_health_prints_only_changes_to_or_from_unhealthy():
    evts = ["Error response from daemon: not json", "[1, 2]"]  # stderr text and non-object JSON are skipped
    evts += [docker_event(f"health_status: {s}") for s in ("healthy", "unhealthy", "unhealthy", "healthy", "healthy")]
    evts.append(docker_event("health_status: healthy", cid="id9", service="db"))
    out = io.StringIO()
    run_follow("p", [API], Query(), UTC, out=out, open_logs=lambda c, since=None: FakeProc([]), open_events=lambda p, pseudo: FakeProc(evts))
    assert [line.split(" ", 1)[1] for line in out.getvalue().splitlines()[1:]] == [
        "! api health: unhealthy", "! api health: unhealthy", "! api health: healthy"]

def test_start_attaches_only_selected_services(monkeypatch):
    web = Container("id3", "web-1", "p", "web", "/w/p", "running", None, 0, 0, None, None)
    monkeypatch.setattr("logq.docker.inspect", lambda ids: [web])
    opened, out = [], io.StringIO()

    def open_logs(c, since=None):
        opened.append(c.name)
        return FakeProc([])

    run_follow("p", [API], Query(services=["api"]), UTC, out=out, open_logs=open_logs,
               open_events=lambda p, pseudo: FakeProc([docker_event("start", "id3", "web")]))
    assert opened == ["api-1"] and "! web started" in out.getvalue()

def test_restart_while_reader_runs_attaches_after_it_ends(monkeypatch):
    restarted = Container("id1", "api-1", "p", "api", "/w/p", "running", None, 0, 0, STARTED, None)  # a restart keeps the id
    monkeypatch.setattr("logq.docker.inspect", lambda ids: [restarted])
    release, procs, since_seen = threading.Event(), [], []

    def held():  # the old reader has not reached EOF when the start events arrive
        release.wait(5)
        yield "2026-11-08T02:20:07.0Z ERROR before restart"

    def events():
        yield docker_event("start", "id1")
        yield docker_event("start", "id1")  # a second start while deferred adds no third reader
        release.set()  # runs once both start lines have been handled

    def spawn(lines):
        procs.append(FakeProc(lines))
        return procs[-1]

    def open_logs(c, since=None):
        since_seen.append(since)
        return spawn(held() if since is None else ["2026-11-08T02:20:09.0Z ERROR after restart"])

    out = io.StringIO()
    run_follow("p", [API], Query(), UTC, out=out, open_logs=open_logs, open_events=lambda p, pseudo: spawn(events()))
    assert since_seen == [None, STARTED]
    assert "ERROR before restart" in out.getvalue() and "ERROR after restart" in out.getvalue()
    assert len(procs) == 3 and all(p.terminated and p.waited for p in procs)  # api-1, events, api-1 again

def test_mid_run_attach_reads_since_container_start(monkeypatch):
    new = Container("id2", "api-2", "p", "api", "/w/p", "running", None, 0, 0, STARTED, None)
    monkeypatch.setattr("logq.docker.inspect", lambda ids: [new])
    opened = []

    def open_logs(c, since=None):
        opened.append((c.name, since))
        return FakeProc([])

    run_follow("p", [API], Query(), UTC, out=io.StringIO(), open_logs=open_logs,
               open_events=lambda p, pseudo: FakeProc([docker_event("start", "id2")]))
    assert opened == [("api-1", None), ("api-2", STARTED)]
