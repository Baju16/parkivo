from fastapi.testclient import TestClient

from app.main import create_app


def make(tmp_path, monkeypatch, fake_redis):
    monkeypatch.setenv("CACHE_PREFIX", "lab2:test:parking-service")
    db_url = "sqlite:///" + (tmp_path / "f.db").as_posix()
    return create_app(database_url=db_url, redis_client=fake_redis)


def test_read_and_write_work_without_redis(tmp_path, monkeypatch, fake_redis):
    app = make(tmp_path, monkeypatch, fake_redis)
    with TestClient(app) as client:
        fake_redis.down = True
        read = client.get("/spaces/1")
        assert read.status_code == 200
        assert read.headers["X-Cache"] == "BYPASS"

        write = client.patch("/spaces/1/status", json={"status": "OCCUPIED"})
        assert write.status_code == 200
        assert app.state.repository.get_space(1)["status"] == "OCCUPIED"  # zatwierdzone w bazie
        assert client.get("/spaces/1").json()["status"] == "OCCUPIED"


def test_rules_still_enforced_without_redis(tmp_path, monkeypatch, fake_redis):
    app = make(tmp_path, monkeypatch, fake_redis)
    with TestClient(app) as client:
        client.patch("/spaces/1/status", json={"status": "OCCUPIED"})
        fake_redis.down = True
        assert client.patch("/spaces/1/status", json={"status": "RESERVED"}).status_code == 409
        assert client.get("/spaces/99").status_code == 404


def test_failed_invalidation_leaves_stale_value_until_ttl(tmp_path, monkeypatch, fake_redis):
    app = make(tmp_path, monkeypatch, fake_redis)
    with TestClient(app) as client:
        assert client.get("/spaces/1").json()["status"] == "FREE"  # wpis w cache
        fake_redis.down = True
        assert client.patch("/spaces/1/status", json={"status": "RESERVED"}).status_code == 200
        fake_redis.down = False
        stale = client.get("/spaces/1")
        # atrapa nie symuluje TTL: pokazuje okno starej wartości
        assert stale.headers["X-Cache"] == "HIT"
        assert stale.json()["status"] == "FREE"
        assert app.state.repository.get_space(1)["status"] == "RESERVED"


def test_failed_cache_set_still_returns_database_value(tmp_path, monkeypatch, fake_redis):
    app = make(tmp_path, monkeypatch, fake_redis)
    with TestClient(app) as client:
        from redis.exceptions import ConnectionError as RedisConnectionError
        monkeypatch.setattr(fake_redis, "set", lambda *a, **k: (_ for _ in ()).throw(RedisConnectionError("x")))
        response = client.get("/spaces/1")
        assert response.status_code == 200
        assert response.headers["X-Cache"] == "BYPASS"


def test_ready_reports_degraded_without_redis(tmp_path, monkeypatch, fake_redis):
    app = make(tmp_path, monkeypatch, fake_redis)
    with TestClient(app) as client:
        assert client.get("/ready").json() == {
            "service": "parking-service", "status": "ok", "database": "ok", "cache": "ok",
        }
        fake_redis.down = True
        response = client.get("/ready")
        assert response.status_code == 200
        assert response.json()["status"] == "degraded"
        assert response.json()["cache"] == "down"
        assert client.get("/health").json() == {"status": "ok", "service": "parking-service"}
