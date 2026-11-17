import pytest
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError

from app.main import create_app


class MemoryRedis:
    """Zamiennik Redis do testów (bez TTL); nie zastępuje ręcznej próby na prawdziwym Redis."""

    def __init__(self):
        self.values = {}
        self.expirations = {}
        self.down = False

    def check(self):
        if self.down:
            raise ConnectionError("Simulated outage")

    def get(self, key):
        self.check()
        return self.values.get(key)

    def set(self, key, value, ex):
        self.check()
        self.values[key] = value
        self.expirations[key] = ex

    def delete(self, key):
        self.check()
        self.values.pop(key, None)
        self.expirations.pop(key, None)

    def ping(self):
        self.check()
        return True

    def close(self):
        pass


@pytest.fixture
def fake_redis():
    return MemoryRedis()


@pytest.fixture
def client(tmp_path, monkeypatch, fake_redis):
    # Osobna baza w tmp_path i osobny cache dla każdego testu.
    monkeypatch.setenv("CACHE_PREFIX", "lab2:test:parking-service")
    db_url = "sqlite:///" + (tmp_path / "test.db").as_posix()
    with TestClient(create_app(database_url=db_url, redis_client=fake_redis)) as test_client:
        yield test_client
