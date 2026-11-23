from sqlalchemy import select
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy.exc import IntegrityError

from app.db_models import PaymentRow

class PaymentsRepository:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    def get_by_session_id(self, session_id: int) -> PaymentRow | None:
        with self.session_factory() as session:
            statement = select(PaymentRow).where(PaymentRow.session_id == session_id)

            return session.scalar(statement)
        
    def add(self, session_id: int, amount: int, currency: str = "PLN"):
        with self.session_factory() as session:
            payment = PaymentRow(session_id=session_id, amount=amount, currency=currency, paid_at=datetime.now(timezone.utc), event_id=f"evt-{uuid4().hex}", published_at = None)
            
            session.add(payment)

            try:
                session.commit()
            except IntegrityError:
                session.rollback()

                existing = self.get_by_session_id(session_id)

                if existing is not None:
                    return existing
                
                raise

            return payment
        
    def mark_published(self, payment_id: int) -> PaymentRow:
        with self.session_factory() as session:
            payment = session.get(PaymentRow, payment_id)

            if payment is None:
                raise LookupError("Płatność nie istnieje")

            if payment.published_at is None:
                payment.published_at = datetime.now(timezone.utc)
                session.commit()

            return payment
