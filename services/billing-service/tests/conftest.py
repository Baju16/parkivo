import pytest
from fastapi.testclient import TestClient
from app.messaging import InMemoryEventBroker

from app.main import create_app

class FakeEurekaClient:
    def __init__(self):
        self.response = {
            "id": 7,
            "started_at": "2026-11-13T10:00:00Z",
            "ended_at": "2026-11-13T11:00:01Z",
        }
        self.error = None
        self.calls = []

    async def start(sefl):
        pass

    async def stop(start):
        pass

    async def do_service(self, service_name, path, return_type=None, timeout=None):
        self.calls.append((service_name, path))

        if self.error is not None:
            raise self.error

        return self.response


@pytest.fixture
def fake_eureka():
    return FakeEurekaClient()


@pytest.fixture
def client(fake_eureka, tmp_path):
    app = create_app(
        eureka_client=fake_eureka,
        event_broker=InMemoryEventBroker(),
        database_url=f"sqlite:///{tmp_path / 'billing.db'}",
    )

    with TestClient(app) as test_client:
        yield test_client
