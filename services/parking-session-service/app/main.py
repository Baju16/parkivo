import os
import logging

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Response
from redis import RedisError
from py_eureka_client.eureka_client import EurekaClient
from asyncio import to_thread


from app.models import SessionCreate, ParkingSession
from app.database import Base, make_database
from app.repository import ParkingSessionsRepository
from app.cache import make_redis, JsonCache
from app.messaging import BrokerUnavailableError, RabbitEventBroker

logger = logging.getLogger(__name__)

PAYMENT_QUEUE = "parking-session.payment-events"
PAYMENT_ROUTING_KEY = "payment.completed"

def create_app(database_url: str | None = None, redis_client=None, eureka_client=None, event_broker=None) -> FastAPI:
    discovery = eureka_client
    if discovery is None:
        discovery = EurekaClient(
            eureka_server=os.getenv("EUREKA_SERVER_URL", "http://127.0.0.1:8761"),
            eureka_context="/eureka",
            app_name=os.getenv("SERVICE_NAME", "PARKING-SESSION-SERVICE"),
            instance_host=os.getenv("INSTANCE_HOST", "localhost"),
            instance_ip=os.getenv("INSTANCE_IP", "127.0.0.1"),
            instance_port=int(os.getenv("SERVICE_PORT", "8103")),
            strict_service_error_policy=False
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        url = database_url or os.getenv("DATABASE_URL", "sqlite:///./sessions.db")
        engine, sessions = make_database(url)

        broker = event_broker
        if broker is None:
            broker = RabbitEventBroker()
        
        app.state.event_broker = broker

        client = redis_client

        try:
            if client is None:
                client = make_redis(os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"))

            Base.metadata.create_all(engine)
            app.state.repository = ParkingSessionsRepository(sessions)
            app.state.cache = JsonCache(client, prefix=os.environ["CACHE_PREFIX"], resource_name="session", ttl=int(os.getenv("CACHE_TTL_SECONDS", "60")))
            app.state.eureka_client = discovery
            try:
                try:
                    await to_thread(
                        broker.bind_queue,
                        PAYMENT_QUEUE,
                        PAYMENT_ROUTING_KEY,
                    ) 
                except BrokerUnavailableError:
                    logger.warning("RabbitMQ jest niedostępny podczas tworzenia kolejki")
                await discovery.start()
                yield
            finally:
                try:
                    await discovery.stop()
                finally:
                    broker.close()
        finally:
            try:
                if redis_client is None and client is not None:
                    client.close()
            finally:
                engine.dispose()

    app = FastAPI(title="Parking Session Service", lifespan=lifespan)

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "parking-session-service"}


    @app.post("/sessions", response_model=ParkingSession, status_code=201)
    def create_session(payload: SessionCreate):
        try:
            return app.state.repository.add(payload)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    

    @app.get("/sessions", response_model=list[ParkingSession])
    def list_session():
        return app.state.repository.list_session()


    @app.get("/sessions/{session_id}", response_model=ParkingSession)
    def get_session(session_id: int, response: Response):
        cache = app.state.cache
        cached, source = cache.get(session_id)

        if cached is not None:
            response.headers["X-Cache"] = "HIT"
            return cached

        try:
            session = app.state.repository.get_by_id(session_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        payload = ParkingSession.model_validate(session).model_dump(mode="json")

        if source == "MISS":
            if not cache.put(session_id, payload):
                source = "BYPASS"

        response.headers["X-Cache"] = source
        return payload


    @app.post("/sessions/{session_id}/end", response_model=ParkingSession)
    def end_session(session_id: int):
        try:
            ended = app.state.repository.end_session(session_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        app.state.cache.delete(session_id)
        return ended

    @app.post("/sessions/consume-events")
    def consume_payment_events():
        unique_events_processed = 0

        def handle_event(event):
            nonlocal unique_events_processed

            if not isinstance(event, dict):
                raise ValueError("Zdarzenie musi być obiektem JSON")

            event_id = event.get("event_id")
            session_id = event.get("session_id")

            if not isinstance(event_id, str) or not event_id.strip():
                raise ValueError("Brak poprawnego event_id")

            if type(session_id) is not int or session_id < 0:
                raise ValueError("Niepoprawne session_id")

            if event.get("event_type") != "PaymentCompleted":
                raise ValueError("Nieobsługiwany typ zdarzenia")

            applied = app.state.repository.apply_payment_event(
                event_id, session_id
            )

            if not app.state.cache.delete(session_id):
                raise RedisError("Nie udało się unieważnić cache sesji")

            if applied:
                unique_events_processed += 1

        broker = app.state.event_broker

        try:
            broker.bind_queue(PAYMENT_QUEUE, PAYMENT_ROUTING_KEY)

            consumed_messages = broker.consume_available(
                PAYMENT_QUEUE,
                handle_event,
            )
        except (BrokerUnavailableError, RedisError) as exc:
            raise HTTPException(
                status_code=503,
                detail="Przetwarzanie zdarzeń chwilowo niedostępne",
            ) from exc
        except (ValueError, LookupError) as exc:
            raise HTTPException(
                status_code=422,
                detail=str(exc),
            ) from exc

        return {
            "consumed_messages": consumed_messages,
            "unique_events_processed": unique_events_processed,
        }

    return app

app = create_app()
