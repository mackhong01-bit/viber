"""System configuration accessor. Reads from DB with sane defaults."""
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.config import SystemConfig


DEFAULTS: dict[str, tuple[str, str]] = {
    # key: (default_value, description)
    "small_amount_threshold": ("500", "小额阈值，财务可先付后审批"),
    "allow_finance_prepay": ("true", "是否允许财务对小额单据先付款"),
    "large_amount_threshold": ("5000", "大额二次审批阈值（管理必须审批）"),
    "post_approval_timeout_hours": ("48", "事后补审批超时提醒（小时）"),
    "default_currency": ("CNY", "默认币种"),
    "enable_multi_currency": ("false", "是否启用多币种"),
    "company_name": ("我的公司", "公司名称"),
    "doc_code_prefix": ("PAY", "单据编号前缀"),
    "telegram_notify_new_request": ("true", "新申请推送 Telegram"),
    "telegram_notify_payment": ("true", "付款推送 Telegram"),
    "telegram_notify_approval": ("true", "审批结果推送 Telegram"),
    "telegram_bot_token": ("", "Telegram Bot Token（覆盖 .env）"),
    "telegram_finance_chat_id": ("", "财务通知群 chat_id（覆盖 .env）"),
    "telegram_manager_chat_id": ("", "管理通知群 chat_id（覆盖 .env）"),
    "duplicate_check_hours": ("24", "重复申请检测窗口（小时）"),
}


def get_config(db: Session, key: str) -> str:
    row = db.get(SystemConfig, key)
    if row:
        return row.value
    return DEFAULTS.get(key, ("", ""))[0]


def get_config_decimal(db: Session, key: str) -> Decimal:
    return Decimal(get_config(db, key) or "0")


def get_config_bool(db: Session, key: str) -> bool:
    return get_config(db, key).lower() in ("true", "1", "yes", "on")


def get_config_int(db: Session, key: str) -> int:
    return int(get_config(db, key) or "0")


def set_config(db: Session, key: str, value: str, description: str | None = None) -> None:
    row = db.get(SystemConfig, key)
    if row:
        row.value = value
        if description is not None:
            row.description = description
    else:
        row = SystemConfig(
            key=key,
            value=value,
            description=description or DEFAULTS.get(key, ("", ""))[1],
        )
        db.add(row)
    db.commit()


def all_configs(db: Session) -> list[tuple[str, str, str]]:
    """Returns [(key, value, description), ...] merging DB and defaults."""
    db_rows = {r.key: r for r in db.query(SystemConfig).all()}
    out = []
    for key, (default_val, default_desc) in DEFAULTS.items():
        row = db_rows.get(key)
        out.append((
            key,
            row.value if row else default_val,
            row.description if row and row.description else default_desc,
        ))
    return out


def seed_defaults(db: Session) -> None:
    """Insert default config rows if missing. Called on app startup."""
    for key, (val, desc) in DEFAULTS.items():
        if not db.get(SystemConfig, key):
            db.add(SystemConfig(key=key, value=val, description=desc))
    db.commit()
