from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import String, DateTime, Numeric, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PettyCashType(str, Enum):
    ALLOCATE = "allocate"      # 拨付备用金
    SPEND = "spend"            # 支出
    REPLENISH = "replenish"    # 补充
    RETURN = "return"          # 归还


class PettyCash(Base):
    __tablename__ = "petty_cash"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    type: Mapped[str] = mapped_column(String(20))
    account_type: Mapped[str] = mapped_column(String(20), default="cash", index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    balance_after: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    tx_hash: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    ref_request_id: Mapped[int | None] = mapped_column(ForeignKey("payment_requests.id"), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    attachment_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    user = relationship("User", foreign_keys=[user_id])
    operator = relationship("User", foreign_keys=[operator_id])
