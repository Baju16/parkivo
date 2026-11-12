from fastapi.testclient import TestClient

from app.main import create_app

def test_session_survives_app_restart(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'sessions.db'}"

    with TestClient(create_app(database_url=database_url)) as first_client:
        response = first_client.post(
            "/sessions",
            json={"space_id": 1, "vehicle_plate": "RKR12345"},
        )
        assert response.status_code == 201
        created = response.json()

    with TestClient(create_app(database_url=database_url)) as second_client:
        response = second_client.get(f"/sessions/{created['id']}")
        assert response.status_code == 200
        assert response.json() == created