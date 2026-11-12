from fastapi.testclient import TestClient


def test_session_survives_app_restart(app_factory):
    with TestClient(app_factory()) as first_client:
        response = first_client.post(
            "/sessions",
            json={"space_id": 1, "vehicle_plate": "RKR12345"},
        )
        assert response.status_code == 201
        created = response.json()

    with TestClient(app_factory()) as second_client:
        response = second_client.get(f"/sessions/{created['id']}")
        assert response.status_code == 200
        assert response.headers["X-Cache"] == "MISS"
        assert response.json() == created
