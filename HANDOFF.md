# HANDOFF — 上下文交接

> 这份文件是给**接手开发的 Claude Code CLI 会话**的。
> 先读 `CLAUDE.md` 了解项目结构和约定，再读这份了解"开发到哪了 + 下一步要干啥"。
> 项目源代码：分支 `claude/hhh-PqtbX`，仓库 `mackhong01-bit/viber`。

## 当前进度

| 里程碑 | 内容 | 状态 |
|---|---|---|
| **M1** | 用户/角色 + 系统配置 + 申请单 CRUD + 审计日志 | ✅ |
| **M2** | 三级审批流 + 强制截图凭证 + 字段锁定 | ✅ |
| **M3** | 备用金（拨付/支出/补充/归还）+ 报表 + CSV 导出 | ✅ |
| **M4** | Telegram 推送（财务群/管理群/申请人私聊） | ✅ |
| **M5** | 账户分类（现金/USDT/银行）+ USDT-TRC20 链上监控 | ✅ |
| M6（未做） | Telegram 内联按钮审批 / USDT 自动入账 / 双因素登录 | ⬜ |

代码已经过手动冒烟测试（所有 routes 200，状态机/权限/重复检测/对账逻辑都通过）。

## 用户的下一步：部署

**目标服务器**：用户提到的 Windows Server（IP 不在此文档里——已让用户改密码后再说）。
**部署目录**：`C:\finance`
**Windows 服务名**：`Finance`（用 NSSM）
**端口**：8000（外网防火墙需放行）

### 用户已表态

- 不要动服务器上其他东西，只在独立目录工作 ← **务必尊重这条边界**
- 已经在本机装了 Claude Code CLI，要用 CLI 继续开发
- 之前用过临时账号在另一个 GitHub，可能会把仓库搬过去
- 项目最终名字叫 **Finance**（不再叫 Viber Finance）

### 部署核对清单（Windows）

```powershell
# 体检（不改任何东西）
python --version            # 没装就装 3.11+
git --version
netstat -ano | findstr ":8000"   # 看端口是否占用
Test-Path C:\finance              # 目录是否已存在

# 装依赖（如缺）
choco install -y python312 git nssm    # 没装 chocolatey 先装

# 克隆 + 启动
cd C:\
git clone https://github.com/mackhong01-bit/viber.git finance
cd finance
git checkout claude/hhh-PqtbX
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# 改 SECRET_KEY 和 ADMIN_PASSWORD！
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 装 Windows 服务（避免关 PowerShell 就停）
nssm install Finance "C:\finance\.venv\Scripts\python.exe" "-m uvicorn app.main:app --host 0.0.0.0 --port 8000"
nssm set Finance AppDirectory C:\finance
nssm start Finance

# 防火墙
New-NetFirewallRule -DisplayName "Finance 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow
```

## 待办（按优先级）

### 高优先级

1. **🔴 用户的 Telegram bot token 已泄露**
   - 用户在聊天里贴过明文 token：`8928708882:AAF_T8hEA173ymT6Hu3VAA20aJHbJbNC3Ng`
   - 已写入 `.env`（未提交），但必须让用户 **去 @BotFather `/revoke` 然后 `/token` 重发**，再填新 token
   - 务必在第一次部署时提醒用户

2. **🔴 用户的 RDP 密码已泄露**
   - 用户在聊天里贴过 Windows Server 凭证
   - 必须让用户改 RDP 密码
   - 务必在第一次见到用户时提醒

3. **配置 Telegram chat_id**
   - admin → 系统配置：填 `telegram_finance_chat_id` 和 `telegram_manager_chat_id`
   - 工具按钮"获取 chat_id"会调 `getUpdates` 自动列出群 ID

4. **创建实际员工账号**
   - 至少：1 个财务、1-N 个管理、N 个申请人
   - 给员工填 Telegram chat_id（私聊推送）、USDT 地址（USDT 监控）

### 中优先级

5. **跑通一次完整流程**做 UAT：申请 → 审批 → 付款 → 备用金拨付 → USDT 支出 → 看报表 → 看审计

6. **域名 + HTTPS**
   - 现在 `http://IP:8000` 不安全
   - 选项：IIS 反代 + Let's Encrypt（win-acme），或 nginx for Windows

7. **数据备份**
   - 数据全在 `C:\finance\data\finance.db` 和 `C:\finance\uploads\`
   - 推荐：每天 PowerShell 计划任务打 tar.gz 备份到另一个目录或 OSS

### 低优先级（M6 候选）

8. **Telegram 内联按钮审批**——财务/管理在群里按按钮就批/拒，不用打开 web
9. **USDT 自动入账**——后台 worker 定时扫链上 TX，自动创建 petty_cash 记录
10. **改密功能**——目前只能改 .env 重启
11. **alembic 迁移**——目前 schema 改了就得删 db 重跑

## 开发约定（接手必看）

读 `CLAUDE.md` 里的"开发规范"那一节。要点：

- 任何"动钱"动作要走 `payment_service` / `petty_cash_service`，里面有权限和状态校验
- 添加新事件要同步加 `telegram.notify_*`
- 改 schema 后**没有迁移脚本**——开发环境直接 `rm data/finance.db` 重新 bootstrap
- 用户对**截图凭证**的要求是硬性的——别图省事把它做成可选

## 用户的偏好（沟通中观察到的）

- 中文交流，回复偏短直接
- 想要"我说一句你做完"的体验，对反复来回的等待没耐心
- 安全意识中等：会问"会不会冲突"，但也会把密码贴聊天里——**主动给安全提醒**
- 对"配置可改"很看重——不希望写死值
- 关注 USDT、银行、现金三种账户的分离
- 部署环境是 Windows Server（不是 Linux），命令要用 PowerShell

## 仓库 / 分支

- GitHub：`https://github.com/mackhong01-bit/viber`（用户可能改名）
- 开发分支：`claude/hhh-PqtbX`
- 主分支 `main` 当前是空的（没合并过任何东西）

## 文件别动

- `.env`（含敏感信息，已 gitignore）
- `data/finance.db`（运行时数据，已 gitignore）
- `uploads/`（用户上传，已 gitignore）

---

**接手后第一句话建议**：
"我看了 CLAUDE.md 和 HANDOFF.md。当前在 `claude/hhh-PqtbX` 分支，M1-M5 完成，准备部署到 Windows Server。你想从哪一步开始？"
