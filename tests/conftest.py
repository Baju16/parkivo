import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client():
    # Świeża aplikacja i magazyn (z danymi początkowymi) przy każdym teście.
    with TestClient(create_app()) as test_client:
        yield test_client
