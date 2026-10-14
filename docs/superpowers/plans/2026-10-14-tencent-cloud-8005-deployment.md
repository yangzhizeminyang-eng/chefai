# 腾讯云 8005 生产部署加固实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 AI 厨娘现有 Docker Compose 部署整理为适配腾讯云 Ubuntu 24.04、2 核 2GB、Docker 27.5.1 的生产配置，并固定通过 `YOUR_SERVER_IP:8005` 对外提供服务。

**Architecture:** 保留根 Compose 作为本地开发入口，生产通过 `docker-compose.yml` 与 `docker-compose.prod.yml` 叠加启动。生产只发布 Nginx 的宿主机 `8005`，API、PostgreSQL、Redis 置于内部数据网络；前端镜像在本地构建并传输，服务器只构建较轻的后端镜像。

**Tech Stack:** Docker Compose v2、Nginx、FastAPI/Uvicorn、PostgreSQL 16 + pgvector、Redis 7、Node 22 多阶段前端镜像、Ubuntu 24.04。

## Global Constraints

- 公网入口固定为 `TCP 8005`，后端 `8000`、PostgreSQL `5432`、Redis `6379` 不得发布到宿主机。
- 生产服务器按 `2 vCPU / 2 GB RAM / 50 GB SSD / 4 Mbps` 配置资源上限，保留系统、Docker 和 swap 余量。
- 生产必须使用 `.env.production` 与 `backend/.env` 注入凭据，禁止使用 Compose 中的生产默认弱口令。
- 前端在本地构建后 `docker save`/`docker load`，服务器不执行 Node 构建。
- 不删除命名卷，不执行 `docker compose down -v`。

---

### Task 1: 生产网络与资源约束

**Files:**
- Modify: `docker-compose.yml`
- Modify: `docker-compose.prod.yml`

- [ ] **Step 1: 定义 edge/data 网络**

让 `web` 同时加入 `edge` 和 `data`，让 `api`、`db`、`redis` 只加入 `data`，并将 `data` 设置为 `internal: true`。

- [ ] **Step 2: 为生产服务加入限制**

在生产覆盖层为 `web`、`api`、`db`、`redis` 增加 `cpus`、`mem_limit`、`mem_reservation`、健康检查和日志轮转；总内存上限控制在约 1.7GB 以内。

- [ ] **Step 3: 取消生产 API 宿主端口与前端构建**

继续使用 `ports: !reset []` 清除 API 的 `8000` 发布，并使用 `build: !reset null` 确保生产 web 只使用已加载的镜像。

- [ ] **Step 4: 用 Compose 配置校验**

运行：

```powershell
docker compose --env-file .env.production.example -f docker-compose.yml -f docker-compose.prod.yml config --quiet
```

预期：命令成功退出，组合配置无语法错误。

### Task 2: 后端非 root 运行

**Files:**
- Create: `backend/docker-entrypoint.sh`
- Modify: `backend/Dockerfile`
- Modify: `docker-compose.prod.yml`

- [ ] **Step 1: 添加运行用户和 writable 目录**

在运行镜像创建 `app` 用户，准备 `/app/uploads` 与 `/app/assets/recipe_covers`，并保留 root 入口用于启动时修复挂载目录权限。

- [ ] **Step 2: 添加入口脚本**

入口脚本只修复上传目录和封面目录权限，然后使用 `gosu app` 执行 Alembic 与 Uvicorn，保证应用进程不以 root 运行。

- [ ] **Step 3: 增加生产只读语料挂载**

将 `backend/data` 以只读方式挂载到 `/app/data`，将 `backend/assets` 挂载到 `/app/assets`，上传图片继续使用命名卷。

- [ ] **Step 4: 检查 Dockerfile 关键指令**

确认 `EXPOSE 8000`、健康检查 URL、迁移命令和 `APP_PORT` 默认值保持一致。

### Task 3: 前端构建与 Nginx 健康检查

**Files:**
- Modify: `Dockerfile.web`
- Modify: `nginx/nginx.conf`
- Modify: `docker-compose.yml`

- [ ] **Step 1: 对齐 Node 引擎版本**

将构建阶段从 Node 20 调整到满足前端 `engines` 的 Node 22，并为低内存构建设置安全的 `NODE_OPTIONS`。

- [ ] **Step 2: 添加网关健康端点**

在 Nginx 增加 `GET /healthz`，返回纯文本 `ok`，不依赖 API，供容器健康检查和外部部署探活使用。

- [ ] **Step 3: 增加 web 容器健康检查**

用容器内 `wget` 检查 `/healthz`，并让生产 `depends_on` 同时等待 API 健康。

### Task 4: 腾讯云部署指南

**Files:**
- Create: `项目开发文档/18-腾讯云8005生产部署指南-V1.0.md`
- Modify: `.env.production.example`

- [ ] **Step 1: 写明服务器资源与安全组**

记录 Ubuntu 24.04、Docker 27.5.1、IP `YOUR_SERVER_IP`、swap、磁盘和只开放 `22/8005` 的规则。

- [ ] **Step 2: 写明镜像搬运和部署命令**

覆盖本地构建、镜像导出、上传、服务器加载、Compose 校验、启动、种子初始化和健康检查。

- [ ] **Step 3: 写明运维和回滚**

覆盖日志、资源/磁盘检查、数据库备份、恢复注意事项、镜像回滚和禁止删除卷的操作。

### Task 5: 最终验证

**Files:**
- No additional files.

- [ ] **Step 1: Shell 与 Compose 静态校验**

运行 `bash -n scripts/deploy.sh` 与生产 Compose `config --quiet`。

- [ ] **Step 2: 检查端口与资源配置**

从渲染后的 Compose 配置确认只有 `8005:80` 对外发布，并确认 API、数据库、Redis 没有宿主端口。

- [ ] **Step 3: 检查 Git diff**

确认只包含部署相关变更和新部署指南，保留用户已有的 `scripts/deploy.sh` 与 `.workbuddy/memory/2026-10-14.md` 修改。
