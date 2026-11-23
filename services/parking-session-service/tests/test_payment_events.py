from datetime import datetime, timezone

from sqlalchemy import select

from app.db_models import ProcessedEventRow


def test_payment_event_is_idempotent_and_invalidates_cache(client):
    created = client.post(
        "/sessions",
        json={"space_id": 1, "vehicle_plate": "KR12345"},
    )
    assert created.status_code == 201
    session_id = created.json()["id"]
    path = f"/sessions/{session_id}"

    ended = client.post(f"{path}/end")
    assert ended.status_code == 200

    for expected_cache in ("MISS", "HIT"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["X-Cache"] == expected_cache
        assert response.json()["is_paid"] is False

    event = {
        "event_id": "evt-test-payment-1",
        "event_type": "PaymentCompleted",
        "payment_id": 1,
        "session_id": session_id,
        "amount": 5,
        "currency": "PLN",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "additional_field": "ignorowane przez konsumenta",
    }

    broker = client.app.state.event_broker
    broker.publish("payment.completed", event)
    broker.publish("payment.completed", event)

    consumed = client.post("/sessions/consume-events")

    assert consumed.status_code == 200, consumed.text
    assert consumed.json() == {
        "consumed_messages": 2,
        "unique_events_processed": 1,
    }

    repository = client.app.state.repository
    assert repository.get_by_id(session_id)["is_paid"] is True

    with repository.sessions() as db:
        event_ids = db.scalars(
            select(ProcessedEventRow.event_id)
        ).all()
        assert event_ids == [event["event_id"]]

    for expected_cache in ("MISS", "HIT"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.json()["is_paid"] is True
        assert response.headers["X-Cache"] == expected_cache

    empty = client.post("/sessions/consume-events")
    assert empty.status_code == 200
    assert empty.json() == {
        "consumed_messages": 0,
        "unique_events_processed": 0,
    }

def test_consumer_returns_503_when_broker_is_down(client):
    client.app.state.event_broker.down = True
    response = client.post("/sessions/consume-events")
    assert response.status_code == 503
    assert response.json()["detail"] == "Przetwarzanie zdarzeń chwilowo niedostępne"
    with client.app.state.repository.sessions() as db:
        assert db.scalars(select(ProcessedEventRow.event_id)).all() == []
