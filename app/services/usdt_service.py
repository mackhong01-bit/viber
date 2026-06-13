"""USDT TRC20 on-chain monitor via Tronscan public API."""
import asyncio
import logging
from decimal import Decimal
from datetime import datetime

import httpx
from sqlalchemy.orm import Session

from app.services import config_service

logger = logging.getLogger(__name__)

USDT_TRC20_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
USDT_DECIMALS = 6
DEFAULT_ENDPOINT = "https://apilist.tronscan.org"
TIMEOUT = 10


def _endpoint(db: Session) -> str:
    return (config_service.get_config(db, "tron_api_endpoint") or DEFAULT_ENDPOINT).rstrip("/")


def _headers(db: Session) -> dict:
    key = config_service.get_config(db, "tron_api_key")
    return {"TRON-PRO-API-KEY": key} if key else {}


def _contract(db: Session) -> str:
    return config_service.get_config(db, "usdt_trc20_contract") or USDT_TRC20_CONTRACT


def is_valid_trc20_address(addr: str) -> bool:
    return bool(addr) and addr.startswith("T") and 30 <= len(addr) <= 40


async def _fetch_balance(endpoint: str, headers: dict, address: str, contract: str) -> Decimal | None:
    url = f"{endpoint}/api/account"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, headers=headers) as c:
            r = await c.get(url, params={"address": address})
            if r.status_code != 200:
                return None
            data = r.json()
        for tok in data.get("trc20token_balances", []) or []:
            if (tok.get("tokenId") or "").lower() == contract.lower():
                bal = Decimal(str(tok.get("balance", "0")))
                dec = int(tok.get("tokenDecimal", USDT_DECIMALS))
                return bal / (Decimal(10) ** dec)
        return Decimal("0")
    except Exception as e:
        logger.warning("USDT balance fetch failed for %s: %s", address, e)
        return None


async def _fetch_transfers(endpoint: str, headers: dict, address: str,
                           contract: str, limit: int = 20) -> list[dict] | None:
    url = f"{endpoint}/api/token_trc20/transfers"
    params = {
        "limit": limit, "start": 0, "sort": "-timestamp",
        "count": "true", "relatedAddress": address,
        "contract_address": contract,
    }
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, headers=headers) as c:
            r = await c.get(url, params=params)
            if r.status_code != 200:
                return None
            data = r.json()
        rows = []
        for t in data.get("token_transfers", []) or []:
            decimals = int((t.get("tokenInfo") or {}).get("tokenDecimal", USDT_DECIMALS))
            amount = Decimal(str(t.get("quant", "0"))) / (Decimal(10) ** decimals)
            ts = t.get("block_ts") or 0
            from_addr = t.get("from_address") or ""
            to_addr = t.get("to_address") or ""
            direction = "in" if to_addr == address else "out"
            rows.append({
                "tx_hash": t.get("transaction_id"),
                "from": from_addr,
                "to": to_addr,
                "amount": amount,
                "direction": direction,
                "ts": datetime.fromtimestamp(ts / 1000) if ts else None,
                "confirmed": t.get("confirmed", True),
            })
        return rows
    except Exception as e:
        logger.warning("USDT transfers fetch failed for %s: %s", address, e)
        return None


def _run(coro):
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


def get_balance(db: Session, address: str) -> Decimal | None:
    if not is_valid_trc20_address(address):
        return None
    return _run(_fetch_balance(_endpoint(db), _headers(db), address, _contract(db)))


def get_transfers(db: Session, address: str, limit: int = 20) -> list[dict] | None:
    if not is_valid_trc20_address(address):
        return None
    return _run(_fetch_transfers(_endpoint(db), _headers(db), address, _contract(db), limit))


def reconcile(db: Session, address: str, system_txs: list[str]) -> dict:
    """Returns {on_chain: [...], missing_in_system: [...], unmatched_in_system: [...]}"""
    transfers = get_transfers(db, address, limit=50) or []
    sys_set = {t for t in system_txs if t}
    onchain_set = {t["tx_hash"] for t in transfers if t.get("tx_hash")}
    return {
        "on_chain": transfers,
        "missing_in_system": [t for t in transfers if t["tx_hash"] not in sys_set],
        "unmatched_in_system": list(sys_set - onchain_set),
    }
