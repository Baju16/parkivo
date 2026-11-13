import os
from secrets import randbelow

import httpx
import pytest


@pytest.fixture
def gateway():
    url = os.getenv("GATEWAY_URL", "http://127.0.0.1:8080")
    with httpx.Client(base_url=url, timeout=10, trust_env=False) as client:
        yield client


@pytest.fixture
def active_session(gateway):
    payload = {"space_id": 1 + randbelow(2**31 - 1), "vehicle_plate": "LAB4-TEST"}
    created = gateway.post("/api/sessions", json=payload)
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]
    yield session_id, payload

    path = f"/api/sessions/{session_id}"
    current = gateway.get(path)
    current.raise_for_status()
    if current.json()["ended_at"] is None:
        gateway.post(f"{path}/end").raise_for_status()


def test_read_session_through_gateway(gateway, active_session):
    session_id, payload = active_session
    path = f"/api/sessions/{session_id}"
    for expected_cache in ("MISS", "HIT"):
        response = gateway.get(path)
        assert response.status_code == 200, response.text
        assert response.headers["X-Gateway"] == "lab4"
        assert response.headers["X-Cache"] == expected_cache

        session = response.json()
        assert session["id"] == session_id
        assert session["space_id"] == payload["space_id"]
        assert session["vehicle_plate"] == payload["vehicle_plate"]
        assert session["ended_at"] is None


def test_quote_for_ended_session_through_gateway(gateway, active_session):
    session_id, _ = active_session
    ended = gateway.post(f"/api/sessions/{session_id}/end")
    assert ended.status_code == 200, ended.text

    quote = gateway.get(f"/api/billing/quote/{session_id}")
    assert quote.status_code == 200, quote.text
    assert quote.headers["X-Gateway"] == "lab4"
    assert quote.json() == {
        "session_id": session_id,
        "billable_hours": 1,
        "amount": 5,
        "currency": "PLN",
    }


def test_end_session_invalidates_cache_through_gateway(gateway, active_session):
    session_id, _ = active_session
    path = f"/api/sessions/{session_id}"
    for expected_cache in ("MISS", "HIT"):
        active = gateway.get(path)
        assert active.status_code == 200, active.text
        assert active.headers["X-Cache"] == expected_cache
        assert active.json()["ended_at"] is None

    ended = gateway.post(f"{path}/end")
    assert ended.status_code == 200, ended.text
    assert ended.headers["X-Gateway"] == "lab4"
    assert ended.json()["ended_at"] is not None

    for expected_cache in ("MISS", "HIT"):
        current = gateway.get(path)
        assert current.status_code == 200, current.text
        assert current.headers["X-Gateway"] == "lab4"
        assert current.headers["X-Cache"] == expected_cache
        assert current.json() == ended.json()


def test_gateway_forwards_session_validation_error(gateway):
    response = gateway.post("/api/sessions", json={"space_id": 1})
    assert response.status_code == 422, response.text
    assert response.headers["X-Gateway"] == "lab4"
    errors = response.json()["detail"]
    assert any(
        error["loc"] == ["body", "vehicle_plate"] and error["type"] == "missing"
        for error in errors
    )
