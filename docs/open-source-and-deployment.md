# 驿途（Yitu）开源发布与部署上线指南

本指南分两大部分：**A. 推送到开源社区（以 GitHub 为例）**、**B. 部署上线（单机 Docker Compose 生产方案，附上云路径）**。所有命令均在项目根目录 `yitu/` 下执行。

---

## 〇、项目现状体检（已核查）

先把好消息和待办讲清楚：

| 检查项 | 现状 | 结论 |
|--------|------|------|
| `.env` 是否被 git 跟踪 | 未跟踪（`.gitignore` 已含 `.env`） | ✅ 安全 |
| git 历史是否泄露 `.env`/密钥 | 未发现；`credential_models.py` 等是业务「末次 Mile 凭证」模块，非密钥 | ✅ 安全 |
| `node_modules/`、`frontend/dist/` | 未跟踪 | ✅ 安全 |
| 远程仓库 | 无（`git remote -v` 为空） | ⬜ 需新建 |
| 开源许可证 | 无 `LICENSE` 文件 | ⬜ 需补 |
| IDE/个人配置（`.idea/`、`.trae/`、`.CLAUDE`） | **曾被跟踪**，已执行 `git rm --cached` 移出 | ✅ 本次已处理 |
| 生产部署文件 | 无 | ✅ 本次已在 `deploy/` 补齐 |
| 生产安全项 | JWT 密钥、取件码 pepper 有「开发默认值」，`.env.example` 未列出 | ⚠️ 上线必须覆盖 |

> 结论：密钥没有泄露风险，可以放心开源；主要工作是补社区化文件（LICENSE/README/贡献指南）和生产配置。

---

# A. 推送到开源社区

## A1. 开源前清理（关键）

### 1. 忽略个人/IDE 配置（本次已做）

`.idea/`、`.trae/`、`.CLAUDE`、`reasonix.toml`、`overview.md` 属于个人工具状态或内部讲解稿，不适合公开。已：

- 在 `.gitignore` 增加忽略规则；
- 执行 `git rm -r --cached .idea .trae .CLAUDE` 把它们**移出版本库但保留本地文件**。

> 说明：`overview.md` 已在旧 `.gitignore` 中（内部深度讲解稿）。若你希望开源时**公开架构讲解**作为卖点，可把它改名为 `docs/architecture-deep-dive.md` 并取消忽略——这对简历/作品集项目反而是加分项。建议公开，见 A5。

### 2. 全仓密钥扫描（推送前必跑一次）

```bash
# 在项目根目录执行，扫描所有被跟踪文件里的真实密钥特征
git grep -nE "sk-[A-Za-z0-9]{20,}|AKID[A-Za-z0-9]+|BEGIN (RSA|OPENSSH) PRIVATE KEY|api[_-]?key\s*[:=]\s*['\"][A-Za-z0-9]{16,}" $(git rev-list --all | head -50) -- 2>/dev/null
```

当前 `.env` 里的真实密钥（DeepSeek/百炼/MinerU/COS）从未入库，历史也干净，所以**无需改写历史**。若未来误提交过密钥，仅删文件不够——需用 `git filter-repo` 清理历史并**立即轮换所有泄露密钥**。

### 3. 确认演示身份说明

README 里写了 demo 账号密码 `YituDemo2026!`。开源保留没问题（本地演示用），但**生产环境必须**：
- 设 `YITU_APP_PROFILE=production`（关闭 demo 自动建号与固定取件码）；
- 覆盖 `YITU_JWT_SECRET` 和 `YITU_PICKUP_CODE_PEPPER`。

生产 compose 已强制 `APP_PROFILE=production`（见 `deploy/docker-compose.prod.yml`）。

## A2. 补开源社区化文件

开源仓库的「门面」直接影响别人是否愿意 star。建议补齐以下文件（本次已生成 LICENSE，其余按需）：

### LICENSE（必选）

作品集/简历项目推荐 **MIT**（最宽松、最常见）。已在仓库根目录生成 `LICENSE`（MIT，2026）。若想要求衍生作品也开源，可换 **Apache-2.0**（含专利授权条款，更适合企业级项目）或 **GPL-3.0**。

> 换许可证：把 LICENSE 内容替换为对应文本，并同步更新 `package.json` 的 `license` 字段（当前前端 package.json 未声明 license，可加 `"license": "MIT"`）。

### README.md（必改）

当前 README 只有本地运行说明。开源版建议补充：

- 一句话简介 + 2~3 个**卖点 bullet**（AI 对话下单、状态机履约约束、RAG 混合检索、LangGraph interrupt 人工确认）；
- 架构图 / 截图（GIF 演示 AI 下单效果最佳）；
- 技术栈表格（FastAPI / LangGraph / PostgreSQL+pgvector / Celery / Vue3 / Element Plus）；
- 「快速开始」（3 条命令跑起来）；
- 文档索引（链接到 `docs/`）；
- 目录结构说明；
- License 声明。

### 可选但推荐

- `CONTRIBUTING.md`：如何提 PR、代码规范（中文注释、中文 commit、ruff/mypy）；
- `.github/`：Issue 模板、PR 模板、GitHub Actions CI（跑 ruff + pytest）；
- `docs/` 里已有的 `technical-highlights.md`、`langgraph-flow.md`、`agent-rag-architecture.md` 都是很好的技术宣传材料。

## A3. 在 GitHub 创建仓库并推送

### 方式一：gh CLI（推荐，一条命令搞定）

```bash
# 1. 安装并登录（首次）
gh auth login

# 2. 在项目根目录，创建并推送（public 开源）
gh repo create yitu-logistics --public --source=. --remote=origin --push \
  --description "有真实履约约束的 AI 智能物流平台：LangGraph 单图编排 + 状态机 + RAG + interrupt 人工确认"
```

### 方式二：网页建仓 + 命令行推送

1. 在 GitHub 网页 New repository，名字如 `yitu-logistics`，**不要**勾选 Initialize with README（避免冲突）；
2. 本地执行：

```bash
git add -A
git commit -m "docs: 补充开源许可证、部署模板与开源发布指南"
git branch -M main
git remote add origin https://github.com/<你的用户名>/yitu-logistics.git
git push -u origin main
```

> 当前分支是 `codex/jianli`，开源建议推 `main`。可用 `git branch -M main` 重命名。

### 推送后再确认一次

```bash
# 打开仓库设置 → Settings → Secrets，确认没有 .env 内容出现在任何文件里
gh secret list          # 确认 CI 用的 secret（如有）
git ls-files | grep -E "\.env$"   # 必须为空
```

## A4. 国内开源社区（可选）

若希望国内访问更快，可**同步镜像**到：

- **Gitee（码云）**：`git remote add gitee https://gitee.com/<用户名>/yitu.git`，推送后可在 Gitee 申请「推荐项目」；
- **GitCode（CSDN）** / **AtomGit（开放原子）**：类似。

多远程推送：`git push origin main && git push gitee main`，或 `git remote set-url --add origin <gitee地址>` 后一次 push 多端。

## A5. 作品集项目的曝光建议（可选）

这个项目技术含量很高（LangGraph 单图编排 + interrupt 人工确认、状态机履约、双路 RAG、异步任务与通知可靠性），非常适合作为简历项目。建议：

1. README 顶部放一段 **30 秒演示 GIF**（AI 对话下单 → 确认卡片 → 建单 → 轨迹）；
2. 把 `overview.md` 公开为 `docs/architecture-deep-dive.md`（深度技术讲解，面试可直接讲）；
3. 打 Release Tag：`git tag -a v0.1.0 -m "首个开源版本" && git push origin v0.1.0`；
4. 在 `docs/technical-highlights.md` 基础上写一篇技术博客，README 里挂链接。

---

# B. 部署上线

## B1. 架构总览

生产用一条 `docker compose` 拉起 5 个服务：

```
                    ┌─────────────┐
        用户 ──────▶ │  frontend   │  Nginx :80（唯一对外端口）
                    │ (Vue 静态)   │
                    └──────┬──────┘
                           │ /api/ 反向代理（含 SSE 长连接）
                    ┌──────▼──────┐
                    │     api     │  FastAPI + uvicorn(2 workers)
                    │  (FastAPI)  │  启动时自动 alembic 迁移
                    └──────┬──────┘
                           │
            ┌──────────────┼───────────────┐
            ▼              ▼                ▼
      ┌──────────┐   ┌──────────┐    ┌────────────┐
      │    db    │   │  redis   │    │   worker   │
      │ pgvector │   │ (Celery  │    │ Celery+beat│
      │  pg16    │   │  broker) │    │ (PDF解析等) │
      └──────────┘   └──────────┘    └────────────┘
                           │
                    ┌──────▼──────┐
                    │  腾讯云 COS  │  对象存储（知识库 PDF）
                    │ 百炼/MinerU │  外部 AI 服务
                    └─────────────┘
```

与本地 `compose.yaml` 的差异：**去掉 MinIO**（生产用 COS）、**DB/Redis 不暴露宿主机端口**、**全部 `restart: unless-stopped`**、**新增 Nginx 前端**、**强制 production profile**。

## B2. 服务器准备

- 一台云服务器（腾讯云/阿里云，2 核 4G 起步；跑 embedding + LLM 是调外部 API，本机不需要 GPU）；
- 安装 **Docker** 与 **Docker Compose 插件**；
- 一个**域名**（用于 HTTPS 和支付宝回调），解析到服务器 IP；
- 放行安全组端口：80、443（22 仅限你的 IP）。**不要**放行 5432/6379/8000。

## B3. 配置生产环境变量

```bash
# 在服务器上，项目根目录
cp deploy/.env.production.example deploy/.env.production
vi deploy/.env.production
```

**必须修改的项**（模板里标了 `CHANGE_ME`）：

| 变量 | 说明 | 生成方式 |
|------|------|---------|
| `POSTGRES_PASSWORD` / `YITU_DATABASE_URL` | 数据库密码，两处要一致 | `openssl rand -base64 24` |
| `YITU_JWT_SECRET` | JWT 签名密钥（**不设则用源码默认值，任何人都能伪造令牌**） | `openssl rand -hex 32` |
| `YITU_PICKUP_CODE_PEPPER` | 取件码哈希 pepper | `openssl rand -hex 32` |
| `YITU_KNOWLEDGE_S3_*` | 腾讯云 COS 桶名和密钥 | 云控制台获取 |
| `YITU_EMBEDDING_API_KEY` | 阿里云百炼 Key | 百炼控制台 |
| `YITU_MINERU_TOKEN` | MinerU 解析 Token | mineru.net |
| `YITU_AGENT_MODEL_API_KEY` | DeepSeek 等对话模型 Key | 对应平台 |

> `deploy/.env.production` 已加入 `.gitignore`，不会被提交。

## B4. 启动生产服务

```bash
# 在项目根目录（deploy/docker-compose.prod.yml 内用 ../backend、../frontend 相对路径）
docker compose -f deploy/docker-compose.prod.yml \
  --env-file deploy/.env.production up -d --build

# 查看状态（5 个服务应全为 healthy/running）
docker compose -f deploy/docker-compose.prod.yml ps

# 看日志
docker compose -f deploy/docker-compose.prod.yml logs -f api
```

启动后：

- 前端：`http://<服务器IP>/`
- 健康检查：`http://<服务器IP>/api/v1/health`
- 数据库迁移由 api 容器启动时自动执行（`alembic upgrade head`）。

## B5. 配置 HTTPS（必做）

生产环境必须 HTTPS（登录令牌、支付回调都依赖）。用 Nginx + Let's Encrypt：

```bash
# 安装 certbot
apt-get install -y certbot python3-certbot-nginx   # Debian/Ubuntu

# 申请证书（会自动改 Nginx 配置；或用独立的宿主机 Nginx 反代 + certonly）
certbot --nginx -d your-domain.com
```

推荐架构：在**宿主机**再放一层 Nginx（或用 Caddy 自动 HTTPS）终止 TLS，再反代到容器的 80 端口。若用 Caddy，两行配置即可自动签证书：

```
your-domain.com {
    reverse_proxy localhost:80
}
```

> SSE 流式输出注意：`deploy/nginx.conf` 已设置 `proxy_buffering off;`、`proxy_read_timeout 300s;`，HTTPS 层也要保留这些，否则 AI 流式回复会被缓冲成「整段才出现」。

## B6. 验收清单（上线后逐项确认）

**功能**
- [ ] `GET /api/v1/health` 返回 200
- [ ] 前端页面能打开、能登录
- [ ] AI 对话能流式逐字返回（验证 SSE 没被缓冲）
- [ ] AI 对话下单 → 确认卡片 → 建单全链路通
- [ ] 管理员上传 PDF → Worker 异步解析 → 发布 → 知识检索有结果

**安全**
- [ ] `YITU_APP_PROFILE=production`（无 demo 账号、无固定取件码 123456）
- [ ] `YITU_JWT_SECRET`、`YITU_PICKUP_CODE_PEPPER` 已换成随机值
- [ ] 5432/6379 端口不对公网开放（`docker compose ps` 确认无端口映射）
- [ ] 支付仍为 `mock`（接支付宝前不要切 `alipay`）
- [ ] 服务器防火墙/安全组只开 22/80/443

**可靠性**
- [ ] `docker compose restart api` 后服务自愈、迁移幂等
- [ ] 重启后数据不丢（PostgreSQL 用 named volume `postgres_data`）
- [ ] Worker 离线时任务进 Redis 队列，恢复后继续消费

## B7. 日常运维命令

```bash
# 更新代码后重新发布
git pull
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.production up -d --build

# 备份数据库（强烈建议加定时任务）
docker compose -f deploy/docker-compose.prod.yml exec db \
  pg_dump -U yitu yitu | gzip > backup_$(date +%F).sql.gz

# 查看死信 / 重放（业务运维）
# 通过管理员接口 /api/v1/admin/dead-letters（见 README）
```

数据库备份建议配 cron：每日 `pg_dump` 上传到 COS，保留 7~30 天。

## B8. 上云 / 扩展路径（流量增长后）

单机 Compose 适合演示和中小流量。进一步演进：

1. **托管数据库**：把 PostgreSQL/Redis 换成云厂商 RDS / 云数据库（自动备份、主从、高可用），应用连外部地址即可；
2. **对象存储**：已用腾讯云 COS，无需自建 MinIO；
3. **容器编排**：把 `api`/`worker` 做成镜像推到镜像仓库（腾讯云 TCR / 阿里云 ACR），用 **Kubernetes** 或云容器服务部署，`api` 可水平多副本（注意：多副本时 `YITU_AGENT_CHECKPOINTER_BACKEND=postgres` 已强制，图中断点 / 会话状态走 PG 共享，无状态副本可安全扩缩）；
4. **CI/CD**：GitHub Actions 推镜像 → 服务器 `docker compose pull && up -d`，或接云厂商自动部署；
5. **静态前端**：`frontend/dist/` 可直接传到 **腾讯云 COS 静态网站 + CDN**，只把 `/api` 反代到后端，更省服务器资源。

---

## 附：本次为部署/开源新增的文件

| 文件 | 作用 |
|------|------|
| `LICENSE` | MIT 开源许可证 |
| `deploy/docker-compose.prod.yml` | 生产编排（5 服务，无 MinIO，端口不外露） |
| `deploy/.env.production.example` | 生产环境变量样例（含 JWT/pepper/COS/AI 密钥占位） |
| `deploy/frontend.Dockerfile` | 前端多阶段构建（Vue 编译 → Nginx 托管） |
| `deploy/nginx.conf` | Nginx 配置：SPA 回退 + API 反代 + SSE 流式关键参数 |
| `.dockerignore` | 构建上下文瘦身（排除 node_modules/.git/.env 等） |
| `.gitignore`（更新） | 新增忽略 `.env.*`、`.idea/`、`.trae/`、`.CLAUDE`、生产密钥文件 |

> 生产密钥文件 `deploy/.env.production` 需你自行从 example 复制填写，**不要**提交。