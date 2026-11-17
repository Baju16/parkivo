from urllib.error import HTTPError, URLError

from fastapi.testclient import TestClient

from app.main import create_app
from tests.fakes import FakeEurekaClient

BODY = {"space_id": 1, "user_id": "jan"}


def http_error(code):
    return HTTPError("http://parking/spaces/1", code, "error", {}, None)


def test_success_discovers_parking_service_by_name(client, fake):
    response = client.post("/reservations", json=BODY)
    assert response.status_code == 201
    assert response.json() == {"id": 1, "space_id": 1, "user_id": "jan", "status": "ACTIVE"}
    assert fake.calls == [("PARKING-SERVICE", "/spaces/1", "json", 2)]
    assert client.get("/reservations/1").json()["user_id"] == "jan"


def test_path_uses_space_id_from_request(client, fake):
    client.post("/reservations", json={"space_id": 42, "user_id": "ola"})
    assert fake.calls[0][1] == "/spaces/42"


def test_missing_space_is_404_and_nothing_saved():
    fake = FakeEurekaClient(error=http_error(404))
    with TestClient(create_app(eureka_client=fake)) as client:
        response = client.post("/reservations", json=BODY)
        assert response.status_code == 404
        assert response.json() == {"detail": "Space not found"}
        assert client.get("/reservations").json() == []


def test_unavailable_dependency_is_503_and_health_stays_ok():
    fake = FakeEurekaClient(error=URLError("connection refused"))
    with TestClient(create_app(eureka_client=fake)) as client:
        response = client.post("/reservations", json=BODY)
        assert response.status_code == 503
        assert client.get("/health").status_code == 200
        assert client.get("/reservations").json() == []


def test_timeout_is_503():
    fake = FakeEurekaClient(error=TimeoutError("timeout"))
    with TestClient(create_app(eureka_client=fake)) as client:
        assert client.post("/reservations", json=BODY).status_code == 503


def test_other_http_error_is_502():
    fake = FakeEurekaClient(error=http_error(500))
    with TestClient(create_app(eureka_client=fake)) as client:
        assert client.post("/reservations", json=BODY).status_code == 502


def test_not_free_space_is_409_and_not_saved():
    fake = FakeEurekaClient(response={"id": 1, "status": "OCCUPIED"})
    with TestClient(create_app(eureka_client=fake)) as client:
        response = client.post("/reservations", json=BODY)
        assert response.status_code == 409
        assert response.json() == {"detail": "Space not available"}
        assert client.get("/reservations").json() == []


def test_invalid_body_is_422_without_calling_parking_service(client, fake):
    assert client.post("/reservations", json={"space_id": "x", "user_id": ""}).status_code == 422
    assert fake.calls == []


def test_unknown_reservation_is_404(client):
    assert client.get("/reservations/99").status_code == 404


def test_eureka_client_started_and_stopped_with_app(fake):
    with TestClient(create_app(eureka_client=fake)):
        assert fake.starts == 1 and fake.stops == 0
    assert fake.starts == fake.stops == 1
