# Viber Finance（公司财务系统）

把"群里发流水账"升级为有审批、有审计、防篡改的财务系统。

## 解决的痛点

- 重复申请 → 24 小时窗口自动检测，提示二次确认
- 私自修改财务报表 → 已付款单据字段锁定 + 全量审计日志
- 没有审批流 → 三级流程（申请人 → 财务 → 管理），小额可财务先付、管理事后补审批
- 数据散落群里 → Web + Telegram 同步推送，所有记录入库可查

## 技术栈

- 后端：FastAPI + SQLAlchemy
- 数据库：SQLite（<20 人足够，单文件好备份）
- 前端：Jinja2 + Tailwind（无前端构建）
- 通知：Telegram Bot
- 部署：Docker Compose

## 快速开始

```bash
cp .env.example .env
# 编辑 .env，至少修改 SECRET_KEY 和 ADMIN_PASSWORD

docker compose up -d --build
```

访问 http://localhost:8000，默认账号见 `.env` 里的 `ADMIN_USERNAME` / `ADMIN_PASSWORD`。

### 不用 Docker 本地跑

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

## 当前进度

- [x] **M1**：用户/角色 + 系统配置 + 申请单 CRUD + 审计日志
- [ ] **M2**：三级审批流（财务付款 / 管理审批）+ 防篡改锁定
- [ ] **M3**：备用金模块 + 报表（日/周/月）
- [ ] **M4**：Telegram Bot（按钮审批、推送通知）

## 角色

| 角色 | 权限 |
|---|---|
| applicant | 提交/查看自己的申请，撤销待审申请 |
| finance | 审核所有申请，付款，对小额单据先付 |
| manager | 审批已付款单据，驳回异常单 |
| admin | 全部权限 + 配置系统 + 管理用户/分类 + 查看审计日志 |

## 系统配置（admin 后台）

所有规则均可在后台改，不用动代码：

- `small_amount_threshold` — 小额阈值（默认 500）
- `allow_finance_prepay` — 是否允许财务先付（开/关）
- `large_amount_threshold` — 大额二次审批阈值（默认 5000）
- `post_approval_timeout_hours` — 事后补审批超时提醒（默认 48h）
- `default_currency` / `enable_multi_currency` — 币种设置
- `doc_code_prefix` — 单据编号前缀
- `duplicate_check_hours` — 重复申请检测窗口
- Telegram 各类事件推送开关

## Telegram Bot 创建步骤

1. Telegram 搜 `@BotFather`，发 `/newbot`
2. 起名字 + username（必须 `*bot` 结尾）
3. 拿到 token，填入 `.env` 的 `TELEGRAM_BOT_TOKEN`
4. 建群把 bot 拉进去，设为管理员
5. 群里发一条消息，访问 `https://api.telegram.org/bot<TOKEN>/getUpdates` 拿群 `chat.id`
6. 填入 `.env` 的 `TELEGRAM_FINANCE_CHAT_ID` / `TELEGRAM_MANAGER_CHAT_ID`

## 防篡改设计

- `audit_log` 表只追加，不修改不删除
- 申请单进入 `paid` 状态后金额/用途字段锁定，需通过"冲销单"修正并留痕
- 每次配置变更、角色变更、状态变更均记录 before/after JSON
