"""
Shared pytest fixtures for backend tests. Points the app at a throwaway
SQLite file (never the real obtrac.db) — this must happen before app.db
.database is imported anywhere, since DATABASE_URL is read at import time.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

_tmp_dir = tempfile.mkdtemp(prefix="obtrac_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_tmp_dir, 'test.db')}"
os.environ.setdefault("OBTRAC_ENCRYPTION_KEY", "JE2fOcXVLjhWrZUnJc80_IGvz-zRmKHUxooUVZa8k0k=")

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.database import init_db

init_db()


@pytest.fixture()
def client():
    return TestClient(app)
