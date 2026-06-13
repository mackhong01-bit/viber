import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.user import User


def log(
    db: Session,
    user: User | None,
    action: str,
    target_table: str | None = None,
    target_id: str | int | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> None:
    entry = AuditLog(
        user_id=user.id if user else None,
        username=user.username if user else None,
        action=action,
        target_table=target_table,
        target_id=str(target_id) if target_id is not None else None,
        before_json=json.dumps(before, default=str, ensure_ascii=False) if before else None,
        after_json=json.dumps(after, default=str, ensure_ascii=False) if after else None,
        ip_address=ip_address,
    )
    db.add(entry)
    db.commit()
