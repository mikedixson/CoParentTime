from __future__ import annotations

from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import time

import httpx
import pytest


def test_uvicorn_starts_and_serves_application(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    for directory in ("app", "templates", "static"):
        shutil.copytree(
            repo_root / directory,
            tmp_path / directory,
            ignore=shutil.ignore_patterns("__pycache__"),
        )

    log_path = tmp_path / "uvicorn.log"
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "0",
                "--no-use-colors",
            ],
            cwd=tmp_path,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 30
            while True:
                output = log_path.read_text(encoding="utf-8")
                if process.poll() is not None:
                    pytest.fail(f"Uvicorn exited during startup:\n{output}")
                address = re.search(r"Uvicorn running on (http://127\.0\.0\.1:\d+)", output)
                if address:
                    break
                if time.monotonic() >= deadline:
                    pytest.fail(f"Uvicorn did not start within 30 seconds:\n{output}")
                time.sleep(0.1)

            with httpx.Client(base_url=address.group(1), timeout=10, trust_env=False) as client:
                health = client.get("/health")
                assert health.status_code == 200
                assert health.json()["status"] == "ok"

                home = client.get("/")
                assert home.status_code == 200
                assert 'id="googleWarningBanner"' in home.text

                stylesheet = client.get("/static/style.css")
                assert stylesheet.status_code == 200
                assert stylesheet.headers["content-type"].startswith("text/css")
                assert stylesheet.text.strip()

            database = tmp_path / "coparentime.db"
            assert database.is_file()
            with sqlite3.connect(database) as connection:
                tables = {
                    row[0]
                    for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
                }
            assert {"planning_runs", "run_inputs", "run_results"} <= tables
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
