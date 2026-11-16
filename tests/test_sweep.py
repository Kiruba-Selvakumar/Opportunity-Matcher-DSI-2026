"""The endpoint sweep against a real server process. A new route with no sweep step fails here, so coverage cannot slip."""
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from eval import sweep

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def server(pipeline_dir, tmp_path):
    data = tmp_path / "data"
    for part in ("raw", "clean", "derived", "private"):
        shutil.copytree(pipeline_dir / "data" / part, data / part)
    env = {**os.environ, "MATCHER_DATA_ROOT": str(data), "MATCHER_EVAL_ROOT": str(tmp_path / "eval"), "MATCHER_DOTENV": "0", "DEMO_LOGIN": "1",
           "DEMO_PASSWORD": "a long demo password", "WHATSAPP_VERIFY_TOKEN": "vt"}
    subprocess.run([sys.executable, "-m", "matcher.accounts", "seed-demo"], env=env, cwd=ROOT, check=True, capture_output=True)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    p = subprocess.Popen([sys.executable, "-m", "uvicorn", "api.server:app", "--port", str(port), "--log-level", "warning"], env=env, cwd=ROOT)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(120):
            try:
                httpx.get(f"{base}/api/health", timeout=1)
                break
            except httpx.TransportError:
                time.sleep(0.5)
        yield base
    finally:
        p.terminate()
        p.wait(10)


def test_every_route_answers_and_refuses_the_wrong_people(server):
    s = sweep.Sweep(server, None, verify_token="vt")
    s.run()
    assert s.failures == []
    assert sweep.all_routes() - s.covered == set()
    assert s.covered - sweep.all_routes() == set()
