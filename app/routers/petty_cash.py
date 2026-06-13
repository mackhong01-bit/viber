from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Request, Depends, Form, File, UploadFile, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User, UserRole
from app.models.petty_cash import PettyCashType
from app.services.auth import require_user
from app.services.audit import log as audit_log
from app.services.uploads import save_upload
from app.services import petty_cash_service
from app.templates_env import templates

router = APIRouter(prefix="/petty-cash")


def _parse_amount(s: str) -> Decimal:
    try:
        a = Decimal(s)
        if a <= 0:
            raise InvalidOperation
        return a
    except InvalidOperation:
        raise HTTPException(400, "金额格式错误")


@router.get("")
def index(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    items = petty_cash_service.list_for(db, user)
    my_balance = petty_cash_service.get_balance(db, user.id)
    balances = []
    if user.role in (UserRole.FINANCE.value, UserRole.ADMIN.value, UserRole.MANAGER.value):
        balances = petty_cash_service.all_balances(db)
    users = db.query(User).filter(User.is_active == True).order_by(User.id).all()
    return templates.TemplateResponse(
        "petty_cash/index.html",
        {
            "request": request,
            "user": user,
            "items": items,
            "my_balance": my_balance,
            "balances": balances,
            "users": users,
            "types": [t.value for t in PettyCashType],
        },
    )


@router.post("/allocate")
def allocate(
    target_user_id: int = Form(...),
    amount: str = Form(...),
    note: str = Form(""),
    attachment: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    target = db.get(User, target_user_id)
    if not target:
        raise HTTPException(404, "用户不存在")
    amt = _parse_amount(amount)
    path = save_upload(attachment, subdir="petty_cash")
    entry = petty_cash_service.record(
        db, target_user=target, operator=user,
        type_=PettyCashType.ALLOCATE.value, amount=amt,
        note=note.strip() or None, attachment_path=path,
    )
    audit_log(db, user, "petty_cash.allocate", "petty_cash", entry.id,
              after={"target": target.username, "amount": str(amt),
                     "balance_after": str(entry.balance_after), "attachment": path})
    return RedirectResponse("/petty-cash", status_code=303)


@router.post("/replenish")
def replenish(
    target_user_id: int = Form(...),
    amount: str = Form(...),
    note: str = Form(""),
    attachment: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    target = db.get(User, target_user_id)
    if not target:
        raise HTTPException(404, "用户不存在")
    amt = _parse_amount(amount)
    path = save_upload(attachment, subdir="petty_cash")
    entry = petty_cash_service.record(
        db, target_user=target, operator=user,
        type_=PettyCashType.REPLENISH.value, amount=amt,
        note=note.strip() or None, attachment_path=path,
    )
    audit_log(db, user, "petty_cash.replenish", "petty_cash", entry.id,
              after={"target": target.username, "amount": str(amt),
                     "balance_after": str(entry.balance_after), "attachment": path})
    return RedirectResponse("/petty-cash", status_code=303)


@router.post("/spend")
def spend(
    amount: str = Form(...),
    note: str = Form(""),
    attachment: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    amt = _parse_amount(amount)
    path = save_upload(attachment, subdir="petty_cash")
    if not note.strip():
        raise HTTPException(400, "支出用途必填")
    entry = petty_cash_service.record(
        db, target_user=user, operator=user,
        type_=PettyCashType.SPEND.value, amount=amt,
        note=note.strip(), attachment_path=path,
    )
    audit_log(db, user, "petty_cash.spend", "petty_cash", entry.id,
              after={"amount": str(amt), "balance_after": str(entry.balance_after),
                     "note": note, "attachment": path})
    return RedirectResponse("/petty-cash", status_code=303)


@router.post("/return")
def return_cash(
    amount: str = Form(...),
    note: str = Form(""),
    attachment: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    amt = _parse_amount(amount)
    path = save_upload(attachment, subdir="petty_cash")
    entry = petty_cash_service.record(
        db, target_user=user, operator=user,
        type_=PettyCashType.RETURN.value, amount=amt,
        note=note.strip() or None, attachment_path=path,
    )
    audit_log(db, user, "petty_cash.return", "petty_cash", entry.id,
              after={"amount": str(amt), "balance_after": str(entry.balance_after),
                     "attachment": path})
    return RedirectResponse("/petty-cash", status_code=303)
