#!/usr/bin/env bash
# =====================================================================
# 文件名: scripts/deploy.sh
# 用途:   「AI 厨娘」Web 端生产部署脚本（阿里云 ECS Ubuntu 22.04 + Docker CE）
#
# 设计前提（重要）:
#   前端镜像在**本地开发机**构建后经 `docker save` → `scp` → `docker load`
#   送达服务器。本脚本不构建前端 —— 服务器构建两套前端时内存峰值较高，
#   因此在本地完成构建后再传到 ECS。
#   后端 api 镜像由服务器本地构建
#   （纯 Python wheel，无重包，2GHz 双核可承受）。
#
# 用法（在项目根目录执行）:
#   bash scripts/deploy.sh --check     # 只做前置体检，不做任何变更（建议先跑这个）
#   bash scripts/deploy.sh             # 部署/更新，不初始化种子数据
#   bash scripts/deploy.sh --seed      # 部署并执行种子数据初始化（首次部署用）
#   bash scripts/deploy.sh --help
#
# 需要在项目根目录准备的文件:
#   .env.production             生产变量（cp .env.production.example 后填写）
#   backend/.env                后端 LLM / VLM 配置（cp backend/.env.example 后填写）
#   backend/data/HowToCook/     语料库，约 265MB（🔴 镜像内不含，必须放在宿主机）
#   backend/assets/recipe_covers 封面目录（可空目录，seed 会生成内容）
#   aicook-web.tar 或 .tar.gz   本地构建好的前端镜像
#
# 换行符要求：本文件必须为 LF（Windows 下用 git 或编辑器确认，CRLF 会导致
#   `bash: $'\r': command not found`）。修复：sed -i 's/\r$//' scripts/deploy.sh
# =====================================================================

set -euo pipefail

# ---------- 常量与路径 ----------
RAIL='=============================================================='
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ENV_FILE="${ENV_FILE:-$ROOT/.env.production}"
WEB_IMAGE_DEFAULT="aicook-web:20261019"
WEB_TARBALL="${WEB_TARBALL:-$ROOT/aicook-web.tar}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-180}"

DO_CHECK=0
DO_SEED=0

# ---------- 输出工具 ----------
c_ok()   { printf '\033[32m[ OK ]\033[0m %s\n' "$*"; }
c_info() { printf '\033[36m[INFO]\033[0m %s\n' "$*"; }
c_warn() { printf '\033[33m[WARN]\033[0m %s\n' "$*"; }
c_err()  { printf '\033[31m[FAIL]\033[0m %s\n' "$*" >&2; }
die()    { c_err "$*"; exit 1; }

usage() {
  sed -n '3,27p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
}

# ---------- 参数解析 ----------
for arg in "$@"; do
  case "$arg" in
    --check) DO_CHECK=1 ;;
    --seed)  DO_SEED=1 ;;
    -h|--help) usage ;;
    *) die "未知参数：$arg（用 --help 查看用法）" ;;
  esac
done

echo "$RAIL"
echo " AI 厨娘 · Web 端生产部署"
echo " 项目根目录：$ROOT"
echo " 变量文件  ：$ENV_FILE"
echo "$RAIL"

# =====================================================================
# 0. 前置体检
# =====================================================================
c_info "步骤 0/7：前置体检"

command -v docker >/dev/null 2>&1 || die "未找到 docker，请先安装 Docker CE"
docker compose version >/dev/null 2>&1 || die "未找到 docker compose 插件（docker compose version 失败）"

COMPOSE_VER="$(docker compose version --short 2>/dev/null | sed 's/^v//')"
CV_MAJOR="${COMPOSE_VER%%.*}"
CV_REST="${COMPOSE_VER#*.}"; CV_MINOR="${CV_REST%%.*}"
if [ "${CV_MAJOR:-0}" -lt 2 ] || { [ "${CV_MAJOR:-0}" -eq 2 ] && [ "${CV_MINOR:-0}" -lt 24 ]; }; then
  die "Docker Compose 版本过低（当前 v$COMPOSE_VER，需 ≥ 2.24，因为 prod 覆盖层用了 !reset 语法）。
     降级方案：直接编辑 docker-compose.yml，删掉 api 服务的 ports 段（8000:8000）后不使用覆盖层。"
fi
c_ok "docker 与 docker compose 就绪（compose v$COMPOSE_VER）"

command -v curl >/dev/null 2>&1 || die "未找到 curl（apt-get install -y curl）"

[ -f "$ENV_FILE" ] || die "缺少 $ENV_FILE
     请先执行：cp .env.production.example .env.production 并填写真实口令"
c_ok "变量文件存在：$ENV_FILE"

[ -f "$ROOT/docker-compose.yml" ]      || die "缺少 docker-compose.yml"
[ -f "$ROOT/docker-compose.prod.yml" ] || die "缺少 docker-compose.prod.yml"
[ -f "$ROOT/backend/Dockerfile" ]      || die "缺少 backend/Dockerfile（backend 目录是否完整上传？）"
[ -f "$ROOT/nginx/nginx.conf" ]        || die "缺少 nginx/nginx.conf"
c_ok "编排与构建文件齐备"

# 后端运行期配置：缺失不致命（可后补），但会让 LLM/VLM 走默认值
if [ -f "$ROOT/backend/.env" ]; then
  c_ok "backend/.env 存在（LLM / VLM / 语音配置将注入 api 容器）"

  # Provider 体检：取 mock 时接口不会报错，只会静默返回演示内容 —— 最容易被误判为「功能坏了」
  for key in VISION_PROVIDER SPEECH_PROVIDER TTS_PROVIDER; do
    val="$(grep -E "^${key}=" "$ROOT/backend/.env" | tail -1 | cut -d= -f2- | tr -d ' \r')"
    if [ "${val:-mock}" = "mock" ]; then
      c_warn "${key}=mock —— 该能力在线上只返回演示内容（不报错、不提示）。
     若要对外演示真实效果，请在 backend/.env 切到真实 Provider（vlm / bailian）。"
    else
      c_ok "${key}=${val}"
    fi
  done

  # 行尾符体检：Windows 编辑后直传的 .env 若带 CRLF，值可能带尾部 \r 导致判断失配
  if grep -q $'\r' "$ROOT/backend/.env" 2>/dev/null; then
    c_warn "backend/.env 含 CRLF 行尾，建议转换后再部署：sed -i 's/\r$//' backend/.env"
  fi
else
  c_warn "缺少 backend/.env —— 大模型、视觉识别与语音能力可能不可用
     修复：cp backend/.env.example backend/.env 并填写 LLM_API_KEY / VISION_API_KEY"
fi

# ---------- 🔴 语料库：这是最容易漏、后果最严重的一项 ----------
CORPUS_DIR="$ROOT/backend/data/HowToCook/dishes"
if [ -d "$CORPUS_DIR" ]; then
  CORPUS_MD="$(find "$CORPUS_DIR" -name '*.md' 2>/dev/null | wc -l | tr -d ' ')"
  c_ok "语料库就绪：$CORPUS_MD 篇菜谱（$CORPUS_DIR）"
else
  if [ "$DO_SEED" -eq 1 ]; then
    die "语料库缺失：$CORPUS_DIR
     后端镜像内不含语料，容器内也没有 git（python:3.11-slim），代码里的
     ensure_corpus() 自动克隆兜底在容器内必然失败 —— 此时执行 seed 不会报错，
     但会静默跳过语料导入，结果是菜谱库为空、推荐与检索全部无数据。
     请先把本地 backend/data/HowToCook 整目录上传到服务器同名路径。"
  else
    c_warn "语料库缺失：$CORPUS_DIR
     本次不执行 --seed，暂不影响；但一旦执行 seed 请务必先补齐，否则菜谱库为空。"
  fi
fi

[ -d "$ROOT/backend/assets/recipe_covers" ] || {
  c_warn "backend/assets/recipe_covers 目录不存在，已自动创建（空目录）"
  mkdir -p "$ROOT/backend/assets/recipe_covers"
}
c_ok "封面目录就绪：backend/assets/recipe_covers"

# ---------- 变量解析 ----------
read_env() {
  grep -E "^$1=" "$ENV_FILE" 2>/dev/null | tail -1 | cut -d= -f2- \
    | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//"
}
WEB_PORT="$(read_env WEB_PORT)";   WEB_PORT="${WEB_PORT:-8005}"
WEB_IMAGE="$(read_env WEB_IMAGE)"; WEB_IMAGE="${WEB_IMAGE:-$WEB_IMAGE_DEFAULT}"
DB_PASSWORD="$(read_env DB_PASSWORD)";         DB_PASSWORD="${DB_PASSWORD:-}"
ADMIN_PASSWORD="$(read_env ADMIN_PASSWORD)";   ADMIN_PASSWORD="${ADMIN_PASSWORD:-}"
ADMIN_JWT_SECRET="$(read_env ADMIN_JWT_SECRET)"; ADMIN_JWT_SECRET="${ADMIN_JWT_SECRET:-}"

for pair in "DB_PASSWORD:$DB_PASSWORD" "ADMIN_PASSWORD:$ADMIN_PASSWORD" "ADMIN_JWT_SECRET:$ADMIN_JWT_SECRET"; do
  key="${pair%%:*}"; val="${pair#*:}"
  [ -n "$val" ] || die "变量缺失：$key（$ENV_FILE 中未配置或被注释）"
  case "$val" in
    CHANGE_ME*|*请替换*|*替换为*) die "变量未替换占位符：$key 仍是示例值，禁止上线" ;;
  esac
done
c_ok "关键变量完整（WEB_PORT=$WEB_PORT，WEB_IMAGE=$WEB_IMAGE，口令均非占位值）"

COMPOSE=(docker compose --env-file "$ENV_FILE" -f docker-compose.yml -f docker-compose.prod.yml)

"${COMPOSE[@]}" config -q || die "docker compose 配置校验失败（见上方报错）"
c_ok "compose 配置校验通过"

# 断言 8000 已从对外端口移除（!reset 是否真的生效）
if "${COMPOSE[@]}" config 2>/dev/null | grep -qE 'published: "?8000"?$' ; then
  die "api 仍在对外发布 8000 端口 —— !reset 未生效。
     降级方案：编辑 docker-compose.yml 删除 api 服务的 ports 段后重跑。"
fi
c_ok "api 的 8000 对外发布已移除（仅走 aicook-net 内网）"

if [ "$DO_CHECK" -eq 1 ]; then
  echo "$RAIL"
  c_ok "体检完成，未做任何变更。去掉 --check 即开始部署。"
  exit 0
fi

# =====================================================================
# 1. 基础镜像别名（绕开仓库内写死的 daocloud 加速前缀）
# =====================================================================
# 🔴 背景：Dockerfile 与 docker-compose.yml 内的镜像名带 `docker.m.daocloud.io/`
#    前缀。镜像名里一旦写死 registry 主机，Docker 就**直连该 registry**，
#    /etc/docker/daemon.json 的 registry-mirrors 完全不会生效。该前缀源
#    已出现 502 Bad Gateway（2026-10-14 实测），会直接卡死 build 与 up。
#    解法：先经镜像加速拉取官方镜像，再打上带前缀的别名 tag —— 构建与启动
#    都命中本地镜像、不再触网。仓库文件无需改动，本地开发流程也不受影响。
c_info "步骤 1/8：准备基础镜像"

ensure_base_image() {
  local official="$1" aliased="$2"
  if docker image inspect "$aliased" >/dev/null 2>&1; then
    c_ok "已就绪：$aliased"
    return 0
  fi
  c_info "拉取 $official（经 registry-mirrors）"
  if docker pull "$official" >/dev/null 2>&1; then
    docker tag "$official" "$aliased"
    c_ok "别名映射完成：$official → $aliased"
  else
    die "拉取 $official 失败。请先修好镜像加速源：
       1) 测连通性：curl -s -o /dev/null -w '%{http_code}\\n' -m 8 https://mirror.ccs.tencentyun.com/v2/
          （返回 200 或 401 都算可用）
       2) 写入 /etc/docker/daemon.json 的 registry-mirrors 后 sudo systemctl restart docker"
  fi
}

ensure_base_image "python:3.11-slim"       "docker.m.daocloud.io/library/python:3.11-slim"
ensure_base_image "pgvector/pgvector:pg16" "docker.m.daocloud.io/pgvector/pgvector:pg16"
ensure_base_image "redis:7-alpine"         "docker.m.daocloud.io/library/redis:7-alpine"
# 注：Dockerfile.web 用到的 node:20-alpine / nginx:alpine 不在此清单 ——
#     web 镜像由本地构建后 docker save/scp/load 送达，服务器既不构建、
#     也不会用到这两个基础镜像（多阶段构建只保留运行层的 nginx:alpine，
#     且该层已随镜像 tar 一并送达）。

# =====================================================================
# 2. 准备前端镜像
# =====================================================================
c_info "步骤 2/8：准备前端镜像 $WEB_IMAGE"

if docker image inspect "$WEB_IMAGE" >/dev/null 2>&1; then
  c_ok "镜像已存在，跳过加载"
else
  if [ -f "$WEB_TARBALL" ]; then
    c_info "从 $WEB_TARBALL 加载镜像（约 25~80MB，请稍候）"
    docker load -i "$WEB_TARBALL"
  elif [ -f "${WEB_TARBALL}.gz" ]; then
    c_info "从 ${WEB_TARBALL}.gz 解压并加载镜像"
    gunzip -c "${WEB_TARBALL}.gz" | docker load
  else
    die "镜像 $WEB_IMAGE 不存在，且未找到 $WEB_TARBALL(.gz)
     请在本地执行：
       docker build -f Dockerfile.web -t $WEB_IMAGE .
       docker save $WEB_IMAGE -o aicook-web.tar
       scp aicook-web.tar root@<服务器IP>:$ROOT/"
  fi
  docker image inspect "$WEB_IMAGE" >/dev/null 2>&1 || die "镜像加载后仍不存在，请检查 tar 包完整性"
fi
c_ok "前端镜像就绪（不会在服务器触发构建）"

# =====================================================================
# 2. 构建后端镜像（纯 Python wheel，服务器本地构建）
# =====================================================================
c_info "步骤 3/8：构建后端 api 镜像"
"${COMPOSE[@]}" build api
c_ok "api 镜像构建完成"

# =====================================================================
# 3. 启动全栈
# =====================================================================
c_info "步骤 4/8：启动容器栈（db → api → web，按依赖顺序）"
"${COMPOSE[@]}" up -d
"${COMPOSE[@]}" ps
c_ok "容器已拉起"

# =====================================================================
# 4. 等待健康检查（经 nginx 反代，验证 nginx → api → db 全链路）
# =====================================================================
c_info "步骤 5/8：等待后端就绪（最长 ${HEALTH_TIMEOUT}s；首次启动需跑 alembic 迁移）"
HEALTH_URL="http://127.0.0.1:${WEB_PORT}/v1/healthz"
ok=0
for i in $(seq 1 $((HEALTH_TIMEOUT / 3))); do
  if curl -fsS -m 5 "$HEALTH_URL" >/dev/null 2>&1; then ok=1; break; fi
  sleep 3
done
if [ "$ok" -eq 1 ]; then
  c_ok "健康检查通过：$HEALTH_URL"
else
  c_err "健康检查超时：$HEALTH_URL"
  echo "----- 最近 60 行 api 日志 -----"
  "${COMPOSE[@]}" logs --tail=60 api || true
  die "启动失败，请对照上方日志排查（迁移失败 / 数据库不可达 / 端口占用）"
fi

# =====================================================================
# 5. 安全断言：8000 不得在宿主机监听
# =====================================================================
c_info "步骤 6/8：安全断言"
if command -v ss >/dev/null 2>&1 && ss -ltn 2>/dev/null | grep -qE ':8000[[:space:]]'; then
  die "宿主机 8000 端口正在监听 —— 后端不应对外暴露。请检查 compose 覆盖是否生效。"
fi
c_ok "宿主机未监听 8000（后端仅容器内网可达）"

# =====================================================================
# 6. 可选：种子数据初始化
# =====================================================================
if [ "$DO_SEED" -eq 1 ]; then
  c_info "步骤 7/8：执行种子数据初始化（幂等，可重复执行）"
  c_warn "即将导入：食材 / 菜谱语料 / 风控规则 / 管理员账号。首次约 1~5 分钟。"
  "${COMPOSE[@]}" exec -T api python -m app.seed
  c_ok "种子数据初始化完成"
  echo "----- 复核数据量 -----"
  "${COMPOSE[@]}" exec -T db psql -U postgres -d aicook -c \
    "SELECT (SELECT count(*) FROM recipe) AS recipes, (SELECT count(*) FROM ingredient) AS ingredients;" \
    || c_warn "数据量复核失败（表名可能不同，不影响部署）"
else
  c_info "步骤 7/8：跳过种子初始化（未指定 --seed）"
fi

# =====================================================================
# 7. 冒烟验证
# =====================================================================
c_info "步骤 8/8：冒烟验证"
smoke() {
  local path="$1" label="$2"
  local code
  code="$(curl -s -o /dev/null -w '%{http_code}' -m 10 "http://127.0.0.1:${WEB_PORT}${path}" || true)"
  code="${code:-000}"
  if [ "$code" = "200" ]; then
    c_ok "$label → 200（$path）"
  else
    c_err "$label → $code（$path）"
    return 1
  fi
}
smoke "/v1/healthz" "后端健康检查" || die "冒烟验证失败，部署未完成"
smoke "/"           "用户端首页" || die "冒烟验证失败，部署未完成"
smoke "/admin/"     "管理后台" || die "冒烟验证失败，部署未完成"

PUBLIC_IP="$(curl -s -m 5 https://ifconfig.me 2>/dev/null || echo '<服务器公网IP>')"
echo "$RAIL"
c_ok "部署完成"
cat <<EOF

 访问地址（需在阿里云 ECS 安全组入站放行 TCP ${WEB_PORT}，并确认已配置公网 IP）：
   用户端    http://${PUBLIC_IP}:${WEB_PORT}/
   管理后台  http://${PUBLIC_IP}:${WEB_PORT}/admin/
   健康检查  http://${PUBLIC_IP}:${WEB_PORT}/v1/healthz

 常用运维命令（在 $ROOT 下执行）：
   查看状态  docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml ps
   查看日志  docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml logs -f api
   停止服务  docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml down
   🔴 禁止   docker compose ... down -v   （会删除 pgdata / uploads 命名卷，数据不可恢复）

 更新发版流程：
   本地 docker build -f Dockerfile.web -t ${WEB_IMAGE} . && docker save ...
   → scp 到服务器 → bash scripts/deploy.sh（镜像已存在则自动复用）
EOF
echo "$RAIL"
