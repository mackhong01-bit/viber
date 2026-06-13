from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User, UserRole
from app.models.payment import PaymentRequest, PaymentStatus
from app.models.config import Category, Department
from app.services.auth import require_user
from app.services.audit import log as audit_log
from app.services import config_service, payment_service
from app.templates_env import templates

router = APIRouter(prefix="/requests")


@router.get("")
def list_requests(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    status: str | None = None,
):
    q = db.query(PaymentRequest)
    if user.role == UserRole.APPLICANT.value:
        q = q.filter(PaymentRequest.applicant_id == user.id)
    if status:
        q = q.filter(PaymentRequest.status == status)
    items = q.order_by(PaymentRequest.created_at.desc()).limit(200).all()
    return templates.TemplateResponse(
        "requests/list.html",
        {
            "request": request,
            "user": user,
            "items": items,
            "current_status": status,
            "statuses": [s.value for s in PaymentStatus],
        },
    )


@router.get("/new")
def new_form(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    categories = db.query(Category).filter(Category.is_active == True).order_by(Category.sort_order).all()
    departments = db.query(Department).filter(Department.is_active == True).all()
    default_currency = config_service.get_config(db, "default_currency")
    multi_currency = config_service.get_config_bool(db, "enable_multi_currency")
    return templates.TemplateResponse(
        "requests/new.html",
        {
            "request": request,
            "user": user,
            "categories": categories,
            "departments": departments,
            "default_currency": default_currency,
            "multi_currency": multi_currency,
            "duplicate_warning": None,
            "form": {},
        },
    )


@router.post("/new")
def new_submit(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    amount: str = Form(...),
    currency: str = Form("CNY"),
    category: str = Form(...),
    department: str = Form(""),
    payee: str = Form(""),
    payee_account: str = Form(""),
    purpose: str = Form(...),
    confirm_duplicate: str = Form(""),
):
    try:
        amt = Decimal(amount)
        if amt <= 0:
            raise InvalidOperation
    except InvalidOperation:
        raise HTTPException(400, "金额格式错误")

    if not confirm_duplicate:
        dup = payment_service.find_possible_duplicate(db, user.id, amt, purpose.strip())
        if dup:
            categories = db.query(Category).filter(Category.is_active == True).order_by(Category.sort_order).all()
            departments = db.query(Department).filter(Department.is_active == True).all()
            return templates.TemplateResponse(
                "requests/new.html",
                {
                    "request": request,
                    "user": user,
                    "categories": categories,
                    "departments": departments,
                    "default_currency": currency,
                    "multi_currency": config_service.get_config_bool(db, "enable_multi_currency"),
                    "duplicate_warning": dup,
                    "form": {
                        "amount": amount,
                        "currency": currency,
                        "category": category,
                        "department": department,
                        "payee": payee,
                        "payee_account": payee_account,
                        "purpose": purpose,
                    },
                },
            )

    code = payment_service.generate_code(db)
    req = PaymentRequest(
        code=code,
        applicant_id=user.id,
        amount=amt,
        currency=currency,
        category=category,
        department=department or None,
        payee=payee or None,
        payee_account=payee_account or None,
        purpose=purpose.strip(),
        status=PaymentStatus.PENDING_FINANCE.value,
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    audit_log(
        db, user, "request.create", "payment_requests", req.id,
        after={"code": req.code, "amount": str(amt), "category": category, "purpose": purpose},
    )

    return RedirectResponse(f"/requests/{req.id}", status_code=303)


@router.get("/{req_id}")
def detail(
    req_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    req = db.get(PaymentRequest, req_id)
    if not req:
        raise HTTPException(404, "申请单不存在")
    if user.role == UserRole.APPLICANT.value and req.applicant_id != user.id:
        raise HTTPException(403, "无权查看")
    return templates.TemplateResponse(
        "requests/detail.html",
        {"request": request, "user": user, "req": req},
    )


@router.post("/{req_id}/cancel")
def cancel(
    req_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    req = db.get(PaymentRequest, req_id)
    if not req:
        raise HTTPException(404)
    if req.applicant_id != user.id and user.role != UserRole.ADMIN.value:
        raise HTTPException(403, "只能撤销自己的申请")
    if req.status != PaymentStatus.PENDING_FINANCE.value:
        raise HTTPException(400, "当前状态无法撤销")
    before = {"status": req.status}
    req.status = PaymentStatus.CANCELLED.value
    db.commit()
    audit_log(db, user, "request.cancel", "payment_requests", req.id,
              before=before, after={"status": req.status})
    return RedirectResponse(f"/requests/{req.id}", status_code=303)
