"""The shared local Jaeger container behind `logq ui` (spec section 9a). Docker access through the CLI only."""
import http.client
import re
import subprocess
import time
import urllib.request
from collections.abc import Callable

from logq.docker import _first_line, _unreachable

NAME = "logq-jaeger"
IMAGE = "cr.jaegertracing.io/jaegertracing/jaeger:2.23.0"
UI_URL = "http://localhost:16686"
MCP_URL = "http://localhost:16686/api/ai/mcp/"
_PROBE_URL = "http://127.0.0.1:16686/"
_PORT_TAKEN = re.compile(r"already allocated|address already in use")


class JaegerError(Exception):
    pass


def _docker(*args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["docker", *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    except FileNotFoundError:
        raise _unreachable("docker CLI not found") from None


def _probe() -> bool:
    try:
        with urllib.request.urlopen(_PROBE_URL, timeout=1):
            return True
    except (OSError, http.client.HTTPException):  # refused, reset while Jaeger starts, timed out, or an HTTP error status
        return False


def status() -> str | None:
    """The container's state (running, exited, created, ...), or None when it doesn't exist."""
    r = _docker("inspect", "--format", "{{.State.Status}}", NAME)
    if r.returncode == 0:
        return r.stdout.strip()
    if "no such object" in r.stderr.lower():
        return None
    raise _unreachable(_first_line(r.stderr))


def _start_failed(stderr: str) -> JaegerError:
    port = re.search(r"127\.0\.0\.1:(\d+)", stderr)
    if _PORT_TAKEN.search(stderr) and port:
        return JaegerError(f"port {port[1]} is already in use")
    return JaegerError(_first_line(stderr) or "docker could not start the container")


def up(probe: Callable[[], bool] = _probe, timeout_s: float = 20.0, sleep=time.sleep, clock=time.monotonic) -> None:
    state = status()
    if state != "running":
        r = (_docker("run", "-d", "--name", NAME, "-p", "127.0.0.1:16686:16686", "-p", "127.0.0.1:4318:4318", IMAGE)
             if state is None else _docker("start", NAME))  # a failed `run` leaves a `created` container, so the retry is a start
        if r.returncode:
            raise _start_failed(r.stderr)
    deadline = clock() + timeout_s
    while not probe():
        if clock() >= deadline:
            raise JaegerError(f"Jaeger did not answer on {_PROBE_URL} within {timeout_s:g}s")
        sleep(0.5)


def down() -> None:
    r = _docker("rm", "-f", NAME)  # -f: a missing container is not an error, so a failure here means Docker itself
    if r.returncode:
        raise _unreachable(_first_line(r.stderr))


def trace_url(trace_id: str) -> str:
    return f"{UI_URL}/trace/{trace_id}"
