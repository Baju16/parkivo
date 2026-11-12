import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'sessions.db'}"
    app = create_app(database_url=database_url)

    with TestClient(app) as test_client:
        yield test_client