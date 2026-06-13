from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.petty_cash import PettyCash, PettyCashType
from app.models.user import User, UserRole


SIGN = {
    PettyCashType.ALLOCATE.value: Decimal("1"),
    PettyCashType.REPLENISH.value: Decimal("1"),
    PettyCashType.SPEND.value: Decimal("-1"),
    PettyCashType.RETURN.value: Decimal("-1"),
}


def get_balance(db: Session, user_id: int) -> Decimal:
    last = (
        db.query(PettyCash)
        .filter(PettyCash.user_id == user_id)
        .order_by(PettyCash.id.desc())
        .first()
    )
    return last.balance_after if last else Decimal("0")


def record(
    db: Session,
    *,
    target_user: User,
    operator: User,
    type_: str,
    amount: Decimal,
    note: str | None,
    attachment_path: str | None,
) -> PettyCash:
    if type_ not in SIGN:
        raise HTTPException(400, "无效的备用金操作类型")
    if amount <= 0:
        raise HTTPException(400, "金额必须大于 0")
    if not attachment_path:
        raise HTTPException(400, "备用金操作必须上传截图凭证")

    # 权限：拨付/补充仅 finance/admin；支出/归还可本人或 finance/admin
    if type_ in (PettyCashType.ALLOCATE.value, PettyCashType.REPLENISH.value):
        if operator.role not in (UserRole.FINANCE.value, UserRole.ADMIN.value):
            raise HTTPException(403, "仅财务/管理员可拨付或补充备用金")
    else:
        if operator.id != target_user.id and operator.role not in (
            UserRole.FINANCE.value, UserRole.ADMIN.value,
        ):
            raise HTTPException(403, "只能操作自己的备用金")

    current = get_balance(db, target_user.id)
    delta = SIGN[type_] * amount
    new_balance = current + delta

    if new_balance < 0:
        raise HTTPException(400, f"余额不足：当前 {current}，本次需 {amount}")

    entry = PettyCash(
        user_id=target_user.id,
        type=type_,
        amount=amount,
        balance_after=new_balance,
        note=note,
        attachment_path=attachment_path,
        operator_id=operator.id,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def all_balances(db: Session) -> list[tuple[User, Decimal]]:
    users = db.query(User).filter(User.is_active == True).order_by(User.id).all()
    return [(u, get_balance(db, u.id)) for u in users]


def list_for(db: Session, user: User, limit: int = 200) -> list[PettyCash]:
    q = db.query(PettyCash)
    if user.role == UserRole.APPLICANT.value:
        q = q.filter(PettyCash.user_id == user.id)
    return q.order_by(PettyCash.created_at.desc()).limit(limit).all()
