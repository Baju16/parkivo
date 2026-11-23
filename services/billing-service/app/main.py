import os
import math

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from py_eureka_client.eureka_client import EurekaClient
from datetime import datetime
from urllib.error import HTTPError, URLError
from asyncio import to_thread
from datetime import datetime, timezone

from app.messaging import RabbitEventBroker, BrokerUnavailableError
from app.database import Base, make_database
from app.repository import PaymentsRepository

def create_app(eureka_client=None, event_broker=None, database_url: str | None = None) -> FastAPI:
    discovery = eureka_client
    if discovery is None:
        discovery = EurekaClient(
            eureka_server=os.getenv("EUREKA_SERVER_URL", "http://127.0.0.1:8761"),
            eureka_context="/eureka",
            app_name=os.getenv("SERVICE_NAME", "BILLING-SERVICE"),
            instance_host=os.getenv("INSTANCE_HOST", "localhost"),
            instance_ip=os.getenv("INSTANCE_IP", "127.0.0.1"),
            instance_port=int(os.getenv("SERVICE_PORT", "8104")),
            strict_service_error_policy=False
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        url = database_url or os.getenv(
            "DATABASE_URL", "sqlite:///./billing.db"
        )
        engine, session_factory = make_database(url)

        try:
            broker = event_broker
            if broker is None:
                broker = RabbitEventBroker()

            try:
                Base.metadata.create_all(engine)

                app.state.repository = PaymentsRepository(session_factory)
                app.state.event_broker = broker
                app.state.eureka_client = discovery

                try:
                    await discovery.start()
                    yield
                finally:
                    await discovery.stop()
            finally:
                broker.close()
        finally:
            engine.dispose()

    app = FastAPI(title="Billing Service", lifespan=lifespan)

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "billing-service"}
    

    @app.get("/billing/quote/{session_id}")
    async def get_quote(session_id: int):
        try:
            session = await app.state.eureka_client.do_service(
                "PARKING-SESSION-SERVICE",
                f"/sessions/{session_id}",
                return_type="json",
                timeout=3
            )
        except HTTPError as exc:
            if exc.code == 404:
                raise HTTPException(status_code=404, detail="Sesja nie istnieje") from exc
            
            raise HTTPException(status_code=502, detail="Błąd odpowiedzi Parking Session Service") from exc
        except (URLError, TimeoutError) as exc:
            raise HTTPException(status_code=503, detail="Parking Session Service niedostępny") from exc

        if session["ended_at"] is None:
            raise HTTPException(status_code=409, detail="Sesja nadal trwa")
        
        start = datetime.fromisoformat(session["started_at"])
        end = datetime.fromisoformat(session["ended_at"])

        duration = end - start
        billable_hours = math.ceil(duration.total_seconds() / 3600)
        hourly_rate = 5

        
        return {
            "session_id": session_id,
            "billable_hours": billable_hours,
            "amount": billable_hours * hourly_rate,
            "currency": "PLN",
        }

    @app.post("/billing/payments/{session_id}", status_code=201)
    async def pay_for_session(session_id: int):
        repository = app.state.repository

        payment = await to_thread(
            repository.get_by_session_id, session_id
        )

        if payment is None:
            quote = await get_quote(session_id)

            payment = await to_thread(
                repository.add,
                session_id,
                quote["amount"],
                quote["currency"],
            )

        if payment.published_at is not None:
            raise HTTPException(
                status_code=409,
                detail="Sesja została już opłacona",
            )

        # SQLite odczytuje DateTime bez informacji o strefie.
        # paid_at jest zapisywane w UTC.
        occurred_at = payment.paid_at.replace(tzinfo=timezone.utc)

        event = {
            "event_id": payment.event_id,
            "event_type": "PaymentCompleted",
            "payment_id": payment.id,
            "session_id": payment.session_id,
            "amount": payment.amount,
            "currency": payment.currency,
            "occurred_at": occurred_at.isoformat(),
        }

        try:
            await to_thread(
                app.state.event_broker.publish,
                "payment.completed",
                event,
            )
        except BrokerUnavailableError as exc:
            raise HTTPException(
                status_code=503,
                detail="Publikacja płatności nie powiodła się. Ponów żądanie.",
            ) from exc

        await to_thread(repository.mark_published, payment.id)

        return {
            "payment_id": payment.id,
            "session_id": payment.session_id,
            "amount": payment.amount,
            "currency": payment.currency,
            "event_id": payment.event_id,
        }    

    return app

app = create_app()