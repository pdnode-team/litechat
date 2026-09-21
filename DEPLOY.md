# 在 Dokploy 上部署 LiteChat（不写 Dockerfile）

本项目是前后端分离的 monorepo：`backend/`（Litestar + PostgreSQL）和 `frontend/`（React + Vite 静态站）。
下面全部使用 Dokploy 自带的 **Nixpacks** 构建，仓库里只有构建描述文件，没有 Dockerfile。

> 说明：Dokploy 本身仍然把应用跑在容器里（Nixpacks 的产物就是镜像）。
> “不用 Docker”在这里指**不需要你写和维护 Dockerfile**，Dokploy 会根据 `nixpacks.toml` 自动构建。

---

## 结论先行：一个域名 + 路径路由

推荐**单域名**方案，也就是浏览器只访问一个地址：

| 路径 | 去向 | 端口 |
|---|---|---|
| `/` | 前端静态站 | 80 |
| `/api` | 后端 API | 8000 |
| `/ws` | 后端 WebSocket（实时推送） | 8000 |

这样前端调用的是**同源**的 `/api` 和 `/ws`，因此：

- 不需要配 CORS
- 不需要给前端传 API 地址（`VITE_API_BASE_URL` 保持默认）
- WebSocket 直接可用

（另一个选择是前后端各用一个域名，那就必须设置 `VITE_API_BASE_URL` 和 `ALLOWED_ORIGINS`，见文末“备选方案”。）

---

## 第 0 步：准备

1. 把仓库推到 GitHub / GitLab / Gitea（Dokploy 需要能拉到代码）。
2. 生成一个 JWT 密钥，后面要用：

   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

3. 准备一个域名（例如 `support.example.com`），A 记录指向 Dokploy 所在服务器。
   Dokploy 会用 Let's Encrypt 自动签发证书。

---

## 第 1 步：创建数据库

Dokploy → 你的 Project → **Create Service → Database → PostgreSQL**。

创建后进入该数据库页面，记下 **Internal Connection URL**，形如：

```
postgres://litechat:xxxxxxxx@dokploy-postgres-xxxx:5432/litechat
```

后端用的是 SQLAlchemy 异步驱动，需要把协议头改掉：

```
postgresql+asyncpg://litechat:xxxxxxxx@dokploy-postgres-xxxx:5432/litechat
```

> 后端已经把 `asyncpg` 作为依赖，不需要额外安装。
> 一定要用**内部**地址（同一个 Dokploy 网络内），不要用公网地址。

---

## 第 2 步：后端应用

Dokploy → Project → **Create Service → Application**，连上你的仓库。

### General（常规）

| 字段 | 值 |
|---|---|
| Name | `litechat-backend`（自定义） |
| Branch | `master`（或你的主分支） |
| **Base Directory / 根目录** | `backend` |
| Build Type | **Nixpacks** |

> 部分 Dokploy 版本这个字段叫 `Base Directory`，旧版本可能没有。
> 如果没有这个字段，见文末的「没有 Base Directory 字段怎么办」。

构建行为由 `backend/nixpacks.toml` 决定：安装 uv 依赖，启动时先跑
`alembic upgrade head` 再拉起 uvicorn（端口取 `$PORT`，默认 8000）。

### Environment（环境变量）

必填：

```ini
JWT_SECRET_KEY=<第 0 步生成的密钥>
ENVIRONMENT=production
DATABASE_URL=postgresql+asyncpg://litechat:xxxxxxxx@dokploy-postgres-xxxx:5432/litechat
ALLOWED_ORIGINS=https://support.example.com
PUBLIC_APP_URL=https://support.example.com
TRUST_PROXY_HEADERS=true
ENABLE_API_DOCS=false
```

可选（按需）：

```ini
# 首次启动自动创建管理员（也可以建好后再用界面创建，见第 6 步）
ADMIN_EMAIL=you@example.com
ADMIN_PASSWORD=ChangeMe123
ADMIN_USERNAME=admin
ADMIN_NAME=System Administrator

# 限流（默认值即下面这些）
RATE_LIMIT_ENABLED=true
RATE_LIMIT_LOGIN=10
RATE_LIMIT_REGISTER=5

# 日志：默认 INFO 输出到 stdout（Dokploy 会收集）。
# 出错时排查 500 用得上，前端看到的 "reference: xxxxx" 就是这里打出来的 request id。
LOG_LEVEL=INFO
# 如果平台不留 stdout 日志，可以再加一个轮转文件（可选）
# LOG_FILE=/app/logs/litechat.log
```

关于 `TRUST_PROXY_HEADERS=true`：打开后限流优先读 `X-Real-IP`，否则取 `X-Forwarded-For` 的**最右一跳**（Traefik 追加的真实对端）。不要用最左跳，那是客户端可伪造的。
只有确定前面有可信代理时才开（这里是 Traefik，安全）。
`FORWARDED_ALLOW_IPS` 默认是 `*`（容器只被 Traefik 访问时可以）。如果后端端口对其他网络暴露，改成 Traefik 的地址。

关于邮件：**SMTP 不一定要写在这里**，可以在应用里配置（见第 7 步）。
数据库里的设置优先于环境变量。

### Advanced（高级）→ Volumes（持久化）

**必须加一个卷**，否则重新部署时用户上传的附件会全部丢失：

| 字段 | 值 |
|---|---|
| Volume Name | `litechat-uploads` |
| Mount Path | `/app/uploads` |

### Ports

不需要对公网暴露端口，Traefik 走内部网络即可（下面的域名配置会指定容器端口 8000）。

### Cluster Settings

**Replicas 保持 1。**

> 实时推送（WebSocket）的连接表、限流计数器都在**进程内存**里。
> 多副本时客户端只会收到「它连上的那个副本」发出的事件。
> 要横向扩展，需要把这两者换成 Redis 之类的共享存储（见 README 的 Known gaps）。

---

## 第 3 步：前端应用

再建一个 Application，同一个仓库。

### General

| 字段 | 值 |
|---|---|
| Name | `litechat-frontend` |
| Branch | `master` |
| **Base Directory** | `frontend` |
| Build Type | **Nixpacks** |
| **Publish Directory** | `dist` |

`dist` 是 Vite 的构建产物目录。设置 Publish Directory 后，Dokploy 会把该目录
交给它自带的 nginx 镜像托管，**对外端口是 80**。

`frontend/nixpacks.toml` 已经指定了 `nodejs_22` + `pnpm`，以及
`pnpm install --frozen-lockfile` 和 `pnpm build`。

### Environment

单域名方案下**不需要**任何变量。前端默认请求同源的 `/api` 和 `/ws`。

---

## 第 4 步：域名与路由（关键）

先给**前端**加域名：

| 字段 | 值 |
|---|---|
| Host | `support.example.com` |
| Path | `/` |
| Container Port | `80` |
| HTTPS | 开 |
| Certificate | `letsencrypt` |

再给**后端**加**两条**域名记录（Host 相同，Path 不同）：

| # | Host | Path | Strip Path | Container Port |
|---|---|---|---|---|
| 1 | `support.example.com` | `/api` | **关闭** | `8000` |
| 2 | `support.example.com` | `/ws` | **关闭** | `8000` |

**Strip Path 一定要关闭。** 后端自己的路由就是 `/api/...` 和 `/ws/...`，
如果开启会把前缀剥掉，导致所有请求 404。

Applications 的域名配置是 Traefik 文件热加载，改完即时生效，不用重新部署。

---

## 第 5 步：部署

按顺序点 **Deploy**：先后端，再前端。

后端首次部署的日志里应该能看到：

```
[start] applying database migrations...
INFO  [alembic.runtime.migration] Running upgrade  -> 47311753a164, initial schema
...
[start] launching API on port 8000
```

三个迁移会依次执行，把表结构和 `app_settings` 建好。

---

## 第 6 步：第一个管理员

数据库是空的，所以有两个办法：

**A. 用界面（推荐）**
打开 `https://support.example.com`。前端会探测到系统还没有用户，
自动显示「初始化 LiteChat → 创建管理员」表单，填完即成为管理员。
这个入口在系统里出现第一个用户后自动锁定。

**B. 用环境变量**
在第 2 步设置 `ADMIN_EMAIL` + `ADMIN_PASSWORD` 后重新部署。

---

## 第 7 步：配置邮件（在应用里配，不用改环境变量）

用管理员登录 → 右上角进入 **Admin Console** → **Email & Alerts** 标签：

- SMTP 主机 / 端口 / 用户名 / 密码 / 发件人
- STARTTLS（587 端口开；465 隐式 TLS 关）
- App base URL（邮件里链接用的地址，填 `https://support.example.com`）
- 四个通知开关：新工单、新回复、被分配、解决/关闭
- 支持邮箱（可选，额外收新工单通知）
- **Send test** 按钮可以直接验证配置

密码会**加密存库**（密钥由 `JWT_SECRET_KEY` 派生），接口只返回“是否已设置”，永不回显。

> 注意：这些设置存在数据库里，**优先级高于环境变量**。改了 `JWT_SECRET_KEY` 会导致已存的
> SMTP 密码无法解密，需要重新填一次。

---

## 上线检查清单

- [ ] `JWT_SECRET_KEY` 已设置（生产环境没设置会直接启动失败，这是故意的）
- [ ] `ENVIRONMENT=production`
- [ ] `ENABLE_API_DOCS=false`（`/schema` 不再对公网开放）
- [ ] `ALLOWED_ORIGINS` 是你的真实域名，不是 `*`
- [ ] `TRUST_PROXY_HEADERS=true`
- [ ] 后端挂了 `/app/uploads` 卷
- [ ] 后端 Replicas = 1
- [ ] 三个域名记录：`/`→80、`/api`→8000、`/ws`→8000，且 Strip Path 全关
- [ ] HTTPS 证书已签发
- [ ] 邮件测试信能收到
- [ ] 建单后浏览器不刷新，另一个浏览器里的客服队列能立刻出现该工单（实时验证）

---

## 常见问题

**构建时 `pnpm install` 报 lockfile 版本错误**
仓库里的 `pnpm-lock.yaml` 是 `lockfileVersion: '9.0'`，pnpm 9/10/11 都能读。
如果 Nixpacks 拉到的 pnpm 太旧，在环境变量里加 `NIXPACKS_PKGS=pnpm`，或把
`nixpacks.toml` 的 `nixPkgs` 改成具体的 pnpm 版本。

**后端启动报 `FATAL: JWT_SECRET_KEY environment variable MUST be explicitly set`**
这是 `ENVIRONMENT=production` 的安全检查，按第 2 步补上变量即可。

**数据库连接失败**
确认用的是 Dokploy 的**内部**地址，并且协议头是 `postgresql+asyncpg://`（不是 `postgres://`）。

**`/api` 返回 404**
九成是后端域名记录上开了 **Strip Path**，关掉它。

**WebSocket 连不上（实时没反应）**
确认 `/ws` 那条域名记录存在且端口是 8000。
另外注意实时是**单进程**的，副本数必须是 1。

**重新部署后上传的附件没了**
没挂 `/app/uploads` 卷。

**想改限流参数**
加 `RATE_LIMIT_LOGIN` / `RATE_LIMIT_REGISTER` 等环境变量后重新部署。

---

## 备选方案：前后端用不同域名

如果希望前后端分开（例如 `support.example.com` + `api.example.com`）：

1. 后端加域名记录：Host `api.example.com`，Path `/`，端口 8000。
2. 后端环境变量改成：
   ```ini
   ALLOWED_ORIGINS=https://support.example.com
   PUBLIC_APP_URL=https://support.example.com
   ```
3. 前端加**构建时**变量（Vite 会在构建时把它打进包里，必须重新构建才生效）：
   ```ini
   VITE_API_BASE_URL=https://api.example.com/api
   VITE_WS_ORIGIN=wss://api.example.com
   ```

前端代码已经支持这两个变量（见 `frontend/.env.example`），默认值仍是同源，所以单域名方案不用配。

---

## 没有 Base Directory 字段怎么办

如果当前 Dokploy 版本在 General 里找不到 Base Directory，可以用官方的
`NIXPACKS_*` 环境变量（写在 Environment 标签里）绕过，让构建和启动都从仓库根目录
切到子目录执行。

**后端：**

```ini
NIXPACKS_PKGS=python311,uv
NIXPACKS_INSTALL_CMD=sh -c "cd backend && uv sync --frozen --no-dev"
NIXPACKS_START_CMD=sh -c "cd backend && sh start.sh"
```

**前端：**

```ini
NIXPACKS_PKGS=nodejs_22,pnpm
NIXPACKS_INSTALL_CMD=sh -c "cd frontend && pnpm install --frozen-lockfile"
NIXPACKS_BUILD_CMD=sh -c "cd frontend && pnpm build"
```

前端的 **Publish Directory** 填 `frontend/dist`。

---

## 本地验证（可选）

部署前想先在本机确认前后端能跑通：

```bash
# 后端
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000

# 前端（另开一个终端）
cd frontend
pnpm install
pnpm dev            # http://127.0.0.1:3000
```

前端开发服务器会把 `/api` 和 `/ws` 代理到 `127.0.0.1:8000`；
目标地址可以通过 `DEV_API_TARGET` 环境变量覆盖。
