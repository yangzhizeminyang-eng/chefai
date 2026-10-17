"""智谱/百炼/哈希向量回填 CLI（python -m app.embedding_backfill）。

职责：
    为 published 官方菜谱按当前配置的嵌入提供方回填向量并自检（阶段 3
    智谱 embedding-3 2048 维空间切换工具）：
        1. 打印当前配置（Provider/space_name/维度/目标列，绝不打印 API Key）；
        2. 调 ensure_embeddings 回填并输出 planned/written/remaining 统计：
           - 全量模式（默认）：幂等，已存在目标空间 verified 行的菜谱自动跳过，
             planned=待处理数、重复执行不增行；
           - 限量模式（--limit N）：最多回填 N 条待处理记录——在 embed 之前
             截断，真实调用远程 API 并写入（非 dry-run 预演）；
           - --force：事务内 upsert 覆盖重算（按 recipe_id 覆盖已有行），
             远程嵌入/写库失败自动回滚、旧行无损，进程非 0 退出——绝不
             「先删后填」，消除 force 失败导致空空间不可恢复的风险；
        3. 自检（按模式分流）：
           - 全量模式 self_check：目标空间 verified 行数 vs published 菜谱数
             （coverage ≥ 0.999）+ 抽样校验向量维度与数值合法性（math.isfinite）；
           - 限量模式 partial_check：仅对目标空间已有行抽样做维度/合法性校验，
             不输出全量 coverage PASS 结论（限量天然不覆盖全部）；
        4. 输出摘要；自检失败（含 partial_check FAIL）退出码非 0（供切流流水线判定）。

用法（Windows PowerShell，backend/ 目录下）：
    .venv\\Scripts\\python.exe -m app.embedding_backfill --provider zhipu
    .venv\\Scripts\\python.exe -m app.embedding_backfill --provider hash --limit 5
    .venv\\Scripts\\python.exe -m app.embedding_backfill --provider zhipu --force

切流与回退（详见 backend/README.md「向量空间切换」一节）：
    - 回填完成后检索自然按新空间过滤（embedding_model 列）实现切流；
    - 旧空间（hash-v1 / qwen3.7-text-embedding）向量行与索引在验证期一律
      保留，绝不删除；回退仅需把 EMBEDDING_PROVIDER 改回旧提供方并重启。

异常：
    数据库不可达 / 回填失败（含 force 失败上抛，旧行已自动回滚）/ 自检不通过
    时进程以非 0 退出码结束。
"""

from __future__ import annotations

import argparse
import math
import sys
from typing import TYPE_CHECKING

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

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """解析命令行参数（函数）。

    参数：
        argv：命令行参数列表；None 时使用 sys.argv（测试注入便利）。

    返回值：
        argparse.Namespace：provider（可空，缺省走 settings）/force/limit。

    异常：
        SystemExit：参数不合法时 argparse 自动退出（退出码 2）。
    """
    parser = argparse.ArgumentParser(
        prog="python -m app.embedding_backfill",
        description="为 published 菜谱回填当前嵌入空间向量并自检（幂等；--limit 限量真实写入）",
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
        help="事务内强制覆盖重算（按 recipe_id upsert 已有行；远程嵌入失败自动回滚，旧行无损）",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="限量回填：最多回填 N 条待处理记录（真实调用远程 API 并写入，非 dry-run 预演）",
    )
    return parser.parse_args(argv)


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


def _count_pending(session: Session, space: str) -> int:
    """统计目标空间待回填的 published 菜谱数（函数，与 ensure_embeddings 内部过滤一致）。

    说明：
        pending = |published 菜谱 ID 集合 − 已有目标空间 verified 行的菜谱 ID 集合|
        （集合差语义与 ensure_embeddings 的 targets 过滤一致，天然防御
        verified 行指向非 published 菜谱的脏数据）。

    参数：
        session：数据库会话（只读）。
        space：目标嵌入空间标识。

    返回值：
        int：待回填数量（最小 0）。

    异常：
        数据库异常向上抛出。
    """
    published_ids = {
        int(rid)
        for (rid,) in session.execute(select(Recipe.id).where(Recipe.status == "published")).all()
    }
    existing_ids = {
        int(rid)
        for (rid,) in session.execute(
            select(RecipeEmbedding.recipe_id)
            .where(RecipeEmbedding.source == "verified")
            .where(RecipeEmbedding.embedding_model == space)
            .where(RecipeEmbedding.recipe_id.is_not(None))
        ).all()
    }
    return max(0, len(published_ids - existing_ids))


def _sample_check_rows(
    session: Session, space: str, dimension: int
) -> tuple[list[int], list[int], int]:
    """抽样校验目标空间向量的维度与数值合法性（模块私有函数，自检共用内核）。

    参数：
        session：数据库会话。
        space：目标嵌入空间标识。
        dimension：期望向量维度。

    返回值：
        tuple[list[int], list[int], int]：(维度不符行下标, 含非有限值行下标, 抽样行数)。

    异常：
        数据库异常向上抛出。
    """
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
    return dim_bad, finite_bad, len(sample_rows)


def _self_check(session: Session, space: str, dimension: int) -> tuple[bool, str]:
    """全量回填后自检（函数）：行数覆盖率 + 抽样向量合法性。

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
    dim_bad, finite_bad, _ = _sample_check_rows(session, space, dimension)
    ok = coverage >= 0.999 and not dim_bad and not finite_bad
    detail = (
        f"coverage={verified_count}/{published_count}={coverage:.3f}, "
        f"dim_check={'ok' if not dim_bad else f'bad_rows={dim_bad}'}, "
        f"finite_check={'ok' if not finite_bad else f'bad_rows={finite_bad}'}"
    )
    return ok, detail


def _partial_self_check(session: Session, space: str, dimension: int) -> tuple[bool, str]:
    """限量回填后局部自检（函数）：仅对目标空间已有行抽样校验维度与合法性。

    说明：
        与全量 _self_check 的区别：不产出全局 coverage 结论（限量模式天然
        不覆盖全部 published，输出 coverage=PASS 会误导切流判定）；仅对目标
        空间已有 verified 行抽样（≤5 条）做维度与 math.isfinite 校验，
        输出形如 partial_check=ok|FAIL。

    参数：
        session：数据库会话。
        space：目标嵌入空间标识。
        dimension：期望向量维度。

    返回值：
        tuple[bool, str]：(是否通过, 说明文本；空间无行时判 FAIL)。

    异常：
        数据库异常向上抛出。
    """
    dim_bad, finite_bad, sampled = _sample_check_rows(session, space, dimension)
    if sampled == 0:
        return False, "sampled=0 (no rows in target space)"
    ok = not dim_bad and not finite_bad
    detail = (
        f"sampled={sampled}, "
        f"dim_check={'ok' if not dim_bad else f'bad_rows={dim_bad}'}, "
        f"finite_check={'ok' if not finite_bad else f'bad_rows={finite_bad}'}"
    )
    return ok, detail


def main(argv: list[str] | None = None) -> int:
    """CLI 主入口（函数）。

    参数：
        argv：命令行参数列表；None 时使用 sys.argv（测试注入便利）。

    返回值：
        int：0 成功；1 自检不通过（含限量 partial_check FAIL）；2 参数/连接/
          回填异常（force 失败旧行已自动回滚，同样以 2 退出）。

    异常：
        不向上抛出（异常统一捕获后按退出码退出，输出错误摘要）。
    """
    args = _parse_args(argv)
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
            pending = _count_pending(session, space)
            planned = pending if args.limit is None else min(max(0, args.limit), pending)
            if args.force:
                print("[backfill] --force: 事务内 upsert 覆盖模式（失败自动回滚，旧行无损）")
            written = ensure_embeddings(session, provider, limit=args.limit, force=args.force)
            remaining = max(0, pending - written)
            if args.limit is None:
                ok, detail = _self_check(session, space, dim)
                verdict = f"self_check={'PASS' if ok else 'FAIL'} ({detail})"
            else:
                ok, detail = _partial_self_check(session, space, dim)
                verdict = f"partial_check={'ok' if ok else 'FAIL'} ({detail})"
    except Exception as exc:  # noqa: BLE001 —— 数据库不可达/force 失败等统一退出
        print(f"[backfill][ERROR] database/backfill failed: {exc}")
        return 2

    print(f"[backfill] planned={planned}")
    print(f"[backfill] written={written}")
    print(f"[backfill] remaining={remaining}")
    print(f"[backfill] {verdict}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
