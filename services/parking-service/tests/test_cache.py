from fastapi.testclient import TestClient

from app.main import create_app


def make(tmp_path, monkeypatch, fake_redis):
    monkeypatch.setenv("CACHE_PREFIX", "lab2:test:parking-service")
    db_url = "sqlite:///" + (tmp_path / "c.db").as_posix()
    return create_app(database_url=db_url, redis_client=fake_redis)


def test_miss_then_hit_skips_repository(tmp_path, monkeypatch, fake_redis):
    app = make(tmp_path, monkeypatch, fake_redis)
    with TestClient(app) as client:
        repo = app.state.repository
        reads = []
        original = repo.get_space
        monkeypatch.setattr(repo, "get_space", lambda i: (reads.append(i), original(i))[1])

        first = client.get("/spaces/1")
        second = client.get("/spaces/1")
        assert first.headers["X-Cache"] == "MISS"
        assert second.headers["X-Cache"] == "HIT"
        assert first.json() == second.json()
        assert len(reads) == 1
        key = app.state.cache.key(1)
        assert key == "lab2:test:parking-service:space:1"
        assert fake_redis.expirations[key] == 60


def test_patch_invalidates_cache(tmp_path, monkeypatch, fake_redis):
    app = make(tmp_path, monkeypatch, fake_redis)
    with TestClient(app) as client:
        client.get("/spaces/1")
        assert client.get("/spaces/1").headers["X-Cache"] == "HIT"
        assert client.patch("/spaces/1/status", json={"status": "RESERVED"}).status_code == 200
        after = client.get("/spaces/1")
        assert after.headers["X-Cache"] == "MISS"
        assert after.json()["status"] == "RESERVED"


def test_rejected_patch_keeps_cache(tmp_path, monkeypatch, fake_redis):
    app = make(tmp_path, monkeypatch, fake_redis)
    with TestClient(app) as client:
        client.get("/spaces/1")
        client.patch("/spaces/1/status", json={"status": "FREE"})  # 409: ten sam status
        assert client.get("/spaces/1").headers["X-Cache"] == "HIT"


def test_missing_space_is_404_and_not_cached(tmp_path, monkeypatch, fake_redis):
    app = make(tmp_path, monkeypatch, fake_redis)
    with TestClient(app) as client:
        assert client.get("/spaces/99").status_code == 404
        assert client.get("/spaces/99").status_code == 404
        assert not fake_redis.values
