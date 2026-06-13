"""Telegram notifier. Pulls token/chat IDs from system_config (DB) first,
falls back to .env. Skips silently if not configured or network fails."""
import asyncio
import logging
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.services import config_service

logger = logging.getLogger(__name__)

TIMEOUT = 8


def _get_token(db: Session) -> str:
    return config_service.get_config(db, "telegram_bot_token") or settings.telegram_bot_token


def _get_chat(db: Session, key: str) -> str:
    return config_service.get_config(db, key) or {
        "telegram_finance_chat_id": settings.telegram_finance_chat_id,
        "telegram_manager_chat_id": settings.telegram_manager_chat_id,
    }.get(key, "")


def _api(token: str, method: str) -> str:
    return f"https://api.telegram.org/bot{token}/{method}"


async def _send_async(token: str, chat_id: str, text: str) -> bool:
    if not token or not chat_id:
        return False
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.post(
                _api(token, "sendMessage"),
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                      "disable_web_page_preview": True},
            )
            if r.status_code != 200:
                logger.warning("Telegram send failed: %s %s", r.status_code, r.text[:200])
                return False
            return True
    except Exception as e:
        logger.warning("Telegram send error: %s", e)
        return False


def send(db: Session, chat_id: str, text: str) -> bool:
    token = _get_token(db)
    if not token or not chat_id:
        return False
    try:
        return asyncio.run(_send_async(token, chat_id, text))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_send_async(token, chat_id, text))
        finally:
            loop.close()


def send_to_finance(db: Session, text: str) -> bool:
    return send(db, _get_chat(db, "telegram_finance_chat_id"), text)


def send_to_manager(db: Session, text: str) -> bool:
    return send(db, _get_chat(db, "telegram_manager_chat_id"), text)


def send_to_user(db: Session, telegram_chat_id: Optional[str], text: str) -> bool:
    if not telegram_chat_id:
        return False
    return send(db, telegram_chat_id, text)


# ---------- 业务事件通知 ----------

def notify_request_created(db: Session, req) -> None:
    if not config_service.get_config_bool(db, "telegram_notify_new_request"):
        return
    text = (
        f"📥 <b>新付款申请</b>\n"
        f"编号：{req.code}\n"
        f"申请人：{req.applicant.full_name}\n"
        f"金额：<b>{req.currency} {req.amount:,.2f}</b>\n"
        f"类别：{req.category}\n"
        f"用途：{req.purpose[:200]}"
    )
    send_to_finance(db, text)


def notify_finance_paid(db: Session, req, approver, is_prepay: bool) -> None:
    if not config_service.get_config_bool(db, "telegram_notify_payment"):
        return
    tag = "🟡 小额已先付，待管理补审批" if is_prepay else "🟢 已付款，待管理审批"
    text = (
        f"💸 <b>财务已付款</b>\n"
        f"编号：{req.code}\n"
        f"金额：<b>{req.currency} {req.amount:,.2f}</b>\n"
        f"申请人：{req.applicant.full_name}\n"
        f"付款人：{approver.full_name}\n"
        f"用途：{req.purpose[:200]}\n"
        f"{tag}"
    )
    send_to_manager(db, text)
    send_to_user(db, req.applicant.telegram_chat_id, text)


def notify_manager_decision(db: Session, req, approver, approved: bool, note: str | None) -> None:
    if not config_service.get_config_bool(db, "telegram_notify_approval"):
        return
    icon = "✅" if approved else "⚠️"
    title = "管理已批准" if approved else "管理驳回（已付款 → 异常单据）"
    text = (
        f"{icon} <b>{title}</b>\n"
        f"编号：{req.code}\n"
        f"金额：{req.currency} {req.amount:,.2f}\n"
        f"申请人：{req.applicant.full_name}\n"
        f"审批人：{approver.full_name}"
    )
    if note:
        text += f"\n备注：{note[:200]}"
    send_to_finance(db, text)
    send_to_user(db, req.applicant.telegram_chat_id, text)


def notify_finance_rejected(db: Session, req, approver, note: str | None) -> None:
    if not config_service.get_config_bool(db, "telegram_notify_approval"):
        return
    text = (
        f"❌ <b>财务驳回申请</b>\n"
        f"编号：{req.code}\n"
        f"金额：{req.currency} {req.amount:,.2f}\n"
        f"申请人：{req.applicant.full_name}\n"
        f"驳回人：{approver.full_name}"
    )
    if note:
        text += f"\n原因：{note[:200]}"
    send_to_user(db, req.applicant.telegram_chat_id, text)


def notify_petty_cash(db: Session, entry, operator) -> None:
    if not config_service.get_config_bool(db, "telegram_notify_payment"):
        return
    type_label = {
        "allocate": "📤 拨付备用金",
        "replenish": "📤 补充备用金",
        "spend": "🛒 备用金支出",
        "return": "↩️ 备用金归还",
    }.get(entry.type, entry.type)
    text = (
        f"{type_label}\n"
        f"对象：{entry.user.full_name}\n"
        f"金额：<b>{entry.amount:,.2f}</b>\n"
        f"操作人：{operator.full_name}\n"
        f"当前余额：{entry.balance_after:,.2f}"
    )
    if entry.note:
        text += f"\n说明：{entry.note[:200]}"
    send_to_finance(db, text)
    send_to_user(db, entry.user.telegram_chat_id, text)
