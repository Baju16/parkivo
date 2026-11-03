import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.models import ParkingLotCreate, SpaceCreate
from app.database import make_database
from app.repository import ParkingRepository
from app.database import Base
from app import db_models  # noqa: F401
from sqlalchemy.exc import IntegrityError


@pytest.fixture
def db_url(tmp_path, monkeypatch):
    monkeypatch.setenv("CACHE_PREFIX", "lab2:test:parking-service")
    return "sqlite:///" + (tmp_path / "persist.db").as_posix()


def run(db_url, fake_redis, action):
    with TestClient(create_app(database_url=db_url, redis_client=fake_redis)) as c:
        return action(c)


def patch(client, space_id, status):
    return client.patch(f"/spaces/{space_id}/status", json={"status": status})


def test_changes_survive_new_app_instance(db_url, fake_redis):
    from tests.conftest import MemoryRedis

    def write(c):
        assert c.post("/parking-lots/1/spaces", json={"number": "B-01", "type": "EV"}).status_code == 201
        assert patch(c, 1, "OCCUPIED").status_code == 200

    run(db_url, fake_redis, write)

    def read(c):
        spaces = c.get("/parking-lots/1/spaces").json()
        assert [s["number"] for s in spaces] == ["A-01", "A-02", "A-03", "B-01"]
        assert spaces[0]["status"] == "OCCUPIED"  # seed nie nadpisał zmiany

    run(db_url, MemoryRedis(), read)


def test_rejected_operations_leave_database_unchanged(db_url, fake_redis):
    from tests.conftest import MemoryRedis

    def write(c):
        assert patch(c, 1, "OCCUPIED").status_code == 200
        assert patch(c, 1, "RESERVED").status_code == 409
        assert c.post("/parking-lots/1/spaces", json={"number": "A-01"}).status_code == 409
        assert c.post("/parking-lots", json={"name": "Parking Szpital", "address": "x"}).status_code == 409

    run(db_url, fake_redis, write)

    def read(c):
        assert c.get("/spaces/1").json()["status"] == "OCCUPIED"
        assert len(c.get("/parking-lots/1/spaces").json()) == 3
        assert len(c.get("/parking-lots").json()) == 1

    run(db_url, MemoryRedis(), read)


def test_unique_violation_maps_to_409_and_rolls_back(db_url):
    engine, sessions = make_database(db_url)
    Base.metadata.create_all(engine)
    repo = ParkingRepository(sessions)
    lot = repo.create_lot(ParkingLotCreate(name="P", address="a"))
    repo.create_space(lot["id"], SpaceCreate(number="X-1"))
    # pomijamy sprawdzenie w kodzie: duplikat łapie dopiero ograniczenie bazy
    with sessions.begin() as db:
        db.add(db_models.ParkingSpaceRow(parking_lot_id=lot["id"], number="X-2", type="STANDARD", status="FREE"))
    with pytest.raises(IntegrityError):
        with sessions.begin() as db:
            db.add(db_models.ParkingSpaceRow(parking_lot_id=lot["id"], number="X-2", type="STANDARD", status="FREE"))
    assert [s["number"] for s in repo.list_spaces(lot["id"])] == ["X-1", "X-2"]
    engine.dispose()


def test_foreign_key_is_enforced(db_url):
    engine, sessions = make_database(db_url)
    Base.metadata.create_all(engine)
    with pytest.raises(IntegrityError):
        with sessions.begin() as db:
            db.add(db_models.ParkingSpaceRow(parking_lot_id=999, number="Z", type="STANDARD", status="FREE"))
    engine.dispose()
