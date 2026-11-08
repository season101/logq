import subprocess
import time
import uuid

import pytest

from logq.cli import main


def _ok(*cmd):
    try:
        return subprocess.run(cmd, capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


pytestmark = pytest.mark.skipif(
    not (_ok("docker", "info") and _ok("docker", "image", "inspect", "alpine")),
    reason="needs a running Docker daemon and the alpine image; run `docker pull alpine`",
)


def test_query_real_container(capsys):
    name = f"logq-it-{uuid.uuid4().hex[:8]}"
    script = ('echo \'{"level":"error","msg":"it-json","trace_id":"abcdef1234567890"}\'; '
              'echo "ERROR it-plain token=supersecret123"; printf "bad \\377 byte\\n"; sleep 60')
    subprocess.run(["docker", "run", "-d", "--name", name, "alpine", "sh", "-c", script], check=True, capture_output=True)
    try:
        time.sleep(1.5)
        assert main(["query", "-p", name, "--since", "5m", "-l", "debug"]) == 0
        out = capsys.readouterr().out
        assert "it-json" in out and "it-plain" in out and "[REDACTED]" in out
        assert "supersecret123" not in out and "�" in out
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)
