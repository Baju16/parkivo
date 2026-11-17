def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "parking-service"}


def test_eureka_client_is_started_and_stopped_with_the_app(tmp_path, monkeypatch, fake_redis):
    from fastapi.testclient import TestClient

    from app.main import create_app
    from tests.fakes import FakeEurekaClient

    monkeypatch.setenv("CACHE_PREFIX", "lab3:test:parking-service")
    fake = FakeEurekaClient()
    db_url = "sqlite:///" + (tmp_path / "eureka.db").as_posix()
    with TestClient(create_app(database_url=db_url, redis_client=fake_redis, eureka_client=fake)) as client:
        assert fake.starts == 1 and fake.stops == 0
        assert client.get("/health").status_code == 200
    assert fake.starts == fake.stops == 1
