"""`logq follow` through cli.main, with fake Docker sources that never end on their own (like `docker logs -f`).
tests/test_follow.py runs it as a child process and sends it SIGTERM or SIGINT. No Docker is touched."""
import functools
import sys
import threading

from logq import cli, docker, follow
from logq.docker import Container
from logq.follow import run_follow

API = Container("id1", "api-1", "p", "api", "/w/p", "running", None, 0, 0, None, None)
LINES = [f"2026-11-08T02:20:0{i}.0Z ERROR {m}" for i, m in enumerate(["boom", "boom", "boom", "ready", "end"])]


class Blocking:
    def __init__(self, lines):
        self.done = threading.Event()
        self.stdout = self._lines(lines)

    def _lines(self, lines):
        yield from (line + "\n" for line in lines)
        self.done.wait()  # no EOF until terminated

    def terminate(self):
        self.done.set()

    def wait(self):
        pass


docker.list_containers = lambda: [API]
follow.run_follow = functools.partial(run_follow, open_logs=lambda c, since=None: Blocking(LINES),
                                      open_events=lambda project, pseudo: Blocking([]))
sys.exit(cli.main(["follow", "-p", "p"]))
