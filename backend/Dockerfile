# =====================================================================
# 文件名: backend/Dockerfile
# 用途:   「AI 厨娘」后端 FastAPI 镜像（多阶段构建）
#         - builder 阶段：python:3.11-slim 安装 requirements.txt 至 /install 前缀；
#         - 运行阶段：python:3.11-slim 携带依赖与 app/ alembic/ alembic.ini，
#           启动前先执行 alembic upgrade head（迁移失败即退出，防止半可用状态），
#           成功后前台运行 uvicorn（0.0.0.0:8000）；
#         - HEALTHCHECK 以 python urllib 探测 /healthz 根级口径
#           （数据库不可达时 handler 返回 503，urlopen 抛异常 → unhealthy）；
#         - 数据库/LLM/管理员配置全部经环境变量注入（compose 中 DB_HOST=db），
#           不将 .env 打入镜像（.dockerignore 已排除，避免密钥泄漏）。
# 构建:   docker build -t aicook-api ./backend
# =====================================================================

# ---------- builder：安装依赖（构建残留不进入运行层） ----------
# 基础镜像走 docker.m.daocloud.io 加速前缀：当前网络直连 Docker Hub 会被劫持
# （registry 元数据返回 text/html）；如需官方源，删除前缀改回 python:3.11-slim 即可
FROM docker.m.daocloud.io/library/python:3.11-slim AS builder
# 与 manage.ps1 setup 同口径的 PyPI 镜像加速（官方源在当前网络下仅 ~30KB/s）
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
WORKDIR /build
COPY requirements.txt ./
RUN pip install --prefix=/install -r requirements.txt

# ---------- runtime：仅携带运行所需产物 ----------
FROM docker.m.daocloud.io/library/python:3.11-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
# pip --prefix=/install 的 bin 与 site-packages 恰好映射到 /usr/local 的同名路径
COPY --from=builder /install /usr/local
# 业务代码与 Alembic 迁移（tests/data/.env 由 backend/.dockerignore 排除）
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
EXPOSE 8000
# 健康检查：slim 镜像无 curl，用标准库 urllib 探测（数据库异常 503 视为不健康）
HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=5 \
    CMD ["python", "-c", "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).getcode() == 200 else 1)"]
# 先迁移后启动：alembic 失败直接退出（compose 依 restart 策略重试），成功则 exec 交棒 uvicorn
ENTRYPOINT ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${APP_PORT:-8000}"]
