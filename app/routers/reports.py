from datetime import datetime, timedelta, date
from decimal import Decimal
from io import StringIO
import csv

from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, case
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.payment import PaymentRequest, PaymentStatus
from app.services.auth import require_user
from app.models.user import UserRole
from fastapi import HTTPException
from app.templates_env import templates

router = APIRouter(prefix="/reports")


def _staff_only(user: User = Depends(require_user)) -> User:
    if user.role not in (UserRole.FINANCE.value, UserRole.MANAGER.value, UserRole.ADMIN.value):
        raise HTTPException(403, "无权查看报表")
    return user


PAID_STATUSES = [
    PaymentStatus.PAID.value,
    PaymentStatus.PAID_PENDING_APPROVAL.value,
    PaymentStatus.APPROVED.value,
    PaymentStatus.FLAGGED.value,
]


def _date_range(period: str) -> tuple[datetime, datetime]:
    now = datetime.utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "today":
        return today, today + timedelta(days=1)
    if period == "week":
        start = today - timedelta(days=today.weekday())
        return start, start + timedelta(days=7)
    if period == "year":
        return today.replace(month=1, day=1), today.replace(month=1, day=1).replace(year=today.year + 1)
    # default: month
    start = today.replace(day=1)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


@router.get("")
def index(
    request: Request,
    period: str = Query("month"),
    db: Session = Depends(get_db),
    user: User = Depends(_staff_only),
):
    start, end = _date_range(period)

    paid_q = db.query(PaymentRequest).filter(
        PaymentRequest.paid_at >= start,
        PaymentRequest.paid_at < end,
        PaymentRequest.status.in_(PAID_STATUSES),
    )
    created_q = db.query(PaymentRequest).filter(
        PaymentRequest.created_at >= start,
        PaymentRequest.created_at < end,
    )

    total_paid = paid_q.with_entities(func.coalesce(func.sum(PaymentRequest.amount), 0)).scalar() or Decimal("0")
    total_requests = created_q.count()
    paid_count = paid_q.count()
    flagged_count = paid_q.filter(PaymentRequest.status == PaymentStatus.FLAGGED.value).count()

    by_category = (
        paid_q.with_entities(
            PaymentRequest.category,
            func.count(PaymentRequest.id),
            func.coalesce(func.sum(PaymentRequest.amount), 0),
        )
        .group_by(PaymentRequest.category)
        .order_by(func.sum(PaymentRequest.amount).desc())
        .all()
    )

    by_department = (
        paid_q.with_entities(
            func.coalesce(PaymentRequest.department, "未指定"),
            func.count(PaymentRequest.id),
            func.coalesce(func.sum(PaymentRequest.amount), 0),
        )
        .group_by(PaymentRequest.department)
        .order_by(func.sum(PaymentRequest.amount).desc())
        .all()
    )

    by_applicant = (
        paid_q.join(User, User.id == PaymentRequest.applicant_id)
        .with_entities(
            User.full_name,
            func.count(PaymentRequest.id),
            func.coalesce(func.sum(PaymentRequest.amount), 0),
        )
        .group_by(User.id)
        .order_by(func.sum(PaymentRequest.amount).desc())
        .all()
    )

    return templates.TemplateResponse(
        "reports/index.html",
        {
            "request": request,
            "user": user,
            "period": period,
            "start": start,
            "end": end,
            "stats": {
                "total_paid": total_paid,
                "total_requests": total_requests,
                "paid_count": paid_count,
                "flagged_count": flagged_count,
            },
            "by_category": by_category,
            "by_department": by_department,
            "by_applicant": by_applicant,
        },
    )


@router.get("/export.csv")
def export_csv(
    period: str = Query("month"),
    db: Session = Depends(get_db),
    user: User = Depends(_staff_only),
):
    start, end = _date_range(period)
    rows = (
        db.query(PaymentRequest)
        .filter(PaymentRequest.created_at >= start, PaymentRequest.created_at < end)
        .order_by(PaymentRequest.created_at.asc())
        .all()
    )

    buf = StringIO()
    buf.write("﻿")  # BOM for Excel CN
    w = csv.writer(buf)
    w.writerow(["编号", "申请人", "金额", "币种", "类别", "部门", "收款方",
                "用途", "状态", "提交时间", "付款时间", "审批时间"])
    for r in rows:
        w.writerow([
            r.code, r.applicant.full_name if r.applicant else "",
            str(r.amount), r.currency, r.category, r.department or "",
            r.payee or "", r.purpose, r.status,
            r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "",
            r.paid_at.strftime("%Y-%m-%d %H:%M") if r.paid_at else "",
            r.approved_at.strftime("%Y-%m-%d %H:%M") if r.approved_at else "",
        ])
    buf.seek(0)

    fname = f"report-{period}-{start.strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
