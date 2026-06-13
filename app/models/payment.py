from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import String, DateTime, Numeric, ForeignKey, Text, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PaymentStatus(str, Enum):
    PENDING_FINANCE = "pending_finance"        # 待财务审核
    PAID_PENDING_APPROVAL = "paid_pending_approval"  # 小额已付，待管理补审批
    PAID = "paid"                              # 已付款，待管理审批
    APPROVED = "approved"                      # 管理已批准（终态）
    REJECTED = "rejected"                      # 已驳回
    FLAGGED = "flagged"                        # 异常（小额先付但管理驳回）
    CANCELLED = "cancelled"                    # 申请人撤销


class ApprovalAction(str, Enum):
    FINANCE_PAY = "finance_pay"
    MANAGER_APPROVE = "manager_approve"
    MANAGER_REJECT = "manager_reject"
    FINANCE_REJECT = "finance_reject"
    CANCEL = "cancel"


class PaymentRequest(Base):
    __tablename__ = "payment_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    applicant_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(8), default="CNY")
    category: Mapped[str] = mapped_column(String(50))
    department: Mapped[str | None] = mapped_column(String(50), nullable=True)
    payee: Mapped[str | None] = mapped_column(String(100), nullable=True)
    payee_account: Mapped[str | None] = mapped_column(String(100), nullable=True)
    purpose: Mapped[str] = mapped_column(Text)
    attachment_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default=PaymentStatus.PENDING_FINANCE.value, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_locked: Mapped[bool] = mapped_column(default=False)

    applicant = relationship("User", foreign_keys=[applicant_id])
    approvals = relationship("Approval", back_populates="request", cascade="all, delete-orphan")


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("payment_requests.id"))
    approver_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(30))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    attachment_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    request = relationship("PaymentRequest", back_populates="approvals")
    approver = relationship("User", foreign_keys=[approver_id])
