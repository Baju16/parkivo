from unittest.mock import Mock

from fastapi.testclient import TestClient

from app.main import create_app
from app.messaging import InMemoryEventBroker


def create_session(client):
    response = client.post("/sessions", json={"space_id": 1, "vehicle_plate": "KR12345"})
    assert response.status_code == 201
    return response.json()


def test_second_read_uses_cache(client, fake_redis, monkeypatch):
    created = create_session(client)
    repo = client.app.state.repository
    read = Mock(wraps=repo.get_by_id)
    monkeypatch.setattr(repo, "get_by_id", read)
    path = f"/sessions/{created['id']}"

    first = client.get(path)
    second = client.get(path)
    assert first.status_code == second.status_code == 200
    assert first.headers["X-Cache"] == "MISS"
    assert second.headers["X-Cache"] == "HIT"
    assert first.json() == second.json() == created
    read.assert_called_once_with(created["id"])
    assert fake_redis.expirations[client.app.state.cache.key(created["id"])] == 60


def test_end_invalidates_cached_session(client):
    created = create_session(client)
    path = f"/sessions/{created['id']}"
    assert client.get(path).headers["X-Cache"] == "MISS"
    assert client.get(path).headers["X-Cache"] == "HIT"

    ended = client.post(f"{path}/end")
    assert ended.status_code == 200
    assert ended.json()["ended_at"] is not None
    after = client.get(path)
    assert after.status_code == 200
    assert after.headers["X-Cache"] == "MISS"
    assert after.json() == ended.json()


def test_database_read_and_write_during_redis_outage(client, fake_redis):
    fake_redis.down = True
    created = create_session(client)
    path = f"/sessions/{created['id']}"
    ended = client.post(f"{path}/end")
    assert ended.status_code == 200
    assert ended.json()["ended_at"] is not None
    read = client.get(path)
    assert read.status_code == 200
    assert read.headers["X-Cache"] == "BYPASS"
    assert read.json() == ended.json()


def test_startup_creates_configured_redis_client(tmp_path, monkeypatch, fake_redis, fake_eureka):
    redis_url = "redis://redis.example:6379/2"
    monkeypatch.setenv("REDIS_URL", redis_url)
    monkeypatch.setenv("CACHE_PREFIX", "lab2:test:parking-session-service")
    factory = Mock(return_value=fake_redis)
    monkeypatch.setattr("app.main.make_redis", factory)
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'sessions.db'}",
        eureka_client=fake_eureka,
        event_broker=InMemoryEventBroker()
    )
    with TestClient(app):
        factory.assert_called_once_with(redis_url)
