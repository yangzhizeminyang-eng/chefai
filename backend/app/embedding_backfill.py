"""智谱/百炼/哈希向量回填 CLI（python -m app.embedding_backfill）。

职责：
    为 published 官方菜谱按当前配置的嵌入提供方回填向量并自检（阶段 3
    智谱 embedding-3 2048 维空间切换工具）：
        1. 打印当前配置（Provider/space_name/维度/目标列，绝不打印 API Key）；
        2. 调 ensure_embeddings 全量回填（幂等：已存在目标空间 verified 行
           的菜谱自动跳过；--force 忽略既有行强制重算）；
        3. 自检：目标空间 verified 行数 vs published 菜谱数、抽样校验向量
           维度与数值合法性（math.isfinite）；
        4. 输出摘要；自检失败退出码非 0（供切流流水线判定）。

用法（Windows PowerShell，backend/ 目录下）：
    .venv\\Scripts\\python.exe -m app.embedding_backfill --provider zhipu
    .venv\\Scripts\\python.exe -m app.embedding_backfill --provider hash --limit 5
    .venv\\Scripts\\python.exe -m app.embedding_backfill --provider zhipu --force

切流与回退（详见 backend/README.md「向量空间切换」一节）：
    - 回填完成后检索自然按新空间过滤（embedding_model 列）实现切流；
    - 旧空间（hash-v1 / qwen3.7-text-embedding）向量行与索引在验证期一律
      保留，绝不删除；回退仅需把 EMBEDDING_PROVIDER 改回旧提供方并重启。

异常：
    数据库不可达 / 回填失败 / 自检不通过时进程以非 0 退出码结束。
"""

from __future__ import annotations

import argparse
import math
import sys

from sqlalchemy import func, select

from app.ability.embedding import (
    EMBEDDING_DIMENSION,
    ensure_embeddings,
    get_embedding_provider,
    probe_zhipu_column,
)
from app.core.config import settings
from app.core.db import SessionLocal
from app.models import Recipe, RecipeEmbedding


def _parse_args() -> argparse.Namespace:
    """解析命令行参数（函数）。

    返回值：
        argparse.Namespace：provider（可空，缺省走 settings）/force/limit。

    异常：
        SystemExit：参数不合法时 argparse 自动退出（退出码 2）。
    """
    parser = argparse.ArgumentParser(
        prog="python -m app.embedding_backfill",
        description="为 published 菜谱回填当前嵌入空间向量并自检（幂等）",
    )
    parser.add_argument(
        "--provider",
        choices=["hash", "bailian", "zhipu"],
        default=None,
        help="覆盖 EMBEDDING_PROVIDER（缺省读配置文件；切换空间用于预演/回退）",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="忽略已存在目标空间 verified 行，强制重算（幂等模式默认跳过）",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="最多回填 N 条（默认不限，调试用）"
    )
    return parser.parse_args()


def _override_provider(name: str) -> None:
    """进程内覆盖 EMBEDDING_PROVIDER 配置（函数，仅 CLI 生效）。

    说明：
        在导入链路构造工厂单例之前调用（get_embedding_provider 首次调用
        前覆盖 settings 字段），使 --provider 参数无需改 .env 即可切换空间。

    参数：
        name：提供方名称（'hash' | 'bailian' | 'zhipu'）。

    返回值：
        None。

    异常：
        无。
    """
    settings.EMBEDDING_PROVIDER = name
    if name == "zhipu":
        settings.EMBEDDING_DIMENSIONS = max(1, int(settings.EMBEDDING_DIMENSIONS))


def _force_reset(session, space: str) -> int:
    """删除目标空间既有 verified 行（--force 模式，函数）。

    参数：
        session：数据库会话。
        space：目标嵌入空间标识。

    返回值：
        int：删除的行数。

    异常：
        数据库异常向上抛出。
    """
    deleted = session.execute(
        select(func.count()).select_from(RecipeEmbedding)
        .where(RecipeEmbedding.source == "verified")
        .where(RecipeEmbedding.embedding_model == space)
    ).scalar()
    rows = session.query(RecipeEmbedding).filter(
        RecipeEmbedding.source == "verified",
        RecipeEmbedding.embedding_model == space,
    ).all()
    for row in rows:
        session.delete(row)
    session.commit()
    return int(deleted or 0)


def _self_check(session, space: str, dimension: int) -> tuple[bool, str]:
    """回填后自检（函数）：行数覆盖率 + 抽样向量合法性。

    参数：
        session：数据库会话。
        space：目标嵌入空间标识。
        dimension：期望向量维度。

    返回值：
        tuple[bool, str]：(是否通过, 说明文本)。

    异常：
        数据库异常向上抛出。
    """
    published_count = session.execute(
        select(func.count()).select_from(Recipe).where(Recipe.status == "published")
    ).scalar() or 0
    verified_count = session.execute(
        select(func.count()).select_from(RecipeEmbedding)
        .where(RecipeEmbedding.source == "verified")
        .where(RecipeEmbedding.embedding_model == space)
    ).scalar() or 0
    if published_count == 0:
        return False, "published 菜谱数为 0，请先执行 python -m app.seed"
    coverage = verified_count / published_count
    sample_rows = session.execute(
        select(RecipeEmbedding.embedding_json)
        .where(RecipeEmbedding.source == "verified")
        .where(RecipeEmbedding.embedding_model == space)
        .limit(5)
    ).scalars().all()
    dim_bad = [i for i, vec in enumerate(sample_rows) if not vec or len(vec) != dimension]
    finite_bad = [
        i for i, vec in enumerate(sample_rows)
        if vec and not all(math.isfinite(float(x)) for x in vec)
    ]
    ok = coverage >= 0.999 and not dim_bad and not finite_bad
    detail = (
        f"coverage={verified_count}/{published_count}={coverage:.3f}, "
        f"dim_check={'ok' if not dim_bad else f'bad_rows={dim_bad}'}, "
        f"finite_check={'ok' if not finite_bad else f'bad_rows={finite_bad}'}"
    )
    return ok, detail


def main() -> int:
    """CLI 主入口（函数）。

    返回值：
        int：0 成功；1 自检不通过或回填失败；2 参数/连接错误。

    异常：
        不向上抛出（异常统一捕获后按退出码退出，输出错误摘要）。
    """
    args = _parse_args()
    if args.provider:
        _override_provider(args.provider)
    try:
        provider = get_embedding_provider()
    except Exception as exc:  # noqa: BLE001 —— 工厂异常（如 bgem3 占位）直接失败退出
        print(f"[backfill][ERROR] provider init failed: {exc}")
        return 2
    space = provider.space_name
    dim = int(getattr(provider, "dimension", EMBEDDING_DIMENSION))
    column_kind = "embedding(1024)" if dim == EMBEDDING_DIMENSION else f"embedding_zhipu({probe_zhipu_column()})"
    print("[backfill] 配置概览（凭证不回显）：")
    print(f"  provider={settings.EMBEDDING_PROVIDER} space_name={space} dimension={dim}")
    print(f"  pgvector_column={column_kind}")

    try:
        with SessionLocal() as session:
            if args.force:
                removed = _force_reset(session, space)
                print(f"[backfill] --force: removed existing rows={removed}")
            written = ensure_embeddings(session, provider)
            if args.limit is not None and written > args.limit:
                print(
                    f"[backfill][WARN] 本次回填 {written} 行超过 --limit={args.limit}"
                    "（--limit 仅提示用途，不截断，防半空间）"
                )
            ok, detail = _self_check(session, space, dim)
    except Exception as exc:  # noqa: BLE001 —— 数据库不可达/失败统一退出
        print(f"[backfill][ERROR] database/backfill failed: {exc}")
        return 2

    print(f"[backfill] written={written}")
    print(f"[backfill] self_check={'PASS' if ok else 'FAIL'} ({detail})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
