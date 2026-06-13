from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models.payment import PaymentRequest, PaymentStatus
from app.services import config_service


def generate_code(db: Session) -> str:
    prefix = config_service.get_config(db, "doc_code_prefix") or "PAY"
    year = datetime.utcnow().year
    last = (
        db.query(PaymentRequest)
        .filter(PaymentRequest.code.like(f"{prefix}-{year}-%"))
        .order_by(PaymentRequest.id.desc())
        .first()
    )
    if last:
        try:
            seq = int(last.code.split("-")[-1]) + 1
        except ValueError:
            seq = 1
        return f"{prefix}-{year}-{seq:04d}"
    return f"{prefix}-{year}-0001"


def find_possible_duplicate(
    db: Session,
    applicant_id: int,
    amount: Decimal,
    purpose: str,
) -> PaymentRequest | None:
    window_hours = config_service.get_config_int(db, "duplicate_check_hours")
    if window_hours <= 0:
        return None
    since = datetime.utcnow() - timedelta(hours=window_hours)
    return (
        db.query(PaymentRequest)
        .filter(
            and_(
                PaymentRequest.applicant_id == applicant_id,
                PaymentRequest.amount == amount,
                PaymentRequest.purpose == purpose,
                PaymentRequest.created_at >= since,
                PaymentRequest.status.notin_([
                    PaymentStatus.CANCELLED.value,
                    PaymentStatus.REJECTED.value,
                ]),
            )
        )
        .first()
    )


def can_finance_prepay(db: Session, amount: Decimal) -> bool:
    if not config_service.get_config_bool(db, "allow_finance_prepay"):
        return False
    threshold = config_service.get_config_decimal(db, "small_amount_threshold")
    return amount <= threshold


def requires_large_approval(db: Session, amount: Decimal) -> bool:
    threshold = config_service.get_config_decimal(db, "large_amount_threshold")
    return amount >= threshold
