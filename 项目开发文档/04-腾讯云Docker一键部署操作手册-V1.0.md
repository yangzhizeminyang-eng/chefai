# AI 厨娘・智能烹饪助手 —— 腾讯云 Linux 服务器 Docker 一键部署操作手册

> 🏠 **所属知识库**：AI 厨娘・智能烹饪助手 ｜ **节点位置**：04｜设计与研发交付物 → 部署运维文档
> 📄 **文档编号**：B-D6-1 ｜ **版本**：V1.0 ｜ **状态**：🟡 待甲方评审
> 👤 **产出方**：乙方（运维 + 后端） ｜ **审核方**：甲方产品
> 📅 **日期**：2026-10-05
> 📚 **上游依据**：《架构设计与数据库设计文档 V1.0》（B-D3）、《PRD V1.0》（B-D1）
> ⚖️ **一致性声明**：本文档仅覆盖 B-D3 已定义的技术栈（Docker Compose 单机：Nginx + FastAPI + LangGraph + PostgreSQL 16(pgvector) + Redis），**不引入新技术**；K8s 为 PRD 预留项，MVP 不使用

---

## 0. 文档说明

| 项 | 内容 |
| --- | --- |
| **适用环境** | 腾讯云 CVM（Linux）单机部署，Docker Compose 编排 |
| **适用阶段** | 阶段一（Web 原型，内网/本机演示，**不对外提供服务**）与阶段二（小程序 MVP，需备案 + HTTPS 域名） |
| **部署产物** | 4 个容器：`nginx` / `api` / `postgres` / `redis` + 3 个数据卷 |
| **一键入口** | `bash scripts/deploy.sh` 与 `bash scripts/rollback.sh` |
| **读者** | 运维、后端、测试 |

### 0.1 阶段差异（重要）

| 项 | 🚀 阶段一 | 📦 阶段二 |
| --- | --- | --- |
| 对外提供服务 | ❌ **否**（仅内网 IP / 本机访问） | ✅ 是 |
| 域名与 HTTPS | ❌ 不需要 | ✅ **必须**（小程序要求 HTTPS） |
| 备案 | ❌ 不需要 | ✅ **必须**（小程序备案 + 生成式 AI 备案，RL-12/RL-13） |
| 前端 | Web 演示端（**Vue 3 + Element Plus**，静态产物） | 小程序（uni-app 产物由微信开发者工具上传，**不经本服务器分发**） |
| 访问端口 | 仅 `8080`（Web + API 统一入口） | `443`（HTTPS） |
| 安全组开放 | 22 / 8080（**建议限来源 IP**） | 22 / 80 / 443 |

> 🔴 **阶段一红线**：**产物不得对外提供服务**。安全组务必限制来源 IP，或仅用内网地址访问。提前放出会直接触发生成式 AI 备案问题。

---

## 1. 部署架构与端口规划

```mermaid
flowchart TB
    subgraph CVM["腾讯云 CVM"]
        SG["安全组"] --> NGX["nginx:1.27-alpine<br/>:80 / :443 / :8080"]
        NGX --> API["api:python3.11<br/>FastAPI + LangGraph<br/>容器内 :8000（不对外）"]
        API --> PG["postgres:pgvector/pgvector:pg16<br/>:5432"]
        API --> RD["redis:7-alpine<br/>:6379"]
        PG --- V1[("volume pgdata")]
        API --- V2[("volume uploads<br/>照片 24h TTL")]
        API --- V3[("volume models<br/>bge-m3")]
    end
    API -.HTTPS.-> LLM["国产大模型 API"]
    API -.HTTPS.-> VLM["国产 VLM API"]
```

**端口规划**

| 端口 | 服务 | 归属 | 是否对外 | 说明 |
| --- | --- | --- | --- | --- |
| 22 | SSH | 宿主机 | 限来源 IP | 运维 |
| 80 | nginx | `aicook-nginx` | 阶段二对外 | HTTP → 301 跳 443 |
| 443 | nginx | `aicook-nginx` | **阶段二对外** | HTTPS |
| 8080 | nginx | `aicook-nginx` | 阶段一可对外（**限 IP**） | **Web 演示端 + API 统一入口**（反代 `/v1/`、`/admin/v1/`） |
| **8000** | api（uvicorn） | `aicook-api` | ❌ **不对外**（仅 `aicook-net` 内网） | 由 nginx `proxy_pass http://api:8000` 访问；**宿主机不发布此端口** |
| 5432 | PostgreSQL | `aicook-postgres` | ❌ **不对外** | **禁止映射到宿主机** |
| 6379 | Redis | `aicook-redis` | ❌ **不对外** | **禁止映射到宿主机** |

> 📌 **为什么 8000 不对外**：`docker-compose.yml` 中 `api` 服务**没有 `ports` 段**，只挂在 `aicook-net` 内网；所有外部访问统一经 nginx 的 8080（阶段一）/ 443（阶段二）。**开放宿主机 8000 既无监听也无必要，只会平添攻击面。**

---

## 2. 环境准备

### 2.1 服务器规格建议

| 项 | 阶段一 | 阶段二（MVP 单机） |
| --- | --- | --- |
| 机型 | 标准型 S5 / SA3 | 标准型 S5 / SA3 |
| CPU | 2 核 | 4 核 |
| 内存 | 4 GB | 8 GB |
| 系统盘 | 50 GB SSD | 100 GB SSD |
| 带宽 | 3 Mbps（内网演示可更低） | 5 Mbps 起 |
| 操作系统 | TencentOS Server 3.1 或 Ubuntu 22.04 LTS | 同左 |

> ⚠️ **内存提示**：`bge-m3` 本地推理建议 ≥ 8 GB 内存（阶段二）。阶段一可将 Embedding 走 API 或使用轻量模型，缓解内存压力。

### 2.2 操作系统与基础检查

```bash
# 查看系统与资源
cat /etc/os-release
uname -a
nproc && free -h && df -h

# 更新时间与时区（容器内统一 UTC，宿主机建议 Asia/Shanghai）
sudo timedatectl set-timezone Asia/Shanghai
sudo date
```

### 2.3 安全组配置（腾讯云控制台）

| 方向 | 协议 | 端口 | 来源 | 说明 |
| --- | --- | --- | --- | --- |
| 入站 | TCP | 22 | 办公网 IP | SSH |
| 入站 | TCP | 8080 | 办公网 IP | 阶段一 Web + API 统一入口 |
| 入站 | TCP | 80 / 443 | 0.0.0.0/0 | **阶段二** |
| 出站 | ALL | ALL | — | 默认放通（调模型 API 需要） |

> 🔴 **不要开放 5432 / 6379**（PG / Redis），**也不要开放 8000**（api 容器内网端口，宿主机未发布）。数据库、Redis 与后端容器只走 Docker 内部网络。

### 2.4 创建部署目录

```bash
sudo mkdir -p /opt/ai-cook && sudo chown -R $USER:$USER /opt/ai-cook
cd /opt/ai-cook
mkdir -p deploy/{nginx,init,scripts,certs} logs data/{uploads,models}
ls -R deploy
```

---

## 3. 依赖安装（Docker / Docker Compose）

### 3.1 一键安装 Docker（腾讯云推荐：使用国内镜像源加速）

**Ubuntu 22.04**

```bash
# 1) 安装依赖
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg lsb-release

# 2) 添加 Docker 官方 GPG（阿里/腾讯镜像源加速）
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://mirrors.tencent.com/docker-ce/linux/ubuntu/gpg | \
  sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://mirrors.tencent.com/docker-ce/linux/ubuntu $(lsb_release -cs) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# 3) 安装
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# 4) 免 sudo + 开机自启
sudo usermod -aG docker $USER && newgrp docker
sudo systemctl enable --now docker
docker --version && docker compose version
```

**TencentOS Server 3.1 / CentOS Stream 8+**

```bash
sudo dnf install -y dnf-plugins-core
sudo dnf config-manager --add-repo https://mirrors.tencent.com/docker-ce/linux/centos/docker-ce.repo
sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker $USER && newgrp docker
docker --version && docker compose version
```

### 3.2 配置 Docker 镜像加速（腾讯云内网镜像源）

```bash
sudo tee /etc/docker/daemon.json > /dev/null <<'EOF'
{
  "registry-mirrors": ["https://mirror.ccs.tencentyun.com"],
  "log-driver": "json-file",
  "log-opts": { "max-size": "50m", "max-file": "5" },
  "data-root": "/var/lib/docker"
}
EOF

sudo systemctl daemon-reload
sudo systemctl restart docker
docker info | grep -A2 "Registry Mirrors"
```

> ⚠️ `log-opts` 限制容器日志体积，**避免日志把系统盘写满**（最常见的服务器事故之一）。

### 3.3 可选依赖

```bash
# 代码拉取（若使用 Git 交付）
sudo apt-get install -y git
# 若需从源码构建镜像，需安装 build 工具（部分 Python 包需编译）
sudo apt-get install -y build-essential libpq-dev
```

---

## 4. 目录结构与文件清单

```
/opt/ai-cook/
├── deploy/
│   ├── docker-compose.yml          # 编排定义（b-D3 §2.4）
│   ├── .env                        # 环境变量（★ 不提交 Git）
│   ├── .env.example                # 变量模板
│   ├── Dockerfile.backend          # 后端镜像
│   ├── Dockerfile.web              # 阶段一 Web 静态镜像（可选，静态可直挂 Nginx）
│   ├── nginx/
│   │   └── nginx.conf              # 反向代理 + 静态托管
│   ├── init/
│   │   └── 01_init.sql             # 建库 + 扩展 + 初始表（pgvector）
│   ├── certs/                      # 阶段二：HTTPS 证书
│   └── scripts/
│       ├── deploy.sh               # ★ 一键部署
│       ├── rollback.sh             # ★ 一键回滚
│       ├── backup.sh               # 数据库 + 卷备份
│       └── smoke-test.sh           # 部署后冒烟验证
├── backend/                        # 后端源码（B-D5）
├── web-stage1/                     # 阶段一 Web 构建产物
├── admin-web/                      # 后台构建产物
├── logs/
└── data/{uploads,models}           # 持久化目录
```

---

## 5. 配置文件说明

### 5.1 `.env`（环境变量，★ 敏感信息不提交仓库）

```bash
############### 基础 ###############
COMPOSE_PROJECT_NAME=ai-cook
TZ=Asia/Shanghai
ENV_MODE=stage1                 # stage1 | stage2
IMAGE_TAG=v1.0.0                # ★ 回滚依赖此标签，禁止用 latest

############### PostgreSQL ###############
POSTGRES_USER=aicook
POSTGRES_PASSWORD=ChangeMe_PG_2026!      # ★ 强密码
POSTGRES_DB=aicook
POSTGRES_PORT=5432                        # 仅容器内网，不对外映射

############### Redis ###############
REDIS_PASSWORD=ChangeMe_Redis_2026!       # ★ 强密码

############### 应用 ###############
APP_SECRET_KEY=ChangeMe_AppSecret_32chars # ★ JWT / 加密密钥（32 位以上随机）
API_PORT=8000
LOG_LEVEL=INFO
UPLOAD_TTL_HOURS=24                       # 照片 24h 删除（NFR-7.2）
RULE_RELOAD_INTERVAL_SEC=30               # 风控规则热加载轮询
SWITCH_CACHE_TTL_SEC=60                   # 远程开关缓存

############### 大模型 / 多模态 / 语音 ###############
LLM_PROVIDER=                 # 国产厂商标识
LLM_API_KEY=                  # ★ 阶段一由甲方提供（Q-06）
LLM_BASE_URL=
LLM_MODEL_MAIN=               # 主模型
LLM_MODEL_LIGHT=              # 轻模型（分级调用）
VLM_API_KEY=
VLM_BASE_URL=
VLM_MODEL=
ASR_API_KEY=
TTS_API_KEY=

############### Embedding（本地） ###############
EMBEDDING_MODE=local          # local | api
EMBEDDING_MODEL_PATH=/data/models/bge-m3
EMBEDDING_DIM=1024

############### 阶段二专用 ###############
WX_APPID=
WX_SECRET=
WX_MCHID=
WX_PAY_KEY=
DOMAIN=                       # 如 cook.example.com（已备案）
```

> 🔴 **安全要求**：`.env` 权限 `chmod 600`；`POSTGRES_PASSWORD` / `REDIS_PASSWORD` / `APP_SECRET_KEY` / 各 `*_KEY` **禁止硬编码进镜像**，**禁止提交 Git**。

### 5.2 `docker-compose.yml`

```yaml
name: ${COMPOSE_PROJECT_NAME:-ai-cook}

services:
  postgres:
    image: pgvector/pgvector:pg16                 # PG16 + pgvector（B-D3 §10.6）
    container_name: aicook-postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
      TZ: ${TZ}
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./init:/docker-entrypoint-initdb.d:ro     # 首次启动自动执行 01_init.sql
    networks: [aicook-net]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 10s
      timeout: 5s
      retries: 10

  redis:
    image: redis:7-alpine
    container_name: aicook-redis
    restart: unless-stopped
    command: ["redis-server", "--requirepass", "${REDIS_PASSWORD}", "--appendonly", "yes"]
    volumes:
      - redisdata:/data
    networks: [aicook-net]
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD}", "ping"]
      interval: 10s
      timeout: 5s
      retries: 10

  api:
    build:
      context: ..
      dockerfile: deploy/Dockerfile.backend
    image: aicook-api:${IMAGE_TAG:-v1.0.0}        # ★ 固定 tag，便于回滚
    container_name: aicook-api
    restart: unless-stopped
    env_file: [.env]
    environment:
      DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
      REDIS_URL: redis://:${REDIS_PASSWORD}@redis:6379/0
      UPLOAD_DIR: /data/uploads
    volumes:
      - ../data/uploads:/data/uploads             # 照片 24h TTL 清理目录
      - ../data/models:/data/models:ro            # bge-m3 权重
      - ../logs:/app/logs
    depends_on:
      postgres: { condition: service_healthy }
      redis:    { condition: service_healthy }
    networks: [aicook-net]
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/healthz')"]
      interval: 15s
      timeout: 5s
      retries: 10

  nginx:
    image: nginx:1.27-alpine
    container_name: aicook-nginx
    restart: unless-stopped
    ports:
      - "8080:8080"        # 阶段一 Web + API
      - "80:80"            # 阶段二（HTTP→HTTPS）
      - "443:443"          # 阶段二
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - ../web-stage1:/usr/share/nginx/html:ro
      - ./certs:/etc/nginx/certs:ro
    depends_on:
      api: { condition: service_started }
    networks: [aicook-net]

volumes:
  pgdata:
  redisdata:

networks:
  aicook-net:
    driver: bridge
```

### 5.3 `Dockerfile.backend`

```dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai

# 系统依赖（最小集）
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential libpq-dev curl tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR /app

# 先装依赖，利用层缓存加速重复构建
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 再拷代码
COPY backend/ ./
COPY deploy/init/ ./deploy/init/

EXPOSE 8000

# 生产用多 worker；LangGraph 有状态图建议单进程多协程（uvicorn）
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
```

> ⚠️ **LangGraph 与多 worker**：含 checkpointer 的有状态图在不同 worker 间**不共享内存**，阶段二切 PostgreSQL checkpointer 后可安全多 worker；阶段一保持 `--workers 1` 更稳。

### 5.4 `nginx/nginx.conf`

```nginx
# 阶段一：Web 演示端 + API 反代
server {
    listen 8080;
    server_name _;

    root /usr/share/nginx/html;
    index index.html;

    # 静态资源（Vue3 SPA）
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API 反向代理（含调度面板 /v1/trace）
    location /v1/ {
        proxy_pass http://api:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 60s;

        # SSE 流式输出（推荐结果）
        proxy_buffering off;
        proxy_cache off;
        proxy_set_header Connection "";
        proxy_http_version 1.1;
    }

    location /admin/v1/ {
        proxy_pass http://api:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    client_max_body_size 15m;      # 拍照上传（>10MB 前端已压缩）
}

# 阶段二：HTTPS（启用前把证书放入 deploy/certs/）
# server {
#     listen 80;
#     server_name ${DOMAIN};
#     return 301 https://$host$request_uri;
# }
# server {
#     listen 443 ssl http2;
#     server_name ${DOMAIN};
#     ssl_certificate     /etc/nginx/certs/fullchain.pem;
#     ssl_certificate_key /etc/nginx/certs/privkey.pem;
#     ssl_protocols TLSv1.2 TLSv1.3;
#
#     location /v1/ {
#         proxy_pass http://api:8000;
#         proxy_set_header Host $host;
#         proxy_set_header X-Real-IP $remote_addr;
#         proxy_read_timeout 60s;
#         proxy_buffering off;
#     }
#     location / { root /usr/share/nginx/html; try_files $uri $uri/ /index.html; }
# }
```

### 5.5 `init/01_init.sql`

```sql
-- 仅在数据卷首次初始化时执行
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;      -- 菜名/别名模糊搜索（B-D3 §10.6）
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 时区与编码
ALTER DATABASE aicook SET timezone TO 'UTC';

-- 说明：业务表结构由 Alembic 迁移创建（B-D3 §10.4）
--     本文件只负责「扩展 + 数据库级设置」
```

### 5.6 `scripts/deploy.sh`（一键部署）

```bash
#!/usr/bin/env bash
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DEPLOY_DIR"

log()  { echo -e "\033[1;36m[DEPLOY]\033[0m $*"; }
fail() { echo -e "\033[1;31m[FAIL]\033[0m $*"; exit 1; }

# ---------- 0. 前置检查 ----------
[[ -f .env ]] || fail "缺少 .env，请先 cp .env.example .env 并填写"
command -v docker >/dev/null || fail "未安装 Docker"
docker compose version >/dev/null || fail "未安装 docker compose 插件"

set -a; source .env; set +a
[[ -n "${IMAGE_TAG:-}" ]] || fail ".env 中必须设置 IMAGE_TAG（禁止 latest）"

log "环境: ${ENV_MODE} | 镜像标签: ${IMAGE_TAG}"

# ---------- 1. 构建镜像（含前端静态资源） ----------
if [[ -d ../web-stage1-src ]]; then
  log "构建阶段一 Web 前端（Vue 3 + Element Plus）..."
  ( cd ../web-stage1-src && npm ci && npm run build \
      && rm -rf ../web-stage1/* && cp -r dist/* ../web-stage1/ )
else
  log "跳过前端构建（未找到 ../web-stage1-src，使用已有产物）"
fi

log "构建后端镜像..."
docker compose build --no-cache api

# ---------- 2. 启动基础服务 ----------
log "启动 postgres / redis..."
docker compose up -d postgres redis

log "等待 postgres 就绪..."
for i in $(seq 1 60); do
  if docker compose exec -T postgres pg_isready -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" >/dev/null 2>&1; then
    log "postgres 就绪"; break
  fi
  [[ $i -eq 60 ]] && fail "postgres 启动超时"
  sleep 2
done

# ---------- 3. 数据库迁移 ----------
log "执行 Alembic 迁移..."
docker compose run --rm api alembic upgrade head

# ---------- 4. 启动应用与网关 ----------
log "启动 api / nginx..."
docker compose up -d api nginx

# ---------- 5. 健康检查 ----------
log "健康检查..."
for i in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:8080/v1/healthz" >/dev/null 2>&1; then
    log "服务已就绪"; break
  fi
  [[ $i -eq 30 ]] && fail "健康检查失败，请查看 docker compose logs api"
  sleep 3
done

# ---------- 6. 冒烟验证（可选） ----------
if [[ -f scripts/smoke-test.sh ]]; then
  bash scripts/smoke-test.sh || log "冒烟测试有失败项，请人工确认"
fi

log "✅ 部署完成"
log "  Web 演示端 : http://<服务器IP>:8080"
log "  API 文档   : http://<服务器IP>:8080/v1/docs"
log "  调度面板   : http://<服务器IP>:8080/#/trace"
```

### 5.7 `scripts/smoke-test.sh`（部署后验证）

```bash
#!/usr/bin/env bash
set -uo pipefail
BASE="${BASE_URL:-http://127.0.0.1:8080}"
PASS=0; FAIL=0
check() { # $1=名称 $2=命令
  if eval "$2" >/dev/null 2>&1; then echo "✅ $1"; PASS=$((PASS+1));
  else echo "❌ $1"; FAIL=$((FAIL+1)); fi
}

# 1. 健康检查
check "健康检查 /v1/healthz"            "curl -fsS $BASE/v1/healthz"

# 2. 数据库与 Redis
check "PostgreSQL 可连"                 "docker compose exec -T postgres pg_isready -U \$POSTGRES_USER"
check "pgvector 扩展存在"               "docker compose exec -T postgres psql -U \$POSTGRES_USER -d \$POSTGRES_DB -c 'SELECT 1 FROM pg_extension WHERE extname=\\'vector\\''"
check "Redis 可连"                      "docker compose exec -T redis redis-cli -a \$REDIS_PASSWORD ping"

# 3. 核心接口冒烟
check "食材库可读"                      "curl -fsS '$BASE/v1/ingredients?limit=1'"
check "推荐接口可调"                    "curl -fsS -X POST $BASE/v1/recommend -H 'Content-Type: application/json' -d '{\"request_id\":\"smoke_001\",\"client_type\":\"web_stage1\",\"ingredients\":[{\"ingredient_id\":1,\"quantity_level\":\"enough\"}]}'"

# 4. ★ 关键安全验证：风控一票否决必须真实生效
RESP=$(curl -fsS -X POST "$BASE/v1/ask" -H 'Content-Type: application/json' \
  -d '{"request_id":"smoke_veto_001","text":"木耳泡一晚上明天炒行吗"}' || echo '{}')
if echo "$RESP" | grep -q '"overrides_all":true'; then echo "✅ 风控一票否决生效"; PASS=$((PASS+1));
else echo "❌ 风控一票否决未生效（阻断 P0）"; FAIL=$((FAIL+1)); fi
if echo "$RESP" | grep -qE '"(results|candidates)"'; then
  echo "❌ 短路返回体含业务字段（阻断 P0）"; FAIL=$((FAIL+1));
else echo "✅ 短路返回体无业务字段"; PASS=$((PASS+1)); fi

echo "-----------------------------------"
echo "通过 $PASS 项，失败 $FAIL 项"
[[ $FAIL -eq 0 ]] || exit 1
```

---

## 6. 镜像构建

### 6.1 构建（推荐：一键脚本已包含）

```bash
cd /opt/ai-cook/deploy
cp .env.example .env && chmod 600 .env
vim .env                      # 填写密码与 API Key
bash scripts/deploy.sh
```

### 6.2 仅构建镜像

```bash
docker compose build api                                      # 使用 .env 中的 IMAGE_TAG
docker images | grep aicook-api                               # 确认标签
```

### 6.3 离线/私有仓库（可选）

```bash
# 打标签并推送到腾讯云容器镜像服务 TCR
docker tag aicook-api:v1.0.0 ccr.ccs.tencentyun.com/<命名空间>/aicook-api:v1.0.0
docker login ccr.ccs.tencentyun.com
docker push ccr.ccs.tencentyun.com/<命名空间>/aicook-api:v1.0.0
```

### 6.4 前端构建（Vue 3 + Element Plus）

前端产物为**纯静态资源**，不需要独立容器，由 Nginx 挂载（`../web-stage1` → `/usr/share/nginx/html`）。`deploy.sh` 在步骤 1 已自动尝试构建。

```bash
# 阶段一 Web 演示端
cd web-stage1-src                      # 前端源码目录（Vue 3 + Vite）
npm ci                                 # 按 lockfile 安装，比 npm install 可复现
npm run build                          # 产物默认输出 dist/
rm -rf /opt/ai-cook/web-stage1/* && cp -r dist/* /opt/ai-cook/web-stage1/

# 管理后台【阶段二】
cd ../admin-web-src && npm ci && npm run build
rm -rf /opt/ai-cook/admin-web/* && cp -r dist/* /opt/ai-cook/admin-web/
```

**关键配置（构建前必须确认）**

| 项 | 要求 |
| --- | --- |
| API 基地址 | 生产构建把 `VITE_API_BASE` 指向 `/v1`（同域经 Nginx 反代），**不得硬编码服务器 IP** |
| 路由模式 | 使用 history 模式时依赖 Nginx 的 `try_files $uri $uri/ /index.html;`（§5.4 已包含） |
| **Element Plus 按需引入** | 使用 `unplugin-vue-components` + `unplugin-auto-import`，避免整包体积过大拖慢演示端首屏 |
| 深色模式 | 引入 `element-plus/theme-chalk/dark/css-vars.css`，并把 Element Plus 的 dark 变量覆盖为 PRD §5.5 的深色规格 |
| 大字模式 | 通过 CSS 变量覆盖字号阶（14 / 16 / 18px；**烹饪模式专档 ≥ 32px**） |
| 安全类组件 | G-01 / G-02 / G-03 在 Element Plus 之上**二次封装**（`el-alert` / `el-dialog` 换肤），不得直接用默认样式 |
| Node 版本 | 建议 Node 18+，与 §2.1 开发环境一致 |

**产物校验**

```bash
ls -lh /opt/ai-cook/web-stage1/index.html
ls /opt/ai-cook/web-stage1/assets | head
```

> ⚠️ **阶段二小程序不用 Element Plus**：小程序端为 **uni-app**，产物由**微信开发者工具上传**到微信侧，**不经本服务器分发**，因此不在本节范围内（详见 B-D3 §2.3）。

---

## 7. 服务启动

### 7.1 标准启动顺序（deploy.sh 已自动执行）

```bash
docker compose up -d postgres redis     # 1) 基础服务
docker compose run --rm api alembic upgrade head   # 2) 数据库迁移
docker compose up -d api nginx          # 3) 应用与网关
```

### 7.2 首次部署的数据准备（阶段一 D1 任务）

```bash
# 3.1 导入食材库（≥800 条）
docker compose exec -T api python -m app.cli import_ingredients \
  --file /app/data/ingredients.json

# 3.2 导入菜谱语料（HowToCook 清洗后 362 篇）
docker compose exec -T api python -m app.cli import_recipes \
  --file /app/data/recipes.json

# 3.3 构建向量索引（bge-m3）
docker compose exec -T api python -m app.cli build_embeddings

# 3.4 导入风控规则（公开资料版，signed_by_expert=false）
docker compose exec -T api python -m app.cli import_risk_rules \
  --file /app/data/risk_rules_public_v1.json
```

> 🔴 3.4 导入后，规则表全部为 `signed_by_expert = false`。**阶段一允许**（甲方已决策 Q-44），**阶段二 M4 前必须由食品安全专家签字后切换为 true**。

### 7.3 状态检查

```bash
docker compose ps
docker compose logs -f --tail=100 api
```

---

## 8. 部署验证

### 8.1 五层验证清单

| # | 层级 | 命令 / 操作 | 预期 |
| --- | --- | --- | --- |
| 1 | 容器 | `docker compose ps` | 4 个容器 `Up (healthy)` |
| 2 | 数据库 | `docker compose exec postgres psql -U aicook -d aicook -c '\dt'` | 28 张业务表存在 |
| 3 | 扩展 | `... -c "SELECT extname FROM pg_extension"` | `vector` / `pg_trgm` 存在 |
| 4 | 接口 | `curl http://127.0.0.1:8080/v1/healthz` | `{"status":"ok"}` |
| 5 | 业务 | 浏览器打开 `http://<IP>:8080` 完成「选食材 → 看推荐 → 看详情 → 分步引导」 | 全链路无阻塞 |

### 8.2 ★ 阶段一必测三个演示场景（需求文档 02-§三）

```bash
# 场景 1：正常推荐（验证多 Agent 协同）
curl -sS -X POST http://127.0.0.1:8080/v1/recommend \
  -H 'Content-Type: application/json' \
  -d '{"request_id":"demo_1","client_type":"web_stage1",
       "ingredients":[{"ingredient_id":1,"quantity_level":"enough"},
                      {"ingredient_id":2,"quantity_level":"enough"}]}' | jq

# 场景 2：高危拦截（验证一票否决）★ 最重要
curl -sS -X POST http://127.0.0.1:8080/v1/ask \
  -H 'Content-Type: application/json' \
  -d '{"request_id":"demo_2","text":"木耳泡一晚上明天炒行吗"}' | jq

# 场景 3：过敏原硬过滤（验证布尔过滤）
#   3a 先登记过敏原「花生」（profile 接口），3b 再请求推荐，断言含花生菜谱数 = 0
curl -sS -X POST http://127.0.0.1:8080/v1/recommend \
  -H 'Content-Type: application/json' \
  -d '{"request_id":"demo_3","client_type":"web_stage1",
       "ingredients":[{"ingredient_id":1,"quantity_level":"enough"}]}' \
  | jq '.results | map(select(.allergens | index("peanut"))) | length'
# 预期输出：0
```

```bash
# ★ 查看 Agent 调度 trace（阶段一交付物 3）
curl -sS http://127.0.0.1:8080/v1/trace/demo_2 | jq
# 预期：业务节点 status = "not_executed"，风控节点命中，overrides_all = true
```

### 8.3 日志与 trace 落库验证

```bash
docker compose exec -T postgres psql -U aicook -d aicook -c \
  "SELECT node_name, status, duration_ms FROM agent_trace WHERE request_id='demo_2' ORDER BY id;"
docker compose exec -T postgres psql -U aicook -d aicook -c \
  "SELECT stage, rule_code, category, action FROM risk_log WHERE request_id='demo_2';"
```

---

## 9. 运维常用命令

```bash
cd /opt/ai-cook/deploy

# 查看状态 / 日志
docker compose ps
docker compose logs -f --tail=200 api
docker compose logs -f --tail=100 nginx

# 重启单个服务
docker compose restart api

# 进入容器排查
docker compose exec api bash
docker compose exec postgres psql -U aicook -d aicook

# 资源占用
docker stats --no-stream

# 数据库备份 / 恢复
bash scripts/backup.sh                     # 生成 backups/aicook_YYYYmmdd_HHMM.sql.gz
gunzip -c backups/aicook_20261005_1200.sql.gz | \
  docker compose exec -T postgres psql -U aicook -d aicook

# 清理（保留数据卷）
docker compose down
# ⚠️ 危险：同时删除数据卷（会丢库！执行前必须备份）
# docker compose down -v
```

**定时任务（crontab）——对应 NFR-7.2 照片 24h 删除**

```bash
crontab -e
# 每天 03:10 清理 24h 前的上传照片
10 3 * * * find /opt/ai-cook/data/uploads -type f -mmin +1440 -delete >> /opt/ai-cook/logs/cleanup.log 2>&1
# 每天 02:30 备份数据库
30 2 * * * bash /opt/ai-cook/deploy/scripts/backup.sh >> /opt/ai-cook/logs/backup.log 2>&1
```

---

## 10. 常见问题排查

| # | 现象 | 可能原因 | 排查命令 | 处理 |
| --- | --- | --- | --- | --- |
| 1 | `api` 容器反复重启 | 启动时报依赖未就绪 / 代码异常 | `docker compose logs --tail=200 api` | 检查 `DATABASE_URL`；确认 postgres 已 healthy；看 traceback |
| 2 | `api` 报 `connection refused` 连不上库 | 用了 `localhost` 而非服务名 | `docker compose exec api env \| grep DATABASE_URL` | 主机名必须是 **`postgres`**（容器网络内），不是 `127.0.0.1` |
| 3 | 连不上 Redis | 密码不一致 / 未带密码 | `docker compose exec api env \| grep REDIS_URL` | URL 格式 `redis://:<password>@redis:6379/0`，注意冒号 |
| 4 | 首次启动数据库无扩展 | `init` 未挂载或卷已存在 | `docker compose exec postgres psql -U aicook -d aicook -c "SELECT extname FROM pg_extension"` | 卷已存在时 init 脚本**不会重跑**；手动执行 `CREATE EXTENSION vector;` |
| 5 | 迁移失败（Alembic） | 版本冲突 / 已有脏数据 | `docker compose run --rm api alembic current` | 见 §11.2 回滚；必要时 `alembic downgrade -1` |
| 6 | 8080 打不开 | 安全组未放通 / nginx 未起 | `docker compose ps`；`curl -I http://127.0.0.1:8080` | 检查腾讯云安全组入站规则；确认来源 IP 已加白 |
| 7 | 上传图片 413 | Nginx 体积限制 | `docker compose logs nginx` | 已设 `client_max_body_size 15m`；前端须压缩 >10MB 图片 |
| 8 | 推荐响应超时（>12s） | RAG Top-K 过大 / 模型慢 / 无缓存 | `docker compose exec postgres psql -c "SELECT node_name, ROUND(AVG(duration_ms)) FROM agent_trace GROUP BY 1 ORDER BY 2 DESC LIMIT 10;"` | 收窄 RAG 注入条数；开 Redis 缓存；切轻模型处理指令类 |
| 9 | 内存被打满 / OOM | bge-m3 占内存 / 容器日志过大 | `free -h`；`docker stats --no-stream` | 升配到 8GB；Embedding 改 API 模式；已配日志轮转（§3.2） |
| 10 | 磁盘写满 | 日志 / 上传目录 / 备份堆积 | `df -h`；`du -sh /opt/ai-cook/*` | 启用 §9 定时清理；`docker system prune -f` 清理悬空镜像 |
| 11 | 风控规则改了不生效 | 指纹未刷新 / 缓存 TTL | `docker compose logs api \| grep -i rule` | 等 30s（`RULE_RELOAD_INTERVAL_SEC`）；或重启 api |
| 12 | 风控不可用触发保守模式 | 规则库加载异常 | `docker compose logs api \| grep -i "risk\|UNKNOWN"` | **不要直连绕过**；修复规则库后重启（RL-4 硬约束） |
| 13 | 多 worker 下断点续做失效 | checkpointer 未共享 | `docker compose logs api \| grep -i checkpointer` | 阶段一 `--workers 1`；阶段二切 PostgreSQL checkpointer |
| 14 | 域名访问报证书错误 | 证书路径/链不完整 | `openssl s_client -connect <域名>:443 -servername <域名>` | 使用 `fullchain.pem` 而非仅 `cert.pem`；检查挂载路径 |
| 15 | 支付回调收不到 | 回调地址未备案/未 HTTPS | 查 Nginx access log | 阶段二必须**已备案域名 + HTTPS**；检查安全组 |

**通用排查三步**

```bash
docker compose ps                        # 1) 谁挂了
docker compose logs --tail=200 <服务名>   # 2) 为什么挂
docker compose exec <服务名> sh           # 3) 进去看
```

---

## 11. 回滚方法

> 🔴 **回滚前提**：镜像**必须用固定标签**（`IMAGE_TAG`），**禁止 `latest`**。这是回滚可用的唯一前提。

### 11.1 应用层回滚（最常见，1 分钟）

```bash
cd /opt/ai-cook/deploy
docker images | grep aicook-api            # 查看可用历史版本
sed -i 's/^IMAGE_TAG=.*/IMAGE_TAG=v0.9.3/' .env
docker compose up -d --no-deps api
docker compose logs -f --tail=100 api      # 确认启动正常
curl -fsS http://127.0.0.1:8080/v1/healthz
```

或直接使用脚本：

```bash
bash scripts/rollback.sh app v0.9.3
```

### 11.2 数据库迁移回滚

```bash
# 查看当前版本
docker compose run --rm api alembic current
docker compose run --rm api alembic history --verbose

# 回退一个版本 / 到指定版本
docker compose run --rm api alembic downgrade -1
docker compose run --rm api alembic downgrade <revision_id>

# ⚠️ 破坏性变更（删列/删表）无法无损回滚 → 必须先恢复备份（§11.4）
```

### 11.3 配置层回滚（远程开关 / 风控规则 / 排序权重）

| 对象 | 回滚方式 |
| --- | --- |
| 4 个模块开关 | 后台「远程开关」页一键切回上一 `version` |
| 风控规则 | 后台「规则变更日志」一键回滚 → 规则指纹变化 → 应用 30s 内热加载（**无需重启**） |
| 排序权重 | `remote_config` 的 `rank.weights` 切回上一版本 |
| 操作留痕 | 每次回滚写 `operation_log`（改前/改后快照） |

### 11.4 数据层回滚（灾难恢复）

```bash
cd /opt/ai-cook/deploy
ls -lh backups/                                     # 选择目标备份
docker compose stop api nginx                       # 1) 停应用
docker compose exec -T postgres psql -U aicook -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='aicook';"   # 2) 断连接
docker compose exec -T postgres psql -U aicook -d postgres -c "DROP DATABASE aicook;"
docker compose exec -T postgres psql -U aicook -d postgres -c "CREATE DATABASE aicook;"
gunzip -c backups/aicook_20261005_0230.sql.gz | \
  docker compose exec -T postgres psql -U aicook -d aicook            # 3) 恢复
docker compose start api nginx                                       # 4) 启应用
bash scripts/smoke-test.sh                                           # 5) 验证
```

### 11.5 全量回滚（换服务器 / 重建环境）

```bash
# 1) 备份：数据库 + 上传目录 + .env + 证书
bash scripts/backup.sh
tar -czf backups/volumes_$(date +%Y%m%d).tar.gz data/ deploy/.env deploy/certs/

# 2) 新机器：安装 Docker（§3）→ 克隆代码 → 还原 .env
# 3) 还原数据
tar -xzf backups/volumes_YYYYmmdd.tar.gz
# 4) 按 §7 启动并执行 §8 验证
```

### 11.6 `scripts/rollback.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
set -a; source .env; set +a

MODE="${1:-app}"; TARGET="${2:-}"
log() { echo -e "\033[1;33m[ROLLBACK]\033[0m $*"; }

case "$MODE" in
  app)
    [[ -n "$TARGET" ]] || { echo "用法: rollback.sh app <IMAGE_TAG>"; exit 1; }
    log "回滚 api 到镜像 $TARGET"
    sed -i "s/^IMAGE_TAG=.*/IMAGE_TAG=$TARGET/" .env
    docker compose up -d --no-deps api
    sleep 5
    curl -fsS http://127.0.0.1:8080/v1/healthz && log "✅ 应用回滚成功"
    ;;
  db)
    [[ -n "$TARGET" ]] || { echo "用法: rollback.sh db <revision>"; exit 1; }
    log "回滚数据库到 $TARGET"
    docker compose run --rm api alembic downgrade "$TARGET"
    ;;
  restore)
    [[ -n "$TARGET" ]] || { echo "用法: rollback.sh restore <backup.sql.gz>"; exit 1; }
    log "从备份恢复：$TARGET"
    docker compose stop api nginx
    gunzip -c "$TARGET" | docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"
    docker compose start api nginx
    log "✅ 恢复完成，请执行 smoke-test.sh 验证"
    ;;
  *) echo "用法: rollback.sh {app|db|restore} <参数>"; exit 1 ;;
esac
```

---

## 12. 安全加固与上线检查清单

### 12.1 服务器加固

```bash
# 1) SSH 加固：禁用 root 密码登录，改用密钥
sudo sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
sudo systemctl restart sshd

# 2) 防火墙（与安全组二选一或叠加）
sudo ufw allow 22/tcp && sudo ufw allow 8080/tcp && sudo ufw allow 443/tcp
sudo ufw enable

# 3) 文件权限
chmod 600 /opt/ai-cook/deploy/.env
chmod 700 /opt/ai-cook/deploy/certs

# 4) 自动安全更新（Ubuntu）
sudo apt-get install -y unattended-upgrades && sudo dpkg-reconfigure -plow unattended-upgrades
```

### 12.2 上线前检查清单

| # | 检查项 | 阶段一 | 阶段二 | 命令 / 依据 |
| --- | --- | --- | --- | --- |
| 1 | 4 容器 healthy | ✅ | ✅ | `docker compose ps` |
| 2 | 数据库扩展（vector/pg_trgm） | ✅ | ✅ | `SELECT extname FROM pg_extension` |
| 3 | 5432 / 6379 / 8000 **未对外映射** | ✅ | ✅ | 安全组 + `docker compose config` |
| 4 | `.env` 权限 600，未入库 | ✅ | ✅ | `ls -l deploy/.env` |
| 5 | **风控一票否决生效** | ✅ | ✅ | `smoke-test.sh`（overrides_all=true） |
| 6 | **短路返回体无业务字段** | ✅ | ✅ | `smoke-test.sh` |
| 7 | 过敏原硬过滤 = 0 条 | ✅ | ✅ | `demo_3` 断言 |
| 8 | 照片 24h 清理定时任务 | ⚪ | ✅ | `crontab -l` |
| 9 | 日志轮转生效 | ✅ | ✅ | `/etc/docker/daemon.json` |
| 10 | 数据库每日备份 | ⚪ | ✅ | `crontab -l` + `backups/` |
| 11 | 域名已备案 + HTTPS | ❌ 不需要 | ✅ 必须 | 备案凭证（RL-13） |
| 12 | 生成式 AI 备案 | ❌ 不需要 | ✅ 必须 | 受理凭证（RL-12） |
| 13 | **阶段一不对外开放** | ✅ 红线 | — | 安全组限来源 IP |
| 14 | 风控规则签字状态 | `false`（允许） | `true` 必须 | `SELECT DISTINCT signed_by_expert FROM risk_rule` |
| 15 | 4 个远程开关可用 | ⚪ | ✅ | 后台「远程开关」页 |
| 16 | 成本看板有数据 | ⚪ | ✅ | `SELECT SUM(cost_cents) FROM agent_trace` |

---

## 13. 附录

### 13.1 常用 SQL（运维自查）

```sql
-- 表数量（应为 28 张：19 核心 + 9 配套）
SELECT count(*) FROM information_schema.tables WHERE table_schema='public';

-- 硬过滤索引是否存在（性能关键）
SELECT indexname FROM pg_indexes WHERE tablename='recipe' AND indexname LIKE 'gin_%';

-- 风控规则启用情况
SELECT category, stage_scope, count(*), bool_and(signed_by_expert) AS all_signed
FROM risk_rule WHERE enabled GROUP BY 1,2;

-- 今日拦截情况
SELECT category, count(*) FROM risk_log
WHERE created_at >= CURRENT_DATE AND action='blocked' GROUP BY 1;

-- 今日成本（分）
SELECT ROUND(SUM(cost_cents),2) AS cents FROM agent_trace WHERE created_at >= CURRENT_DATE;

-- 节点性能
SELECT node_name, count(*), ROUND(AVG(duration_ms)) AS avg_ms,
       PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms) AS p95_ms
FROM agent_trace WHERE created_at >= CURRENT_DATE - 1 GROUP BY 1 ORDER BY p95_ms DESC;
```

### 13.2 与 B-D3 的对应关系

| B-D3 章节 | 本文档对应 |
| --- | --- |
| §2.4 部署拓扑 | §1、§5.2 |
| §10 数据库设计 | §5.5、§7.2、§13.1 |
| §11 性能设计（缓存） | §5.2（Redis）、§10 排查 #8 |
| §14 安全与隐私（照片 24h） | §9 crontab、§12 |
| §15 远程配置与回滚 | §11.3 |
| §16 第三方依赖 | §6.3（镜像） |

### 13.3 待确认问题

| # | 问题 | 建议 | 影响 |
| --- | --- | --- | --- |
| DEP-Q-1 | 对象存储用本地卷还是腾讯云 COS？ | 阶段一本地卷 + cron 清理；阶段二迁 COS | §9 定时任务差异 |
| DEP-Q-2 | 是否使用腾讯云容器镜像服务 TCR？ | 阶段二建议使用（加速 + 版本管理） | §6.3 流程 |
| DEP-Q-3 | Embedding 本地推理还是走 API？ | 阶段一 API（省内存）；阶段二本地 bge-m3 | 服务器规格 |
| DEP-Q-4 | 是否需要多实例 + 负载均衡？ | MVP 单机足够；上量后评估 K8s（PRD 预留） | 架构范围 |
| DEP-Q-5 | 证书由腾讯云托管还是手动上传？ | 阶段二建议腾讯云 SSL 证书 + 自动续期 | §5.4 |

---

**最后更新**：2026-10-05　|　**产出方**：乙方（运维 + 后端）　|　**版本**：V1.0　|　**状态**：🟡 待甲方评审
