from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")


def format_money(value, currency: str = "CNY") -> str:
    if value is None:
        return "-"
    try:
        return f"{currency} {float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)


def status_label(status: str) -> str:
    return {
        "pending_finance": "待财务审核",
        "paid_pending_approval": "已付款·待管理补审批",
        "paid": "已付款·待管理审批",
        "approved": "已批准",
        "rejected": "已驳回",
        "flagged": "异常",
        "cancelled": "已撤销",
    }.get(status, status)


def status_color(status: str) -> str:
    return {
        "pending_finance": "bg-yellow-100 text-yellow-800",
        "paid_pending_approval": "bg-blue-100 text-blue-800",
        "paid": "bg-blue-100 text-blue-800",
        "approved": "bg-green-100 text-green-800",
        "rejected": "bg-red-100 text-red-800",
        "flagged": "bg-red-200 text-red-900",
        "cancelled": "bg-gray-100 text-gray-700",
    }.get(status, "bg-gray-100 text-gray-700")


def role_label(role: str) -> str:
    return {
        "applicant": "申请人",
        "finance": "财务",
        "manager": "管理",
        "admin": "管理员",
    }.get(role, role)


templates.env.filters["money"] = format_money
templates.env.filters["status_label"] = status_label
templates.env.filters["status_color"] = status_color
templates.env.filters["role_label"] = role_label
