from __future__ import annotations

import shutil
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    # Patch module-level storage paths so tests do not write to production files.
    import app.db as db
    import app.services.report_renderer as report_renderer

    test_db = tmp_path / "test.db"
    test_artifacts = tmp_path / "artifacts"

    monkeypatch.setattr(db, "DB_PATH", test_db)
    monkeypatch.setattr(report_renderer, "ARTIFACTS_DIR", test_artifacts)

    db.init_db()
    yield

    if test_artifacts.exists():
        shutil.rmtree(test_artifacts, ignore_errors=True)
