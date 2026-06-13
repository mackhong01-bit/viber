import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Depends
from fastapi.responses import RedirectResponse, JSONResponse, FileResponse
from fastapi.exceptions import HTTPException
from starlette.middleware.sessions import SessionMiddleware

from app.services.auth import require_user
from app.models.user import User

from app.config import settings
from app.database import Base, engine, SessionLocal
from app.models import User, UserRole, Category, Department  # noqa: F401 (register models)
from app.services.security import hash_password
from app.services import config_service
from app.routers import auth as auth_router
from app.routers import requests as requests_router
from app.routers import admin as admin_router
from app.routers import dashboard as dashboard_router


def _bootstrap():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        config_service.seed_defaults(db)

        if not db.query(User).filter(User.username == settings.admin_username).first():
            db.add(User(
                username=settings.admin_username,
                full_name="系统管理员",
                password_hash=hash_password(settings.admin_password),
                role=UserRole.ADMIN.value,
            ))
            db.commit()

        if db.query(Category).count() == 0:
            for i, name in enumerate(["办公采购", "差旅", "餐饮", "营销", "其他"]):
                db.add(Category(name=name, sort_order=i))
            db.commit()

        if db.query(Department).count() == 0:
            for name in ["管理", "财务", "运营", "技术"]:
                db.add(Department(name=name))
            db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _bootstrap()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, max_age=60 * 60 * 12)


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    if exc.status_code == 401:
        return RedirectResponse("/login", status_code=303)
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


app.include_router(auth_router.router)
app.include_router(dashboard_router.router)
app.include_router(requests_router.router)
app.include_router(admin_router.router)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/uploads/{path:path}")
def serve_upload(path: str, user: User = Depends(require_user)):
    """Serve uploaded files to authenticated users only."""
    full = os.path.normpath(os.path.join("uploads", path))
    if not full.startswith("uploads" + os.sep) and full != "uploads":
        raise HTTPException(404)
    if not os.path.isfile(full):
        raise HTTPException(404)
    return FileResponse(full)
