from fastapi import Request, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User, UserRole


def current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    uid = request.session.get("user_id")
    if not uid:
        return None
    return db.get(User, uid)


def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = current_user(request, db)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    return user


def require_role(*roles: UserRole):
    role_values = {r.value for r in roles}

    def dep(user: User = Depends(require_user)) -> User:
        if user.role not in role_values and user.role != UserRole.ADMIN.value:
            raise HTTPException(status_code=403, detail="权限不足")
        return user

    return dep
