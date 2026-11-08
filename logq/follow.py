"""`logq follow` (spec section 4.4): matching log events and container lifecycle events, live, one flushed line each."""
import json
import queue
import re
import sys
import threading
import time
from collections.abc import Callable
from datetime import tzinfo
from typing import TextIO

from logq import docker
from logq.docker import Container
from logq.filter import Query, matches
from logq.parse import LEVEL_NAMES, Event, Grouper, split_docker_line
from logq.render import format_docker_event, format_event, format_repeat, redact

REPEAT_S = 30
_NUMS = re.compile(r"0x[0-9a-fA-F]+|[0-9a-fA-F]{8,}|\d+")


class Collapser:
    """The first event of a repeat key prints; repeats within the window are only counted."""

    def __init__(self, window_s: float = 30.0, clock: Callable[[], float] = time.monotonic):
        self.window_s, self.clock = window_s, clock
        self._open: dict[tuple, list] = {}  # key -> [first event, window start, repeats]
        self._closed: list[list] = []

    def offer(self, e: Event) -> bool:
        key, now = (e.container, e.level, e.method, e.route, e.status, _NUMS.sub("#", e.error or e.msg)), self.clock()
        w = self._open.get(key)
        if w and now - w[1] < self.window_s:
            w[2] += 1
            return False
        if w:
            self._closed.append(w)  # closed before due() saw it, so its count is not lost
        self._open[key] = [e, now, 0]
        return True

    def due(self) -> list[tuple[Event, int]]:
        now = self.clock()
        self._closed += [self._open.pop(k) for k, w in list(self._open.items()) if now - w[1] >= self.window_s]
        done, self._closed = [(e, n) for e, _, n in self._closed if n], []
        return done

    def flush(self) -> list[tuple[Event, int, float]]:
        """At shutdown: every window with repeats, with the seconds it covered so far."""
        now, windows = self.clock(), self._closed + list(self._open.values())
        self._open, self._closed = {}, []
        return [(e, n, min(now - start, self.window_s)) for e, start, n in windows if n]


def _running(c: Container) -> bool:
    try:
        return any(x.state == "running" for x in docker.inspect([c.id]))
    except docker.DockerUnreachable:  # the events stream ends too and says so
        return False


def run_follow(project: str, containers: list[Container], q: Query, tz: tzinfo | None, out: TextIO = sys.stdout,
               open_logs=docker.follow_logs, open_events=docker.events, clock=time.monotonic,
               stop: threading.Event | None = None) -> int:
    """Print until `stop` is set (SIGTERM or Ctrl-C, see cli) or every source ends, which real Docker never does.
    Returns 2 if the docker events stream ended on its own, else 0."""
    stop = stop or threading.Event()
    items: queue.Queue = queue.Queue()  # Events from the readers, formatted lines from the events thread
    procs, threads, groupers = [], [], []
    attaching = threading.Lock()  # guards reading, deferred, stopping and appends to procs
    reading: set[str] = set()  # ids whose log stream is still open
    deferred: dict[str, Container] = {}  # restarted (same id) while the old reader was still open
    stopping = False  # set at shutdown, so no child is spawned after the snapshot of procs
    events_ended = False

    def spawn(target, *args):
        t = threading.Thread(target=target, args=args, daemon=True)
        threads.append(t)  # before start, so the exit check below never misses it
        t.start()

    def read(c: Container, proc, g: Grouper, lock: threading.Lock):
        last = None  # Docker's error text, merged from stderr
        for line in proc.stdout:
            try:
                ts, payload = split_docker_line(line.rstrip("\r\n"))
            except ValueError:
                last = line.strip() or last
                continue
            with lock:
                for e in g.feed(ts, payload):
                    items.put(e)
        with lock:
            for e in g.flush():
                items.put(e)
        proc.stdout.close()
        proc.wait()  # reap it, or every restart leaves a zombie and an open pipe
        if last and not (stopping or stop.is_set()) and _running(c):  # the stream died, not the container
            items.put(redact(f"! {c.name}: {last}"))
        with attaching:
            groupers.remove((g, lock))
            reading.discard(c.id)
            if nxt := deferred.pop(c.id, None):
                start(nxt, nxt.started_at)

    def attach(c: Container, since=None):
        if q.services and c.service not in q.services:
            return
        with attaching:
            if c.id in reading:
                deferred.setdefault(c.id, c)  # the earliest start, so --since covers every later run too
            else:
                start(c, since)

    def start(c: Container, since):  # caller holds `attaching`
        if stopping:
            return
        reading.add(c.id)
        procs.append(proc := open_logs(c, since=since))
        g, lock = Grouper(c.name, c.service, c.project, clock), threading.Lock()
        groupers.append((g, lock))
        spawn(read, c, proc, g, lock)

    def watch(proc):
        nonlocal events_ended
        health: dict[str, str] = {}  # last health status seen per container id
        last = None  # Docker's error text, merged from stderr
        for line in proc.stdout:
            try:
                evt = json.loads(line)
            except ValueError:
                last = line.strip() or last
                continue
            if not isinstance(evt, dict):
                continue
            action, cid = evt.get("Action", ""), evt.get("id") or evt.get("Actor", {}).get("ID")
            if action.startswith("health_status: "):
                status = action.removeprefix("health_status: ")
                prev, health[cid] = health.get(cid), status
                if not (status == "unhealthy" or (status, prev) == ("healthy", "unhealthy")):
                    continue
            if text := format_docker_event(evt, tz):
                items.put(text)
            if action == "start" and cid:
                try:
                    for c in docker.inspect([cid]):
                        attach(c, c.started_at)  # from its start, so lines printed before the reader attached show too
                except docker.DockerUnreachable:  # the events stream ends too, nothing to attach to
                    pass
        if not (stopping or stop.is_set()):  # without events no restart is seen, so say so loudly
            events_ended = True
            items.put(redact(f"! docker events ended: {last or 'stream closed'}"))

    def say(text: str):
        print(text, file=out, flush=True)

    services = ", ".join(sorted({c.service for c in containers}))
    say(redact(f"-- following {services} · level>={LEVEL_NAMES[q.level].lower()}"))
    col = Collapser(REPEAT_S, clock)
    try:
        for c in containers:
            attach(c)
        with attaching:
            procs.append(ev_proc := open_events(project, project != "all" and all(c.working_dir is None for c in containers)))
        spawn(watch, ev_proc)
        while not stop.is_set():  # the signal handlers only set `stop`: raising inside items.get() breaks its lock
            try:
                item = items.get(timeout=0.25)
            except queue.Empty:
                if not any(t.is_alive() for t in threads) and items.empty():
                    break
                item = None
            for e, n in col.due():
                say(format_repeat(e, n, REPEAT_S))
            if isinstance(item, str):
                say(item)
            elif item is not None and matches(item, q) and col.offer(item):
                say(format_event(item, tz))
            for g, lock in list(groupers):
                with lock:
                    for e in g.flush_stale():
                        items.put(e)
    finally:
        try:
            for e, n, s in col.flush():
                say(format_repeat(e, n, s))
        except BrokenPipeError:  # the reader is gone; the children must still stop
            pass
        with attaching:
            stopping = True
            children = list(procs)
        for p in children:
            p.terminate()
        for p in children:
            p.wait()
    return 2 if events_ended else 0
