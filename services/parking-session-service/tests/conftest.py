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


class FakeEurekaClient:
    async def start(self):
        pass

    async def stop(self):
        pass


@pytest.fixture
def fake_redis():
    return MemoryRedis()


@pytest.fixture
def app_factory(tmp_path, monkeypatch, fake_eureka):
    monkeypatch.setenv("CACHE_PREFIX", "lab2:test:parking-session-service")
    monkeypatch.setenv("CACHE_TTL_SECONDS", "60")
    database_url = f"sqlite:///{tmp_path / 'sessions.db'}"

    def make_app(redis_client=None):
        if redis_client is None:
            redis_client = MemoryRedis()
        return create_app(database_url=database_url, redis_client=redis_client,  eureka_client=fake_eureka)

    return make_app


@pytest.fixture
def client(app_factory, fake_redis):
    with TestClient(app_factory(fake_redis)) as test_client:
        yield test_client


@pytest.fixture
def fake_eureka():
    return FakeEurekaClient()
