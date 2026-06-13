from decimal import Decimal

from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User, UserRole
from app.models.petty_cash import PettyCash
from app.models.payment import AccountType
from app.services.auth import require_user
from app.services import usdt_service, petty_cash_service
from app.templates_env import templates

router = APIRouter(prefix="/usdt")


def _staff_only(user: User = Depends(require_user)) -> User:
    if user.role not in (UserRole.FINANCE.value, UserRole.MANAGER.value, UserRole.ADMIN.value):
        raise HTTPException(403, "无权查看 USDT 监控")
    return user


@router.get("")
def index(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(_staff_only),
):
    users_with_addr = (
        db.query(User)
        .filter(User.is_active == True, User.usdt_trc20_address.isnot(None))
        .order_by(User.id)
        .all()
    )
    rows = []
    for u in users_with_addr:
        on_chain = usdt_service.get_balance(db, u.usdt_trc20_address)
        system_bal = petty_cash_service.get_balance(db, u.id, AccountType.USDT_TRC20.value)
        diff = (on_chain - system_bal) if on_chain is not None else None
        rows.append({
            "user": u,
            "address": u.usdt_trc20_address,
            "on_chain": on_chain,
            "system": system_bal,
            "diff": diff,
        })
    return templates.TemplateResponse(
        "usdt/index.html",
        {"request": request, "user": user, "rows": rows},
    )


@router.get("/{user_id}")
def detail(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(_staff_only),
):
    target = db.get(User, user_id)
    if not target or not target.usdt_trc20_address:
        raise HTTPException(404, "用户不存在或未配置 USDT 地址")
    on_chain = usdt_service.get_balance(db, target.usdt_trc20_address)
    system_bal = petty_cash_service.get_balance(db, target.id, AccountType.USDT_TRC20.value)
    # System USDT transactions
    system_txs = (
        db.query(PettyCash)
        .filter(
            PettyCash.user_id == target.id,
            PettyCash.account_type == AccountType.USDT_TRC20.value,
        )
        .order_by(PettyCash.created_at.desc())
        .limit(100)
        .all()
    )
    system_hashes = [t.tx_hash for t in system_txs if t.tx_hash]
    reconciliation = usdt_service.reconcile(db, target.usdt_trc20_address, system_hashes)
    return templates.TemplateResponse(
        "usdt/detail.html",
        {
            "request": request, "user": user, "target": target,
            "on_chain": on_chain, "system_bal": system_bal,
            "system_txs": system_txs, "reconciliation": reconciliation,
        },
    )
