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
        key, now = (e.container, e.level, _NUMS.sub("#", e.error or e.msg)), self.clock()
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


def run_follow(project: str, containers: list[Container], q: Query, tz: tzinfo | None, out: TextIO = sys.stdout,
               open_logs=docker.follow_logs, open_events=docker.events, clock=time.monotonic) -> None:
    """Print until every source ends, which real Docker never does: SIGTERM (see cli) ends it."""
    items: queue.Queue = queue.Queue()  # Events from the readers, formatted lines from the events thread
    procs, threads, groupers = [], [], []
    reading: set[str] = set()  # ids whose log stream is still open

    def spawn(target, *args):
        t = threading.Thread(target=target, args=args, daemon=True)
        threads.append(t)  # before start, so the exit check below never misses it
        t.start()

    def read(c: Container, proc, g: Grouper, lock: threading.Lock):
        for line in proc.stdout:
            try:
                ts, payload = split_docker_line(line.rstrip("\r\n"))
            except ValueError:  # Docker error text, merged from stderr
                continue
            with lock:
                for e in g.feed(ts, payload):
                    items.put(e)
        reading.discard(c.id)
        with lock:
            for e in g.flush():
                items.put(e)

    def attach(c: Container):
        if c.id in reading or (q.services and c.service not in q.services):
            return
        reading.add(c.id)
        procs.append(proc := open_logs(c))
        g, lock = Grouper(c.name, c.service, c.project, clock), threading.Lock()
        groupers.append((g, lock))
        spawn(read, c, proc, g, lock)

    def watch(proc):
        health: dict[str, str] = {}  # last health status seen per container id
        for line in proc.stdout:
            try:
                evt = json.loads(line)
            except ValueError:  # Docker error text, merged from stderr
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
                        attach(c)
                except docker.DockerUnreachable:  # the events stream ends too, nothing to attach to
                    pass

    def say(text: str):
        print(text, file=out, flush=True)

    services = ", ".join(sorted({c.service for c in containers}))
    say(redact(f"-- following {services} · level>={LEVEL_NAMES[q.level].lower()}"))
    col = Collapser(REPEAT_S, clock)
    try:
        for c in containers:
            attach(c)
        procs.append(ev_proc := open_events(project, project != "all" and all(c.working_dir is None for c in containers)))
        spawn(watch, ev_proc)
        while True:
            try:
                item = items.get(timeout=0.25)
            except queue.Empty:
                if not any(t.is_alive() for t in threads) and items.empty():
                    return
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
        for p in procs:
            p.terminate()
        for p in procs:
            p.wait()
