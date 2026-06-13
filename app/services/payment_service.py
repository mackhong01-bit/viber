from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models.payment import PaymentRequest, PaymentStatus, Approval, ApprovalAction
from app.models.user import User, UserRole
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


# ---------- 状态机动作 ----------

def finance_pay(db: Session, req: PaymentRequest, user: User, note: str | None,
                attachment_path: str | None) -> dict:
    """财务付款。小额走 paid_pending_approval，其他走 paid（均需管理审批）。
    必须附付款截图。"""
    if req.status != PaymentStatus.PENDING_FINANCE.value:
        raise HTTPException(400, "当前状态无法付款")
    if user.role not in (UserRole.FINANCE.value, UserRole.ADMIN.value):
        raise HTTPException(403, "无财务权限")
    if not attachment_path:
        raise HTTPException(400, "付款必须上传付款凭证截图")
    before = {"status": req.status, "is_locked": req.is_locked}
    if can_finance_prepay(db, req.amount):
        req.status = PaymentStatus.PAID_PENDING_APPROVAL.value
    else:
        req.status = PaymentStatus.PAID.value
    req.paid_at = datetime.utcnow()
    req.is_locked = True
    db.add(Approval(
        request_id=req.id, approver_id=user.id,
        action=ApprovalAction.FINANCE_PAY.value, note=note,
        attachment_path=attachment_path,
    ))
    db.commit()
    db.refresh(req)
    return {"before": before, "after": {"status": req.status, "is_locked": req.is_locked}}


def finance_reject(db: Session, req: PaymentRequest, user: User, note: str | None,
                   attachment_path: str | None) -> dict:
    if req.status != PaymentStatus.PENDING_FINANCE.value:
        raise HTTPException(400, "当前状态无法驳回")
    if user.role not in (UserRole.FINANCE.value, UserRole.ADMIN.value):
        raise HTTPException(403, "无财务权限")
    if not note:
        raise HTTPException(400, "驳回必须填写原因")
    before = {"status": req.status}
    req.status = PaymentStatus.REJECTED.value
    db.add(Approval(
        request_id=req.id, approver_id=user.id,
        action=ApprovalAction.FINANCE_REJECT.value, note=note,
        attachment_path=attachment_path,
    ))
    db.commit()
    db.refresh(req)
    return {"before": before, "after": {"status": req.status}}


def manager_approve(db: Session, req: PaymentRequest, user: User, note: str | None,
                    attachment_path: str | None) -> dict:
    if req.status not in (PaymentStatus.PAID.value, PaymentStatus.PAID_PENDING_APPROVAL.value):
        raise HTTPException(400, "当前状态无法审批")
    if user.role not in (UserRole.MANAGER.value, UserRole.ADMIN.value):
        raise HTTPException(403, "无管理权限")
    before = {"status": req.status}
    req.status = PaymentStatus.APPROVED.value
    req.approved_at = datetime.utcnow()
    db.add(Approval(
        request_id=req.id, approver_id=user.id,
        action=ApprovalAction.MANAGER_APPROVE.value, note=note,
        attachment_path=attachment_path,
    ))
    db.commit()
    db.refresh(req)
    return {"before": before, "after": {"status": req.status}}


def manager_reject(db: Session, req: PaymentRequest, user: User, note: str | None,
                   attachment_path: str | None) -> dict:
    """管理驳回：若已付款，标记 flagged（异常单据）；否则 rejected。"""
    if req.status not in (PaymentStatus.PAID.value, PaymentStatus.PAID_PENDING_APPROVAL.value):
        raise HTTPException(400, "当前状态无法驳回")
    if user.role not in (UserRole.MANAGER.value, UserRole.ADMIN.value):
        raise HTTPException(403, "无管理权限")
    if not note:
        raise HTTPException(400, "驳回必须填写原因")
    before = {"status": req.status}
    req.status = PaymentStatus.FLAGGED.value
    db.add(Approval(
        request_id=req.id, approver_id=user.id,
        action=ApprovalAction.MANAGER_REJECT.value, note=note,
        attachment_path=attachment_path,
    ))
    db.commit()
    db.refresh(req)
    return {"before": before, "after": {"status": req.status}}


# ---------- 队列查询 ----------

def actionable_for(db: Session, user: User):
    """返回当前用户需要处理的申请单。"""
    q = db.query(PaymentRequest)
    if user.role == UserRole.FINANCE.value:
        q = q.filter(PaymentRequest.status == PaymentStatus.PENDING_FINANCE.value)
    elif user.role == UserRole.MANAGER.value:
        q = q.filter(PaymentRequest.status.in_([
            PaymentStatus.PAID.value,
            PaymentStatus.PAID_PENDING_APPROVAL.value,
        ]))
    elif user.role == UserRole.ADMIN.value:
        q = q.filter(PaymentRequest.status.in_([
            PaymentStatus.PENDING_FINANCE.value,
            PaymentStatus.PAID.value,
            PaymentStatus.PAID_PENDING_APPROVAL.value,
            PaymentStatus.FLAGGED.value,
        ]))
    else:
        q = q.filter(PaymentRequest.id == -1)  # applicant 无队列
    return q.order_by(PaymentRequest.created_at.desc())
