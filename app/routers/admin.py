from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User, UserRole
from app.models.config import Category, Department
from app.models.audit import AuditLog
from app.services.auth import require_user
from app.services.audit import log as audit_log
from app.services import config_service, telegram as tg_service
from app.services.security import hash_password
from app.templates_env import templates

router = APIRouter(prefix="/admin")


def _admin_only(user: User = Depends(require_user)) -> User:
    if user.role != UserRole.ADMIN.value:
        raise HTTPException(403, "仅管理员可访问")
    return user


@router.get("/config")
def config_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(_admin_only),
):
    return templates.TemplateResponse(
        "admin/config.html",
        {"request": request, "user": user, "configs": config_service.all_configs(db)},
    )


@router.post("/config")
async def config_save(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(_admin_only),
):
    form = await request.form()
    changes = []
    for key, _, _ in config_service.all_configs(db):
        new_val = form.get(key)
        if new_val is None:
            continue
        old = config_service.get_config(db, key)
        if new_val != old:
            config_service.set_config(db, key, new_val)
            changes.append({"key": key, "from": old, "to": new_val})
    if changes:
        audit_log(db, user, "config.update", "system_config", None, after={"changes": changes})
    return RedirectResponse("/admin/config", status_code=303)


@router.get("/categories")
def categories_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(_admin_only),
):
    cats = db.query(Category).order_by(Category.sort_order, Category.id).all()
    return templates.TemplateResponse(
        "admin/categories.html",
        {"request": request, "user": user, "items": cats},
    )


@router.post("/categories/add")
def categories_add(
    request: Request,
    name: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(_admin_only),
):
    name = name.strip()
    if not name:
        raise HTTPException(400, "名称必填")
    if db.query(Category).filter(Category.name == name).first():
        raise HTTPException(400, "已存在")
    cat = Category(name=name)
    db.add(cat)
    db.commit()
    audit_log(db, user, "category.create", "categories", cat.id, after={"name": name})
    return RedirectResponse("/admin/categories", status_code=303)


@router.post("/categories/{cat_id}/toggle")
def categories_toggle(
    cat_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_admin_only),
):
    cat = db.get(Category, cat_id)
    if not cat:
        raise HTTPException(404)
    before = {"is_active": cat.is_active}
    cat.is_active = not cat.is_active
    db.commit()
    audit_log(db, user, "category.toggle", "categories", cat.id,
              before=before, after={"is_active": cat.is_active})
    return RedirectResponse("/admin/categories", status_code=303)


@router.get("/users")
def users_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(_admin_only),
):
    users = db.query(User).order_by(User.id).all()
    return templates.TemplateResponse(
        "admin/users.html",
        {"request": request, "user": user, "items": users, "roles": [r.value for r in UserRole]},
    )


@router.post("/users/add")
def users_add(
    request: Request,
    username: str = Form(...),
    full_name: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    telegram_chat_id: str = Form(""),
    department: str = Form(""),
    usdt_trc20_address: str = Form(""),
    bank_account: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(_admin_only),
):
    if role not in {r.value for r in UserRole}:
        raise HTTPException(400, "角色不合法")
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(400, "用户名已存在")
    new_user = User(
        username=username.strip(),
        full_name=full_name.strip(),
        password_hash=hash_password(password),
        role=role,
        telegram_chat_id=telegram_chat_id or None,
        department=department or None,
        usdt_trc20_address=usdt_trc20_address.strip() or None,
        bank_account=bank_account.strip() or None,
    )
    db.add(new_user)
    db.commit()
    audit_log(db, user, "user.create", "users", new_user.id,
              after={"username": username, "role": role,
                     "usdt": usdt_trc20_address, "bank": bank_account})
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/{user_id}/edit")
def users_edit(
    user_id: int,
    full_name: str = Form(...),
    telegram_chat_id: str = Form(""),
    department: str = Form(""),
    usdt_trc20_address: str = Form(""),
    bank_account: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(_admin_only),
):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404)
    before = {
        "full_name": target.full_name, "telegram_chat_id": target.telegram_chat_id,
        "department": target.department, "usdt_trc20_address": target.usdt_trc20_address,
        "bank_account": target.bank_account,
    }
    target.full_name = full_name.strip()
    target.telegram_chat_id = telegram_chat_id.strip() or None
    target.department = department.strip() or None
    target.usdt_trc20_address = usdt_trc20_address.strip() or None
    target.bank_account = bank_account.strip() or None
    db.commit()
    audit_log(db, user, "user.edit", "users", target.id,
              before=before, after={
                  "full_name": target.full_name, "telegram_chat_id": target.telegram_chat_id,
                  "department": target.department, "usdt_trc20_address": target.usdt_trc20_address,
                  "bank_account": target.bank_account,
              })
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/{user_id}/toggle")
def users_toggle(
    user_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_admin_only),
):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404)
    if target.id == user.id:
        raise HTTPException(400, "不能停用自己")
    before = {"is_active": target.is_active}
    target.is_active = not target.is_active
    db.commit()
    audit_log(db, user, "user.toggle", "users", target.id,
              before=before, after={"is_active": target.is_active})
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/telegram/test")
def telegram_test(
    target: str = Form("finance"),
    db: Session = Depends(get_db),
    user: User = Depends(_admin_only),
):
    text = f"🔧 测试推送 from {config_service.get_config(db, 'company_name')}\n操作人：{user.full_name}"
    if target == "finance":
        ok = tg_service.send_to_finance(db, text)
    else:
        ok = tg_service.send_to_manager(db, text)
    audit_log(db, user, "telegram.test", "system_config", None,
              after={"target": target, "ok": ok})
    return RedirectResponse(f"/admin/config?test={'ok' if ok else 'fail'}", status_code=303)


@router.get("/telegram/updates")
def telegram_updates(
    db: Session = Depends(get_db),
    user: User = Depends(_admin_only),
):
    """获取 Bot 收到的最近消息，方便从中提取群 chat_id。"""
    import asyncio, httpx
    token = config_service.get_config(db, "telegram_bot_token") or ""
    if not token:
        return {"error": "Telegram Bot Token 未配置"}
    try:
        async def fetch():
            async with httpx.AsyncClient(timeout=8) as c:
                r = await c.get(f"https://api.telegram.org/bot{token}/getUpdates")
                return r.json()
        try:
            data = asyncio.run(fetch())
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                data = loop.run_until_complete(fetch())
            finally:
                loop.close()
    except Exception as e:
        return {"error": str(e)}
    chats = {}
    for upd in data.get("result", []):
        msg = upd.get("message") or upd.get("channel_post") or {}
        chat = msg.get("chat", {})
        if chat.get("id"):
            chats[str(chat["id"])] = {
                "type": chat.get("type"),
                "title": chat.get("title") or chat.get("username") or chat.get("first_name"),
            }
    return {"raw": data, "chats": chats,
            "hint": "把上面的 chat id（群是负数）填到 admin/config 的 telegram_finance_chat_id / telegram_manager_chat_id"}


@router.get("/audit")
def audit_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(_admin_only),
):
    logs = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(200).all()
    return templates.TemplateResponse(
        "admin/audit.html",
        {"request": request, "user": user, "items": logs},
    )
