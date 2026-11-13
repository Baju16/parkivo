from urllib.error import HTTPError, URLError

def test_quote_charges_for_two_started_hours(client, fake_eureka):
    response = client.get("/billing/quote/7")

    assert response.status_code == 200
    assert response.json() == {
        "session_id": 7,
        "billable_hours": 2,
        "amount": 10,
        "currency": "PLN",
    }
    assert fake_eureka.calls == [("PARKING-SESSION-SERVICE", "/sessions/7")]

def test_session_not_existing(client, fake_eureka):
    fake_eureka.error = HTTPError("/sessions/6", 404, "Not Found", {}, None)
    
    response = client.get("/billing/quote/6")

    assert response.status_code == 404
    assert response.json() == {"detail": "Sesja nie istnieje"}
    assert fake_eureka.calls == [("PARKING-SESSION-SERVICE", "/sessions/6")]

def test_no_connection_with_session_service(client, fake_eureka):
    fake_eureka.error = URLError("Brak połączenia z Parking Session Service")

    response = client.get("/billing/quote/6")

    assert response.status_code == 503
    assert response.json() == {"detail": "Parking Session Service niedostępny"}
    assert fake_eureka.calls == [("PARKING-SESSION-SERVICE", "/sessions/6")]
    assert client.get("/health").status_code == 200

def test_session_service_error_returns_502(client, fake_eureka):
    fake_eureka.error = HTTPError("/sessions/6", 500, "Internal Server Error", {}, None)

    response = client.get("/billing/quote/6")

    assert response.status_code == 502
    assert response.json() == {"detail": "Błąd odpowiedzi Parking Session Service"}
    assert fake_eureka.calls == [("PARKING-SESSION-SERVICE", "/sessions/6")]

def test_quote_for_active_session_returns_409(client, fake_eureka):
    fake_eureka.response["ended_at"] = None

    response = client.get("/billing/quote/7")

    assert response.status_code == 409
    assert response.json() == {"detail": "Sesja nadal trwa"}
    assert fake_eureka.calls == [("PARKING-SESSION-SERVICE", "/sessions/7")]