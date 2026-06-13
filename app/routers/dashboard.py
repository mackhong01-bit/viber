from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Request, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User, UserRole
from app.models.payment import PaymentRequest, PaymentStatus
from app.services.auth import require_user
from app.templates_env import templates

router = APIRouter()


@router.get("/")
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = today.replace(day=1)

    base_q = db.query(PaymentRequest)
    if user.role == UserRole.APPLICANT.value:
        base_q = base_q.filter(PaymentRequest.applicant_id == user.id)

    pending_finance = base_q.filter(PaymentRequest.status == PaymentStatus.PENDING_FINANCE.value).count()
    pending_approval = base_q.filter(
        PaymentRequest.status.in_([PaymentStatus.PAID.value, PaymentStatus.PAID_PENDING_APPROVAL.value])
    ).count()

    month_paid = (
        base_q.filter(
            PaymentRequest.paid_at >= month_start,
            PaymentRequest.status.in_([
                PaymentStatus.PAID.value,
                PaymentStatus.PAID_PENDING_APPROVAL.value,
                PaymentStatus.APPROVED.value,
            ]),
        )
        .with_entities(func.coalesce(func.sum(PaymentRequest.amount), 0))
        .scalar()
    ) or Decimal("0")

    flagged = base_q.filter(PaymentRequest.status == PaymentStatus.FLAGGED.value).count()

    recent = base_q.order_by(PaymentRequest.created_at.desc()).limit(10).all()

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "stats": {
                "pending_finance": pending_finance,
                "pending_approval": pending_approval,
                "month_paid": month_paid,
                "flagged": flagged,
            },
            "recent": recent,
        },
    )
