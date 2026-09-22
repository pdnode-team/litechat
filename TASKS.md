# LiteChat 上线前 / 上线后任务交接书

给接手的 agent 的完整说明。**每个任务（T1…T11）都是自包含的**，可以单独派给一个 agent。
开始前请完整读完「零、开工前必读」和「二、全局边界」。

- 仓库：`pdnode-team/litechat`，monorepo（`backend/` + `frontend/`）
- 部署：Dokploy + Nixpacks，**没有 Dockerfile，也不允许新增**（用户明确要求）
- 语言：回答用中文，代码 / UI / API 文案用英文（见 `AGENT.md`）

---

## 零、开工前必读

### 0.1 ⚠️ 工作区里有别人未提交的改动，绝对不要弄丢

当前工作区**不是干净的**。有约 1000 行、49 个文件的改动**没有提交**，产生于 2026-09-20 00:08~00:27，
是一次**安全加固**，不是垃圾：

| 文件 | 内容 |
|---|---|
| `backend/app/controllers/messages.py`（`FileController`） | 附件下载从"无鉴权静态目录"改为按 uploader 校验 |
| `backend/app/models/file_upload.py`（新） | 上传文件的归属记录 |
| `backend/app/services/access.py`（新） | 统一的工单可见性检查（客户不可见的单返回 404 而不是 403，避免存在性泄漏） |
| `backend/app/db/search.py`（新） | `LIKE` 通配符转义 |
| `backend/app/controllers/auth.py` | `token_version` + `revoke_user_sessions`；`/api/auth/ws-ticket` 短期票据 |
| `backend/migrations/versions/c4f91a2b7d10_*.py`（新） | `token_version` 列 + `file_uploads` 表 |
| `backend/app/config.py` | `WS_TICKET_TTL_MINUTES` + 4 条新限流 |
| `backend/tests/test_security.py` 等 | 相应测试 |

**验证过：`import app.main` 正常，115 个后端测试全过**，状态健康。

因此：

- **禁止** `git checkout .` / `git reset --hard` / `git stash` 任何"清理工作区"的操作
- **禁止**在没有读完 `git diff` 的情况下修改上述文件
- 想提交别人的工作前，**先问用户**（见 T0）

### 0.2 未推送的提交

```
7287546  fix(admin): a bad value in an admin form is a 422, not a database 500
1bc9350  fix(admin): stop admin forms sending the same write twice
```

这两个也还在本地，没 push、没部署。生产环境跑的是更早的版本。

### 0.3 改动前必须先跑一遍基线

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider      # 期望 115 passed

cd ..\frontend
.\node_modules\.bin\tsc.cmd -b                                    # 期望 0 错误
.\node_modules\.bin\oxlint.cmd                                    # 期望 0 error（11 个既有 warning 可忽略）
```

**改完必须再跑一遍，并给出对比。** 任何一项变红都不算完成。

### 0.4 环境与沙箱（很重要，能省你半小时）

- Windows + PowerShell。不要用 `cat`，用 read 工具；不要 `find`，用 glob。
- `uv` / `pnpm` / `vite` 的缓存目录在工作区之外，**受限沙箱下会被 EPERM 拒绝**。
  这些命令需要申请完整文件系统权限（一次性的 escalation 即可）。
- `pwsh` 里给原生命令传 `"*"` 会被展开成文件名列表。
  `uvicorn --forwarded-allow-ips "*"` 要写成 `"--forwarded-allow-ips=*"`。
- 本地没有 Docker daemon，别指望本地构建镜像。

---

## 一、任务总览与顺序

| ID | 任务 | 优先级 | 预估 | 前置 |
|---|---|---|---|---|
| T0 | 清理并提交已有的未提交改动 | **阻塞项** | 2h | 用户确认 |
| T1 | 登出即解约（logout） | 上线前必须 | 3h | T0 |
| T2 | 健康检查查库 + 失败告警出口 | 上线前必须 | 3h | — |
| T3 | 邮件移出请求路径 + 失败重试 | 上线前必须 | 1d | — |
| T4 | 注册策略 / 邮箱验证是否强制 | 上线前必须 | 需先决策 | — |
| T5 | CI + 文档清理（+ 可选前端测试） | 上线前必须 | 4h | — |
| T6 | 个人资料页（改密 UI / 改邮箱 / 头像） | 上线后 1~2 周 | 1d | — |
| T7 | SLA 可配置 + 工作时间 | 上线后 1~2 周 | 1.5d | — |
| T8 | 站内通知历史 + SLA 到点事件 | 上线后 1~2 周 | 1.5d | T7 一起做更好 |
| T9 | 搜索扩展（tag 筛选 / 消息 / 自定义字段） | 上线后 1~2 周 | 1d | — |
| T10 | 审计日志（只做写入侧） | 上线后 1~2 周 | 1d | — |
| T11 | CSV 导出 | 有人要再做 | 2h | — |

T1~T5 之间基本无依赖，可以并行派给不同 agent。
T7 和 T8 强相关，**建议给同一个 agent**。

---

## 二、全局边界（不要做）

以下任何一条都不要碰，无论任务看起来多需要：

1. **不要新增 Dockerfile / docker-compose / `.dockerignore`。** 用户明确要求 Dokploy 走 Nixpacks 原生构建。
2. **不要改 `backend/nixpacks.toml`、`frontend/nixpacks.toml`、`backend/start.sh` 的构建语义**（除非任务明确要求，且先说清楚理由）。
3. **不要改数据库 schema 而不写 Alembic 迁移。** 改完必须 `uv run alembic check` 通过。
4. **不要破坏"所有 DateTime 列存 naive UTC"这条约定。** 见 3.2。
5. **不要改 `ticket_types.fields_schema_json` 的存储格式**（它是 JSON 文本，扩展属性靠默认值兼容旧数据）。
6. **不要改动现有 API 的响应契约**（分页信封 `{items,total,limit,offset}`、错误体 `{detail, errors[]}`），只能新增字段。
7. **不要顺手重构。** 每个任务的 diff 只包含该任务需要的东西。看到别的代码有问题，写进回复里告诉用户，不要自己动手。
8. **不要为了让测试变绿而放宽断言或删除测试。**
9. **不要 `git push`。** 提交可以，推送必须由用户决定。
10. **不要引入新的重型依赖**（Redis / Celery / Sentry SDK / 状态管理库…）而不先问用户。
    T3 的重试请用数据库表 + 现有的启动钩子，不要引入任务队列。
11. **一个任务一个提交**，提交信息用英文，说明"为什么"而不只是"做了什么"。

---

## 三、已知坑（踩过，别再踩）

### 3.1 ⚠️ "本地测试通过"说明不了任何事

SQLite 和 PostgreSQL 在下面这些点上**行为不同**，而本项目的本地库正是 SQLite：

| 差异 | 后果 |
|---|---|
| 字符串超长 | SQLite 照存，Postgres 抛 `StringDataRightTruncation` → 500 |
| 外键约束 | SQLite 默认不校验，Postgres 强制 → 500 |
| `timestamp without time zone` | 见 3.2 |

**任何写库的代码，都要问一句"这在 Postgres 上会怎样"。**

### 3.2 时间必须是 naive UTC

所有 `DateTime` 列都用 `app/db/base.py` 里的 `UTCDateTime`，所有"现在"都用 `utcnow()`（返回 **naive** UTC）。

用 `datetime.now(timezone.utc)`（aware）赋值给这些列，在 **Postgres 上会直接 TypeError → 500**，SQLite 上却静默通过。
`tests/test_utc_conventions.py` 有结构化断言守着这条，别绕过它。

### 3.3 测试库是固定文件，不能并发跑

`backend/tests/conftest.py` 用固定的 `tests/test_isolated.db`。
**两个 pytest 同时跑会互相踩**，产生一堆假失败。串行跑。

### 3.4 邮箱校验会拒绝 `.test` 域名

`email-validator` 把 `.test` / `.invalid` / `.localhost` 当保留域名拒绝。
测试里用 `@formtest.com` 这类，别用 `@x.test`。

### 3.5 错误响应契约与异常处理器

- 业务错误：`raise ValidationException("...")` → 400
- 字段级错误：`raise FormValidationError([FieldError(field, message, label, code)])` → 422，body 带 `errors[]`
- **异常处理器按状态码注册，不要注册 `Exception` 类**：Litestar 先查状态码再走 MRO，
  注册 `Exception` 会把 404/403/401 全部吞成 500。见 `app/exception_handlers.py` 的注释。
- 500 会自动带上 request id 并打完整 traceback，**不要**再包一层 try/except 把它吃掉。

### 3.6 动态表单是"三处必须一致"

`frontend/src/components/admin/CustomFieldBuilder.tsx`（管理端）、
`frontend/src/components/customer/CreateTicketModal.tsx`（客户表单）、
`backend/app/services/form_logic.py`（**唯一权威**，前端 `frontend/src/utils/formLogic.ts` 是它的镜像）。

加一个字段属性，三处都要动。改其中一处而忘了另一处 = 表单漂移。

---

## 四、任务详情

### T0 — 提交工作区里已有的未提交改动（阻塞项，先问用户）

**背景**：见 0.1。这批改动是好的、测试是过的，但它没提交也没部署；一句 `git checkout .` 就永久消失。

**要做**
1. `git diff` 通读全部 49 个改动 + 4 个新文件，确认没有调试残留（`print(`、注释掉的代码、临时开关）。
2. 跑 0.3 的基线。
3. 拆成 **2~3 个逻辑提交**，建议：
   - `fix(security): serve uploads through an ownership-checked endpoint`
   - `feat(auth): revoke sessions via token_version and short-lived ws tickets`
   - `fix(security): escape LIKE wildcards, tighten rate limits, uniform ticket 404s`
4. 提交信息说清"为什么"。

**不要做**
- 不要顺手重构、不要"顺便修一下"里面任何你觉得不好的地方——有问题写在回复里。
- 不要 push。
- 不要动 `7287546` / `1bc9350` 这两个已有提交（除非用户要求 rebase）。

**验收**：`git status` 干净；115 个测试仍全过；`git log` 里能看出三块改动各自独立。

---

### T1 — 登出即解约

**现状（已核实）**
- 机制**已经存在**：`users.token_version` 列；`access_token_claims()` 写 `ver`；
  `get_user_from_token()` 比对版本（`backend/app/controllers/auth.py:62`）；
  `revoke_user_sessions()` 会 bump（`auth.py:75`）。
  改密、重置密码、角色变更都已调用它。
- **缺的是一个 `POST /api/auth/logout` 端点**，以及前端登出时调用它。
- 全仓库没有 logout 路由；`frontend/src/context/AuthContext.tsx` 的 `logout()` 只删 localStorage。
- 后果：JWT 有效 7 天。设备丢失、token 被复制走，对方在 7 天内始终可用。

**要做**
1. 后端 `POST /api/auth/logout`：需要认证，调用 `revoke_user_sessions()`，返回 204 或 `{"status":"ok"}`。
   放进现有的限流规则里（`RATE_LIMIT_RULES`）。
2. 前端 `AuthContext.logout()`：先**尽力**调一次接口（失败也要继续登出，不能因为网络问题卡住用户），再清 localStorage。
3. 测试：登出后旧 token 调用 `/api/auth/me` 必须 401；登出不影响其它用户的 token。

**不要做**
- 不要做 token 黑名单表——`token_version` 就是为此存在的。
- 不要动 7 天的有效期（那是另一个决策）。

**验收**：新增测试覆盖"登出后旧 token 失效"；基线四项命令全绿。

---

### T2 — 健康检查要真的检查，失败要有人知道

**现状（已核实）**
`backend/app/main.py:76`
```python
@get("/api/health")
async def health_check() -> dict:
    return {"status": "ok", "service": "LiteChat"}
```
不碰数据库。Dokploy 探活永远绿 —— **库挂了、迁移没跑、连接池耗尽，全是绿的。**

而且**没有任何错误上报/告警出口**：现在 500 有结构化日志和 request id，但只有人主动去翻容器才知道。

**要做**
1. `/api/health` 执行 `SELECT 1`（用 `async_session_factory`，带超时，例如 2 秒）。
   - 成功：`{"status": "ok", "service": "LiteChat", "database": "ok"}`
   - 失败：HTTP **503**，`{"status": "degraded", "database": "error", ...}`，并记一条 ERROR 日志。
2. 新增一个**可选的**失败出口，通过环境变量启用，默认关闭：
   - `ALERT_WEBHOOK_URL`：POST 一段 JSON（事件类型、request id、路径、异常摘要）。
   - 挂到 `backend/app/exception_handlers.py` 的 5xx 分支上；**必须不能因为告警本身失败而影响响应**（包 try/except，只记日志）。
3. 更新 `DEPLOY.md`：说明 Dokploy 健康检查该指向 `/api/health`、返回 503 会被判失败，以及 `ALERT_WEBHOOK_URL` 怎么配。

**不要做**
- 不要接入 Sentry 或任何第三方 SDK（见边界 10）。webhook 是刻意的无依赖方案。
- 不要在 health 里做重活（不要统计工单）。
- 不要给 `/api/health` 加认证（探活必须能匿名访问）。
- 注意：`RequestContextMiddleware` 对 `/api/health` 只记 DEBUG 日志，别改这个行为。

**验收**：新增测试——正常时 200 且 `database == "ok"`；把数据库 URL 换成不可达时返回 503
（可以用 monkeypatch 模拟 `session.execute` 抛异常）。

---

### T3 — 邮件不要卡住请求，发失败要能重试

**现状（已核实）**
- `events.publish()` 里 `await notification_service.handle(...)`，
  而 `publish()` 是在控制器的请求路径里 `await` 的。
- `notification_service.handle()` 会 `await email_service.send_ticket_notification(...)`。
- 也就是：**SMTP 一慢，建单/回复就慢**；发失败只写日志，没有重试。
- 最严重的后果不是"慢"，而是**账户恢复整条链路依赖邮件**：
  重置密码邮件发不出去或进垃圾箱，用户就永久卡住，没有任何补救手段。

**要做**
1. **移出请求路径**：控制器/事件里只把邮件任务入队，实际发送放到请求之后。
   用现有的 Litestar/Starlette 后台机制（`BackgroundTask`）或一个 `asyncio.create_task` 包装，
   **不要引入 Celery/RQ/Redis**。
2. **失败落表 + 重试**：新模型 `email_outbox`（迁移必须写）：
   `id, to_address, subject, body, kind, status(pending/sent/failed), attempts, last_error, next_attempt_at, created_at, updated_at`
   - 发送成功 → `sent`
   - 失败 → `attempts += 1`，指数退避写入 `next_attempt_at`，超过 N 次（建议 5）→ `failed`
3. **重试执行器**：应用启动时起一个后台循环（`asyncio.Task`），每 60 秒捞一批
   `status=pending AND next_attempt_at <= now` 的发。
   **注意多 worker 会重复发送**——用 `SELECT ... FOR UPDATE SKIP LOCKED` 或一个简单的
   "先标记 in_flight 再发"的乐观锁，并在 README 里写清楚它的限制。
4. **管理员可见**：`GET /api/settings/email/outbox`（admin），返回最近 50 条失败的，
   包含 `last_error`。前端可以先不做 UI，但接口要有——否则运维无从排查。
5. 测试：SMTP 抛异常时请求仍返回成功且 outbox 里有一条 pending；
   重试成功后状态变 sent；超过上限变 failed。

**不要做**
- 不要改 `email_service.py` 的发送逻辑本身（除非为了拆出"可重试"的边界）。
- 不要改成同步阻塞重试（那等于把慢移到了别处）。
- **SPF / DKIM / DMARC 不在代码范围内**——那是用户要在 DNS 做的，
  在 `DEPLOY.md` 里写一节说明即可，不要试图"实现"它。

**验收**：新增测试覆盖成功/失败/重试三种路径；现有 `tests/test_notifications.py` 仍全过。

---

### T4 — 注册策略与邮箱验证（⚠️ 必须先让用户决策，不要自己选）

**现状（已核实）**
- `POST /api/auth/register` 任何人可调，验证码都不需要 → 任何人可注册并提工单。
- `email_verified` 字段存在，但**只是提示性的**：未验证邮箱照样能登录、能提工单。
- 也就是：**任何人都能用别人的邮箱注册**（冒名 + 垃圾工单入口）。
- 邮箱改不了（见 T6），所以填错了也没有自救路径。

**要做（第一步不是写代码，是提问）**
把这个决策表给用户，拿到答案再动手：

| 选项 | 含义 | 影响 |
|---|---|---|
| A. 全开放 | 保持现状 | 需要更强的反垃圾（限流 + 人机校验） |
| B. 注册后必须验证邮箱才能提工单 | 折中 | 未验证用户能登录但看到"请先验证"横幅，不能建单 |
| C. 关闭自助注册，仅管理员邀请 | 最严 | **需要新增管理端建号接口**——已核实 `/api/users` 只有 list / assignable / role / status，**没有创建用户的端点** |

拿到答案后：
- 若 B：在 `create_ticket` 前加检查，未验证 → 422 且错误体指向具体原因；
  前端在显眼处给"重新发送验证邮件"的入口（`/api/auth/resend-verification` 已有）。
- 若 C：新增管理员邀请流程（一次性 token 复用 `auth_tokens` 表），
  并想清楚**第一个用户之外**所有账号的来源（否则一旦管理员账密丢了就彻底进不去）。

**不要做**
- **不要自己替用户选。** `AGENT.md` 第 4 条：不确定就问。
- 不要在没决定前就改注册接口的行为。

**验收**：用户明确选了其中一项，且行为与所选一致；有对应测试。

---

### T5 — CI 与文档

**现状（已核实）**
- 没有 `.github/`，**没有任何 CI**。
- `frontend/README.md` 还是 Vite 模板（`# React + TypeScript + Vite` / "This template provides…"）。
- `backend/README.md` 的 **Known gaps 已经过时**（仍写着"没有 token 吊销"，而机制已存在；
  我这两轮已经修了 realtime / 错误处理两段，剩下的要一并清）。
- 前端没有测试脚本（`package.json` 只有 dev/build/lint/preview）。

**要做**
1. `.github/workflows/ci.yml`，两条 job：
   - backend：装 uv → `uv sync --frozen` → `pytest`
   - frontend：装 node 24 + pnpm → `pnpm install --frozen-lockfile` → `tsc -b` → `oxlint` → `vite build`
   版本要和 `backend/nixpacks.toml` / `frontend/nixpacks.toml` 保持一致（**Node 24**，别用 22.x ——
   见 3.x 的 rolldown 原生绑定问题）。
2. `frontend/README.md` 重写成真实内容（30 行内）：项目是什么、怎么起、`VITE_API_BASE_URL` 怎么配、目录结构。
3. 清 `backend/README.md` 的 Known gaps，只保留**今天仍然成立**的条目。
4. 【可选，但很值】引入 `vitest`，**只测 `frontend/src/utils/formLogic.ts`** ——
   它是 `backend/app/services/form_logic.py` 的镜像，纯函数、无 DOM 依赖，
   目前**完全没有测试**，是三处一致契约里最脆弱的一环。测条件求值、隐藏字段丢弃、四类约束即可，不要扩大范围。

**不要做**
- 不要在 CI 里做部署（Dokploy 有自己的 webhook）。
- 不要引入 eslint/rome 之类替换 oxlint。
- 不要为了 CI 去改测试库路径——**但要记住 3.3，CI 上必须串行跑 pytest**。

**验收**：本地能跑通 workflow 里的每条命令；README 内容与现状一致（不要写未实现的功能）。

---

### T6 — 个人资料页

**现状（已核实）**
- `POST /api/auth/change-password` 存在，但**前端没有界面**调它。
- `users.avatar_url` 列存在、`UserResponse` 里有它、`UserAvatar` 组件也在，但**没有任何地方写入**
  （注册时写死 `avatar_url=None`，见 `auth.py:112`）。
- **没有改邮箱的接口**。

**要做**
1. 前端新增 profile 视图（可放在 Navbar 下拉里），三块：
   - 改显示名（走新的 `PATCH /api/users/me`）
   - 改密码（调已有的 `change-password`）
   - 头像：先做"填 URL"（`avatar_url`），不要做文件上传（附件链路刚被 T0 改成要鉴权，别混在一起）

2. ⚠️ **改密码有个现成的坑，必须一起处理。**
   现状（已核实）：`change_password` 里调了 `revoke_user_sessions()`，会 bump `token_version`，
   也就是**连调用者自己正在用的 token 一起作废**；而接口只返回 `{"detail": "Password changed."}`，
   **不发新 token**。结果是：用户改完密码，界面看着正常，**下一个请求直接 401 被踢出去**，而且没有任何解释。
   必须二选一（推荐前者）：
   - 改密成功后**用新密码重新签发一次 token** 并在响应里返回（前端替换 localStorage）；
   - 或者前端在成功后明确引导"密码已修改，请重新登录"，并主动跳转到登录页。
   无论选哪个，都要有测试断言"改密成功后当前用户仍可用（或明确收到需要重新登录的信号）"。

3. 后端 `PATCH /api/users/me`：允许改 `full_name` / `avatar_url`，**不允许**改 `role` / `is_active` / `email`。
   长度必须按列宽校验（`full_name` 150、`avatar_url` 500），否则 Postgres 上会 500（见 3.1）。

4. 改邮箱：**新邮箱必须验证后才生效**。建议流程：
   `POST /api/auth/change-email`（旧密码确认）→ 往新邮箱发 token →
   `POST /api/auth/verify-email-change` 才真正写入。复用 `auth_tokens` 表。
   在旧邮箱也发一封"你的邮箱正在被修改"的通知（防账号被顶）。

**不要做**
- 不要做头像上传。
- 不要允许直接改 `email` 字段。
- 不要在未确认"改密后当前会话怎么办"的情况下就发布——否则用户改完密码立刻被踢出，体验很糟；
  建议做法是改密成功后**用新密码自动重新签发一次 token**，而不是把用户扔到登录页。

**验收**：改密、改名、改头像、改邮箱（含验证）四条路径各有测试；长度越界返回 422 而非 500。

---

### T7 — SLA 可配置 + 工作时间

**现状（已核实）**
- 时限**写死在代码里**：`backend/app/config.py` 的 `SLA_FIRST_RESPONSE_MINUTES` / `SLA_RESOLUTION_MINUTES`。
- `backend/app/services/sla_service.py` **完全没有工作时间的概念**：
  周六凌晨建的单按自然时间算，到期时间会落在周末。
- 后果不是"不好用"，而是**客户看到的 SLA 数字不可信**。

**要做**
1. 把 SLA 配置放进已有的 `app_settings` 表（**不要新建表**）：
   - 每个优先级的首次响应/解决时限（分钟）
   - 工作时间：每周哪几天、起止时间、时区
   - 可选：是否把节假日算进去（先不做节假日表，留字段即可）
   在现有的 admin "Email & Alerts" 面板旁边加一个 "SLA" 标签页。
   配置解析顺序沿用现有约定：**DB → 环境变量 → 默认值**。
2. `sla_service` 改成按工作时间计算到期时间：跳过非工作时间、跨天/跨周正确推进。
   **必须写单元测试**，边界至少覆盖：周五下班前建单、周末建单、跨月、时区为 UTC+8 的情况。
3. **已有工单的 `first_response_due_at` / `resolution_due_at` 不要批量重算**——
   那会让历史报表突然变化。新配置只影响新工单，并在 UI 上说明这一点。

**不要做**
- 不要做"节假日日历"（这轮不做）。
- 不要改工单表的列结构（到期时间已经在表里了）。
- 不要重算历史工单。
- 不要做自动分配（见"明确不做"）。

**验收**：SLA 配置能从界面改并立即生效（新工单）；工作时间计算的单元测试覆盖上述边界；
旧工单的到期时间不变。

---

### T8 — 站内通知历史 + SLA 到点事件

**现状（已核实）**
- 实时推送存在（`/ws/notifications` + `WebSocketHub`），但**没有任何持久化**：
  刷新页面、断线重连期间的事件就永久丢了。坐席最容易抱怨这条（"我错过了一条"）。
- **没有任何模型存通知**（`backend/app/models/` 下没有 notification 相关表）。
- SLA 有 due time，但**到点了没有任何动作** —— 所以 SLA 目前是装饰品。

**要做**
1. 新模型 `notifications`（要迁移）：
   `id, user_id, type, title, body, ticket_id(nullable), read_at(nullable), created_at`
2. 在 `app/services/events.py` 的 `publish()` 里，**给有 `user_ids` 的事件落库**
   （注意：staff 广播不要给每个坐席各存一条，那会爆炸——只对**明确指名**的用户存，
   例如"分配给你了""你的工单被回复了"）。
3. 接口：`GET /api/notifications`（分页，默认未读优先）、`POST /api/notifications/read`
   （批量已读，body 传 id 列表或 `all: true`）。
4. 前端 Navbar 加铃铛 + 未读数 + 下拉列表；点击跳转到对应工单。
   **实时性复用现有的 `user_updated` 那套订阅机制**，不要再开一条 WebSocket。
5. SLA 到点事件：后台循环（每 60 秒）扫 `first_response_due_at` / `resolution_due_at` 已过
   且仍未响应/未解决的工单 → 写一条 `notifications`（给被指派人，没有则给全体 staff）+ 发布实时事件。
   **必须幂等**：同一张单同一个到期点只提醒一次（加 `sla_first_alerted_at` / `sla_resolution_alerted_at` 两列，要迁移）。

**不要做**
- 不要引入邮件告警之外的其它通道（短信/IM 这轮不做）。
- 不要给"全部工单更新"这类广播落库。
- 不要把通知做成任务队列（同边界 10）。

**验收**：断线期间产生的定向通知在重连后仍在；SLA 到点只提醒一次（跑两遍循环不产生第二条）；
分页与已读接口有测试。

---

### T9 — 搜索扩展

**现状（已核实）**
- `backend/app/controllers/tickets.py` 的 `list_tickets` 只对 `title` / `ticket_code` / `description`
  做 `ILIKE`，**不搜消息正文、不搜自定义字段**。
- `tickets.tags` 字段存了，但**不能当筛选条件**。
- 未提交的改动里已经加了 `backend/app/db/search.py`（`like_contains` 转义 `%` `_` `\`）——
  **新加的搜索必须复用它**，否则用户可以拿 `%` 把查询变成全表扫描。

**要做**
1. `list_tickets` 增加参数：
   - `tag`（单个标签，匹配 `tags` 里的逗号分隔项）
   - `ticket_type_id`
   - `app_id`
   - `created_from` / `created_to`（日期范围）
2. 搜索范围：**在现有基础上**加"消息正文"。
   注意 `ILIKE '%x%'` 在 Postgres 上**不走索引**，所以：
   - 必须复用 `like_contains()`
   - 消息搜索用 `EXISTS (SELECT 1 FROM messages ...)` 子查询，不要 JOIN 造成重复行
   - 在 README 里写明它的性能边界
3. 前端工单列表加上这些筛选器（tag 用 chips，日期用两个 date input）。
4. **自定义字段暂不搜**，除非用户明确要求 —— 它是 JSON 文本，跨库（SQLite / Postgres）语法不一致，
   要做就得先决定是否上 `jsonb` + GIN 索引，那是一次 schema 决策。

**不要做**
- 不要引入全文检索扩展（`pg_trgm` / `tsvector`）——那是独立的一次决策。
- 不要为了搜索改 `custom_fields_json` 的存储类型。
- 不要在列表接口里做 N+1（现在的批量取 user/app/type 的做法是对的，保持它）。

**验收**：新增筛选各有测试；`%` `_` 等特殊字符不会导致匹配异常或全表扫描；
分页信封和 `total` 与新筛选一致。

---

### T10 — 审计日志（只做写入侧，UI 以后再说）

**现状（已核实）**
- 除了工单会话里那些 `action_card` 消息（"Ticket status changed from … to …"），
  **没有任何审计记录**：谁改了谁的角色、谁关的单、谁看了附件，事后都对不上。
- **历史是补不回来的**——这是它必须在功能之前先做的唯一理由。

**要做**
1. 新模型 `audit_logs`（迁移）：`id, actor_id(nullable), actor_name, action, entity_type, entity_id,
   before_json(nullable), after_json(nullable), meta_json(nullable), created_at`。`created_at` 加索引。
2. 新建 `backend/app/services/audit.py`，暴露 `record(session, actor, action, entity, before, after, meta)`：
   - **只加不删**，不提供更新/删除接口
   - 绝不写敏感值（密码哈希、token、SMTP 密码）——写之前过一遍白名单
3. 接到这些动作上：角色变更、启用/停用用户、工单状态/优先级/指派变更、删除工单类型/app/宏/FAQ、
   设置变更（尤其是 SMTP 密码这类）、附件的下载（`meta` 里记 ticket_id）。
4. `GET /api/audit-logs`（admin，分页，可按 actor / action / entity 过滤）。**前端 UI 这轮不做。**

**不要做**
- 不要做 UI。
- 不要试图从 `action_card` 消息里"反向补历史"。
- 不要在审计写入失败时让主操作失败（审计失败只记 ERROR 日志）。
- 不要把审计表当作消息表复用它。

**验收**：上述每个动作各产生一条记录；改密/SMTP 密码不会把明文写进去（写测试断言 `before/after` 里
不含密码原文）；分页接口有测试。

---

### T11 — CSV 导出（有人要再做，可以先跳过）

**要做**
- `GET /api/tickets/export?format=csv`，admin/agent，**必须带日期范围**（默认最近 30 天），
  有硬上限（例如 10000 行，超出返回 422 提示收窄范围）。
- **流式输出**，不要先在内存里拼一个巨大的字符串。
- 列：单号、标题、状态、优先级、类别、客户、指派人、创建/首次响应/解决时间、SLA 状态、标签。
- CSV 注入防护：以 `= + - @` 开头的单元格前加 `'`。

**不要做**
- 不要做 Excel/xlsx。
- 不要导出消息正文和附件（体积 + 隐私）。
- 不要做无上限的"全部导出"。

---

## 五、明确不做（本轮范围之外）

接到这些需求时**直接回绝并说明原因**，除非用户明确改口：

| 不做 | 原因 |
|---|---|
| 自动分配工单 | 小团队共享队列就够；自动分配猜错比不分配更烦。**SLA 到点事件（T8）才是真正需要的那个** |
| 重写 `/api/analytics/summary` 为 SQL 聚合 | 它现在是 O(工单 × 坐席) 的内存计算，1 万单仍可用，10 万单才超时。**先做 T9 的日期范围**就够了 |
| 引入 Redis / Celery / 消息队列 | 见边界 10；T3 和 T8 都用数据库表 + 后台循环解决 |
| Docker / docker-compose | 用户明确要求 Nixpacks |
| 全文检索（pg_trgm / tsvector） | 独立的一次 schema 决策 |
| 前端状态管理库 / UI 组件库 | 现有 Tailwind + 手写组件已足够 |
| 多语言 i18n | 未提出需求 |
| 主题/暗色亮色切换 | 未提出需求 |
| 把 `custom_fields_json` 改成 jsonb | 独立决策，会牵动三处一致的表单契约 |

---

## 六、交付要求

每个任务完成后，回复里必须包含：

1. **改了什么**（文件路径 + 一句话说明为什么这么改）
2. **验证结果**：0.3 那四条命令的实际输出摘要（测试数、tsc/lint/build 结果）
3. **没做什么 / 拿不准的**：主动列出你跳过的部分和原因
4. **提交**：一个任务一个提交，英文提交信息，**不要 push**

如果中途发现任务描述与代码现状不符（这份文档是 2026-09-20 写的，代码会变），
**先停下来说明差异并问用户**，不要按自己的理解继续做。
