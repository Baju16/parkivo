import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.fakes import FakeEurekaClient


@pytest.fixture
def fake():
    return FakeEurekaClient()


@pytest.fixture
def client(fake):
    # Atrapa zamiast Eureki: testy nie łączą się z rejestrem ani z Parking Service.
    with TestClient(create_app(eureka_client=fake)) as test_client:
        yield test_client
