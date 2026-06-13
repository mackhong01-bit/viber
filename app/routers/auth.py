from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.services.security import verify_password
from app.services.audit import log as audit_log
from app.templates_env import templates

router = APIRouter()


@router.get("/login")
def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login")
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.username == username).first()
    if not user or not user.is_active or not verify_password(password, user.password_hash):
        audit_log(db, None, "login_failed", "users", username, after={"username": username})
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "用户名或密码错误"},
            status_code=401,
        )
    request.session["user_id"] = user.id
    audit_log(db, user, "login_success", "users", user.id)
    return RedirectResponse("/", status_code=303)


@router.get("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    uid = request.session.get("user_id")
    if uid:
        user = db.get(User, uid)
        audit_log(db, user, "logout", "users", uid)
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
