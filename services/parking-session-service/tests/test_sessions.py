def test_create_session(client):
    payload = {"space_id": 1, "vehicle_plate": "RKR12345"}

    response = client.post("/sessions", json=payload)

    assert response.status_code == 201
    created = response.json()

    assert isinstance(created["id"], int)
    assert created["space_id"] == 1
    assert created["vehicle_plate"] == "RKR12345"
    assert created["started_at"] is not None
    assert created["ended_at"] is None


def test_read_sessions_list(client):
    payload = {"space_id": 1, "vehicle_plate": "RKR12345"}

    resp = client.post("/sessions", json=payload)
    assert resp.status_code == 201
    created = resp.json()

    response = client.get("/sessions")
    
    assert response.status_code == 200
    assert response.json() == [created]


def test_read_session(client):
    payload = {"space_id": 1, "vehicle_plate": "RKR12345"}

    response = client.post("/sessions", json=payload)
    assert response.status_code == 201
    created = response.json()

    session_id = created["id"]
    response = client.get(f"/sessions/{session_id}")

    assert response.status_code == 200
    assert response.json() == created


def test_worong_space_id(client):
    payload = {"space_id": -1, "vehicle_plate": "RKR12345"}

    response = client.post("/sessions", json=payload)

    assert response.status_code == 422
    errors = response.json()["detail"]
    assert any(error["loc"] == ["body", "space_id"] for error in errors)

    response = client.get("/sessions")
    assert response.status_code == 200
    assert response.json() == []


def test_cannot_create_two_active_sessions_for_same_space(client):
    payload = {"space_id": 1, "vehicle_plate": "RKR12345"}

    response = client.post("/sessions", json=payload)
    assert response.status_code == 201
    created = response.json()

    payload2 = {"space_id": 1, "vehicle_plate": "KR12345"}

    response = client.post("/sessions", json=payload2)
    assert response.status_code == 409
    assert response.json()["detail"] == "Miejsce ma juz aktywną sesję"

    response = client.get("/sessions")
    assert response.status_code == 200
    assert response.json() == [created]


def test_session_end(client):
    payload = {"space_id": 1, "vehicle_plate": "RKR12345"}

    response = client.post("/sessions", json=payload)
    assert response.status_code == 201
    created = response.json()

    session_id = created["id"]
    response = client.post(f"/sessions/{session_id}/end")
    assert response.status_code == 200
    assert response.json()["ended_at"] is not None

    ended = response.json()

    response = client.get(f"/sessions/{session_id}")
    assert response.status_code == 200
    assert response.json() == ended


def test_cannot_end_twice_same_session(client):
    payload = {"space_id": 1, "vehicle_plate": "RKR12345"}

    response = client.post("/sessions", json=payload)
    assert response.status_code == 201
    created = response.json()

    session_id = created["id"]

    response = client.post(f"/sessions/{session_id}/end")
    assert response.status_code == 200
    ended = response.json()

    response = client.post(f"/sessions/{session_id}/end")
    assert response.status_code == 409
    assert response.json()["detail"] == "Sesja jest juz zakończona"

    response = client.get(f"/sessions/{session_id}")
    assert response.status_code == 200
    assert response.json() == ended

def test_new_session_at_same_place(client):
    payload = {"space_id": 1, "vehicle_plate": "RKR12345"}

    response = client.post("/sessions", json=payload)
    assert response.status_code == 201
    created = response.json()

    session_id = created["id"]
    response = client.post(f"/sessions/{session_id}/end")
    assert response.status_code == 200

    payload2 = {"space_id": 1, "vehicle_plate": "KR12345"}
    response = client.post("/sessions", json=payload2)
    assert response.status_code == 201
    new_session = response.json()

    assert new_session["id"] != session_id
    assert new_session["space_id"] == 1
    assert new_session["vehicle_plate"] == "KR12345"
    assert new_session["ended_at"] is None

    response = client.get(f"/sessions/{new_session['id']}")
    assert response.status_code == 200
    assert response.json() == new_session


def test_session_dont_exist(client):
    session_id = 1

    response = client.get(f"/sessions/{session_id}")
    assert response.status_code == 404
    assert response.json()["detail"] == "Sesja nie istnieje"

    response = client.post(f"/sessions/{session_id}/end")
    assert response.status_code == 404
    assert response.json()["detail"] == "Sesja nie istnieje"


def test_health(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "parking-session-service",
    }