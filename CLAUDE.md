# CLAUDE.md — 项目上下文

> 这份文件是 Claude Code 启动时自动读取的项目上下文。每个新会话都从这里继承背景。
> 详细历史和部署 todo 见 `HANDOFF.md`。

## 项目是什么

公司内部 **财务系统**，目的：把"群里发流水账"升级为有审批流、有审计、防篡改的系统。

业务核心：
- 付款申请 → 财务审核 → 财务付款（小额可先付）→ 管理审批
- 备用金管理（拨付/支出/补充/归还）
- USDT-TRC20 钱包链上监控
- Telegram 同步推送
- 所有操作强制上传截图凭证

## 技术栈

| 层 | 选型 |
|---|---|
| 后端 | FastAPI + SQLAlchemy 2.x（同步） |
| 数据库 | SQLite，单文件 `data/finance.db` |
| 前端 | Jinja2 模板 + Tailwind CSS（CDN，零构建） |
| 密码 | bcrypt（直接用 `bcrypt`，不用 passlib） |
| Telegram | httpx 直发 sendMessage |
| USDT | Tronscan 公共 API |
| 部署 | Docker Compose / 或 native Python + NSSM（Windows） |

## 目录结构

```
app/
├── main.py              # FastAPI 入口、lifespan、bootstrap
├── config.py            # pydantic-settings (.env)
├── database.py          # SQLAlchemy engine + SessionLocal
├── templates_env.py     # Jinja2 templates + 自定义 filter
├── models/              # 数据模型
│   ├── user.py          # User + UserRole
│   ├── payment.py       # PaymentRequest + AccountType + Approval
│   ├── petty_cash.py    # PettyCash + PettyCashType
│   ├── config.py        # SystemConfig + Category + Department
│   └── audit.py         # AuditLog（追加式）
├── services/
│   ├── auth.py          # require_user / require_role
│   ├── security.py      # hash_password / verify_password
│   ├── config_service.py # 读写 system_config，含 DEFAULTS
│   ├── audit.py         # log() 追加审计
│   ├── payment_service.py # 状态机：finance_pay/reject, manager_approve/reject
│   ├── petty_cash_service.py # balance 按 (user_id, account_type)
│   ├── usdt_service.py  # Tronscan 查余额 + TRC20 转账列表 + reconcile
│   ├── uploads.py       # save_upload 到 uploads/{subdir}/YYYYMM/{uuid}.ext
│   └── telegram.py      # 各事件 notify_* 函数
├── routers/
│   ├── auth.py          # /login /logout
│   ├── dashboard.py     # /
│   ├── requests.py      # /requests + 审批动作
│   ├── petty_cash.py    # /petty-cash
│   ├── usdt.py          # /usdt 监控
│   ├── reports.py       # /reports + CSV
│   └── admin.py         # /admin/config /users /categories /audit
└── templates/           # Jinja2 模板
```

## 角色

| role | 权限 |
|---|---|
| `applicant` | 提交/查看自己的申请，撤销待审申请 |
| `finance` | 审核所有申请、付款、备用金拨付/补充 |
| `manager` | 审批已付款单据 |
| `admin` | 全部 + 系统配置 + 用户/分类管理 + 审计日志 |

## 申请单状态机

```
                                 ┌─ 财务驳回 → rejected
                                 │
pending_finance ─── 财务通过付款 ─┼─ 小额（且允许先付） → paid_pending_approval ─┐
                                 │                                              ├─ 管理批准 → approved
                                 └─ 其他 → paid ─────────────────────────────────┘
                                                                                 │
                                                              管理驳回（已付款）├─ flagged（异常）
                                                                                 │
applicant 撤销（仅 pending_finance）→ cancelled
```

进入 `paid` 状态后 `is_locked=True`，金额/用途字段锁定。

## 关键约定

### 后台可配置（不动代码即可改）

所有规则进 `system_config` 表，`services/config_service.py::DEFAULTS` 是出厂默认值。常用：

- `small_amount_threshold`（500）— 小额阈值
- `allow_finance_prepay`（true）— 是否允许财务先付
- `duplicate_check_hours`（24）— 重复申请检测窗口
- `telegram_bot_token` + 两个 chat_id（DB 优先级高于 .env）
- `tron_api_endpoint` / `usdt_trc20_contract` — USDT 监控参数

### 强制截图凭证

**所有"动钱"的动作都必须传附件**（图片或 PDF，≤10MB）：

- 申请单提交
- 财务付款
- 备用金 拨付/补充/支出/归还
- 驳回/审批是可选

未传附件 → 后端返 400。

### USDT 强制约束

- USDT 付款申请：必填 `payee_address`（TRC20）
- USDT 财务付款：必填 `tx_hash`
- USDT 备用金 spend/return：必填 `tx_hash`
- 所有 tx_hash 自动生成 `tronscan.org/#/transaction/{hash}` 链接

### 审计日志

每次"动作"都调 `services.audit.log()`：
- 写入 `audit_log` 表（追加式，永不修改/删除）
- 含 user/action/target/before_json/after_json
- 管理员可在 `/admin/audit` 查看

### 防重复提交

申请单提交时调 `payment_service.find_possible_duplicate()`：
- 相同 applicant + amount + purpose
- 在 `duplicate_check_hours` 窗口内
- 命中则返回原单，UI 弹警告，需勾选 `confirm_duplicate=1` 才能继续

## 启动 / 测试 / 部署

```bash
# 开发
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000

# 跑冒烟测试（手动）
python -c "from app.main import app; from fastapi.testclient import TestClient; ..."

# Docker
docker compose up -d --build
docker compose logs -f
```

默认 admin 账号：`admin` / `admin123`（生产环境必须改 .env 里的 ADMIN_PASSWORD）。

## 开发规范

- **不要破坏 audit_log 的追加性**——任何业务改动都要写 audit
- **金额用 Decimal**——别用 float
- **USDT 精度 6 位**，其他默认 2 位
- 路由用 RedirectResponse(303) 跳转，避免重复提交
- 模板 form 提交后用 `enctype="multipart/form-data"`（有文件时）
- 加新业务事件时，记得同时挂到 `telegram.notify_*`

## 已知限制 / 未做

- 没装 alembic 迁移——目前靠 `Base.metadata.create_all`，**schema 改了就得删 db 重跑**
- 没做改密功能（admin 改 .env 重启）
- 没做 Telegram 内联按钮审批（M6 候选）
- 没做 USDT 自动入账（链上扫描 → 自动创建记录）
- 多币种汇率不自动拉
- 没装 alembic / pytest——测试靠手写脚本

## 当前分支

开发都在 `claude/hhh-PqtbX`，主分支 `main` 还是空的。
