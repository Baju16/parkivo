def set_status(client, space_id, status):
    return client.patch(f"/spaces/{space_id}/status", json={"status": status})


# --- odczyt znanych danych początkowych ---

def test_list_and_detail_of_seeded_lot(client):
    listing = client.get("/parking-lots")
    assert listing.status_code == 200
    assert listing.json() == [
        {"id": 1, "name": "Parking Szpital", "address": "ul. lwowska 60"}
    ]

    detail = client.get("/parking-lots/1")
    assert detail.status_code == 200
    assert detail.json()["name"] == "Parking Szpital"


def test_list_spaces_filters_and_empty_list(client):
    all_spaces = client.get("/parking-lots/1/spaces")
    assert all_spaces.status_code == 200
    assert [s["number"] for s in all_spaces.json()] == ["A-01", "A-02", "A-03"]

    ev = client.get("/parking-lots/1/spaces", params={"type": "EV"})
    assert ev.status_code == 200
    assert [s["number"] for s in ev.json()] == ["A-02"]

    # istniejący parking bez pasujących miejsc: 200 i pusta lista, nie 404
    none_match = client.get("/parking-lots/1/spaces", params={"status": "OCCUPIED"})
    assert none_match.status_code == 200
    assert none_match.json() == []


# --- zapis -> odczyt ---

def test_create_space_then_read_it_back(client):
    created = client.post(
        "/parking-lots/1/spaces", json={"number": "B-01", "type": "EV"}
    )
    assert created.status_code == 201
    body = created.json()
    assert body["number"] == "B-01"
    assert body["type"] == "EV"
    assert body["status"] == "FREE"
    assert body["parking_lot_id"] == 1

    # osobny GET potwierdza zapis
    fetched = client.get(f"/spaces/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == body
    numbers = [s["number"] for s in client.get("/parking-lots/1/spaces").json()]
    assert "B-01" in numbers


def test_create_lot_then_read_it_back(client):
    created = client.post(
        "/parking-lots", json={"name": "Parking Rynek", "address": "Rynek 1"}
    )
    assert created.status_code == 201
    assert created.json()["id"] == 2

    fetched = client.get("/parking-lots/2")
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Parking Rynek"
    assert len(client.get("/parking-lots").json()) == 2


# --- brak zasobu (404) ---

def test_missing_resources_return_404(client):
    lot = client.get("/parking-lots/99")
    assert lot.status_code == 404
    assert lot.json() == {"detail": "Parking lot 99 not found"}

    space = client.get("/spaces/99")
    assert space.status_code == 404
    assert space.json() == {"detail": "Space 99 not found"}

    assert client.get("/parking-lots/99/spaces").status_code == 404
    assert client.post("/parking-lots/99/spaces", json={"number": "X-1"}).status_code == 404
    assert set_status(client, 99, "RESERVED").status_code == 404


# --- niepoprawne dane (422), stan bez zmian ---

def test_invalid_data_returns_422_and_changes_nothing(client):
    lots_before = client.get("/parking-lots").json()
    spaces_before = client.get("/parking-lots/1/spaces").json()

    empty_name = client.post("/parking-lots", json={"name": "", "address": "x"})
    assert empty_name.status_code == 422
    assert empty_name.json()["detail"][0]["loc"] == ["body", "name"]

    too_long = client.post("/parking-lots/1/spaces", json={"number": "A" * 11})
    assert too_long.status_code == 422

    bad_status = set_status(client, 1, "BROKEN")
    assert bad_status.status_code == 422

    assert client.get("/parking-lots").json() == lots_before
    assert client.get("/parking-lots/1/spaces").json() == spaces_before


# --- konflikt (409), stan bez zmian ---

def test_duplicate_lot_name_returns_409_and_changes_nothing(client):
    response = client.post(
        "/parking-lots", json={"name": "Parking Szpital", "address": "inny adres"}
    )
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]
    assert len(client.get("/parking-lots").json()) == 1


def test_duplicate_space_number_returns_409_and_changes_nothing(client):
    response = client.post("/parking-lots/1/spaces", json={"number": "A-01"})
    assert response.status_code == 409
    assert response.json() == {
        "detail": "Space A-01 already exists in parking lot 1"
    }
    assert len(client.get("/parking-lots/1/spaces").json()) == 3


def test_same_space_number_allowed_in_another_lot(client):
    other = client.post("/parking-lots", json={"name": "Drugi", "address": "x"}).json()
    response = client.post(f"/parking-lots/{other['id']}/spaces", json={"number": "A-01"})
    assert response.status_code == 201


# --- reguła biznesowa: przejścia statusów ---

def test_allowed_status_transition_is_visible_in_next_get(client):
    response = set_status(client, 1, "RESERVED")
    assert response.status_code == 200
    assert response.json()["status"] == "RESERVED"
    assert client.get("/spaces/1").json()["status"] == "RESERVED"


def test_occupied_space_cannot_be_reserved(client):
    assert set_status(client, 1, "OCCUPIED").status_code == 200

    rejected = set_status(client, 1, "RESERVED")
    assert rejected.status_code == 409
    assert rejected.json() == {
        "detail": "Niedozwolona zmiana statusu: OCCUPIED -> RESERVED"
    }
    # po odrzuceniu stan pozostaje bez zmian
    assert client.get("/spaces/1").json()["status"] == "OCCUPIED"


def test_out_of_service_space_must_return_to_free_first(client):
    assert set_status(client, 1, "OUT_OF_SERVICE").status_code == 200
    assert set_status(client, 1, "OCCUPIED").status_code == 409
    assert client.get("/spaces/1").json()["status"] == "OUT_OF_SERVICE"

    assert set_status(client, 1, "FREE").status_code == 200
    assert set_status(client, 1, "OCCUPIED").status_code == 200


def test_setting_the_same_status_is_a_conflict(client):
    response = set_status(client, 1, "FREE")
    assert response.status_code == 409
    assert client.get("/spaces/1").json()["status"] == "FREE"


# --- izolacja: świeża aplikacja = znany stan ---

def test_each_test_starts_from_seed_state(client):
    # zmiany z innych testów (np. OCCUPIED, dodane miejsca) nie mogą być widoczne
    assert client.get("/spaces/1").json()["status"] == "FREE"
    assert len(client.get("/parking-lots/1/spaces").json()) == 3
    assert len(client.get("/parking-lots").json()) == 1
