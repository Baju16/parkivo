from datetime import datetime, timedelta


def test_payment_is_saved_and_event_is_published(client):
    response = client.post("/billing/payments/7")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["session_id"] == 7
    assert body["amount"] == 10
    assert body["currency"] == "PLN"

    payment = client.app.state.repository.get_by_session_id(7)
    assert payment is not None
    assert payment.id == body["payment_id"]
    assert payment.event_id == body["event_id"]
    assert payment.amount == 10
    assert payment.currency == "PLN"
    assert payment.published_at is not None

    published = client.app.state.event_broker.published
    assert len(published) == 1

    routing_key, event = published[0]
    assert routing_key == "payment.completed"
    assert event["event_type"] == "PaymentCompleted"
    assert event["event_id"] == payment.event_id
    assert event["payment_id"] == payment.id
    assert event["session_id"] == 7
    assert event["amount"] == 10
    assert event["currency"] == "PLN"

    occurred_at = datetime.fromisoformat(event["occurred_at"])
    assert occurred_at.utcoffset() == timedelta(0)

def test_payment_can_be_retried_after_broker_failure(client):
    broker = client.app.state.event_broker
    repository = client.app.state.repository
    broker.down = True

    response = client.post("/billing/payments/7")

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Publikacja płatności nie powiodła się. Ponów żądanie."
    )
    assert broker.published == []

    payment = repository.get_by_session_id(7)
    assert payment is not None
    assert payment.published_at is None

    payment_id = payment.id
    event_id = payment.event_id

    broker.down = False
    retry = client.post("/billing/payments/7")

    assert retry.status_code == 201, retry.text
    assert retry.json()["payment_id"] == payment_id
    assert retry.json()["event_id"] == event_id

    saved = repository.get_by_session_id(7)
    assert saved.id == payment_id
    assert saved.event_id == event_id
    assert saved.published_at is not None

    assert len(broker.published) == 1
    routing_key, event = broker.published[0]
    assert routing_key == "payment.completed"
    assert event["payment_id"] == payment_id
    assert event["event_id"] == event_id

    duplicate = client.post("/billing/payments/7")

    assert duplicate.status_code == 409
    assert len(broker.published) == 1

def test_active_session_does_not_create_payment_or_event(client, fake_eureka):
    fake_eureka.response["ended_at"] = None
    response = client.post("/billing/payments/7")
    assert response.status_code == 409
    assert client.app.state.event_broker.published == []
    assert client.app.state.repository.get_by_session_id(7) is None


def test_missing_session_does_not_create_payment_or_event(client, fake_eureka):
    from urllib.error import HTTPError

    fake_eureka.error = HTTPError("http://sessions/7", 404, "Not found", {}, None)
    response = client.post("/billing/payments/7")
    assert response.status_code == 404
    assert client.app.state.event_broker.published == []
    assert client.app.state.repository.get_by_session_id(7) is None


def test_invalid_session_id_does_not_publish_event(client, fake_eureka):
    response = client.post("/billing/payments/invalid")
    assert response.status_code == 422
    assert client.app.state.event_broker.published == []
    assert fake_eureka.calls == []
