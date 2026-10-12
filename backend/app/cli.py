"""嵌入向量重建 CLI（GAP-5 修复：兑现《05-操作手册》§5.5 承诺的运维入口）。

职责：
    提供 `python -m app.cli build_embeddings` 全量/增量向量重建命令（GAP-5：
    《05-操作手册》§5.5 承诺该命令此前不存在，本模块补齐）；显式构造嵌入
    提供方（🔴 不走 get_embedding_provider() 单例——工厂在 bailian 失败时
    静默回落 hash，运维工具绝不能静默降级，空间标签与向量内容必须严格对应）；
    重建模式仅删除目标空间的 verified 行（ai_private 用户创新菜向量绝不触碰，
    其他嵌入空间行一律不碰）。

用法示例：
    # 增量回填（幂等，仅补缺：当前 provider 空间下缺向量的 published 菜谱）
    python -m app.cli build_embeddings

    # 全量重建：先删除目标空间的 verified 向量行，再按当前 provider 全量回填
    python -m app.cli build_embeddings --rebuild

    # 显式指定目标嵌入空间与批大小（bailian 升级场景）
    python -m app.cli build_embeddings --rebuild --model qwen3.7-text-embedding --batch 20

GAP-5 修复说明：
    《05-操作手册》§5.5 曾承诺 `python -m app.cli build_embeddings` 可用于
    向量模型升级后的全量重建，但仓库中并无 app/cli.py，属文档与实现脱节。
    本模块即该缺陷的修复：命令、参数与手册描述对齐，并在 epilog 中附
    GAP-8 的 pgvector REINDEX 运维指引与嵌入空间切换四段式。

异常约定：
    EmbeddingUnavailableError（bailian 配置缺失/调用失败）与数据库异常统一
    由 main 兜底打印并返回退出码 1；ensure_embeddings 自身不抛出（内部
    rollback 返回已写计数），重建模式以「删除 >0 但回填 =0」作为可疑信号
    打印 WARNING 提示检查提供方可用性。
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import delete
from sqlalchemy.exc import SQLAlchemyError

from app.ability.embedding import (
    BailianEmbeddingProvider,
    EmbeddingProvider,
    EmbeddingUnavailableError,
    HashEmbeddingProvider,
    ensure_embeddings,
)
from app.core.config import settings
from app.core.db import SessionLocal
from app.models import RecipeEmbedding

# epilog：GAP-8 运维指引（ivfflat REINDEX + 嵌入空间切换四段式）
_EPILOG = """\
运维提示：pgvector ivfflat 索引 lists 参数建议随数据量校正（lists ≈ √n，
当前 ≈400 行建议 lists=20），属 REINDEX 运维动作不进应用迁移：
  DROP INDEX IF EXISTS idx_emb_vector;
  CREATE INDEX idx_emb_vector ON recipe_embedding
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 20);
切换嵌入空间四段式：双写 → 校验 → 切流（EMBEDDING_PROVIDER 改 bailian 后重启）→ 清理旧空间行。
"""


def _build_provider() -> EmbeddingProvider:
    """按 EMBEDDING_PROVIDER 显式构造嵌入提供方（函数，运维工具专用）。

    说明：
        🔴 有意不走 get_embedding_provider() 单例工厂：工厂在 bailian 构造
        失败时静默回落 hash，会导致「向量内容是 hash、空间标签却是 bailian
        配置的模型名」的静默降级——运维工具必须显式失败。
        取值约定：'bailian' → BailianEmbeddingProvider（配置缺失抛
        EmbeddingUnavailableError 向上）；'bgem3' → 阶段二占位未实现，
        打印错误后退出；其余（含缺省 'hash'）→ HashEmbeddingProvider。

    参数：
        无（读取全局 settings.EMBEDDING_PROVIDER）。

    返回值：
        EmbeddingProvider：按配置构造的嵌入提供方实例。

    异常：
        EmbeddingUnavailableError：bailian 配置缺失（API BASE/KEY 均为空），
        由调用方打印后以退出码 1 终止；
        SystemExit(1)：EMBEDDING_PROVIDER=bgem3（阶段二占位未实现）。
    """
    name = settings.EMBEDDING_PROVIDER.strip().lower()
    if name == "bailian":
        # 显式构造：失败抛 EmbeddingUnavailableError，绝不静默回落 hash
        return BailianEmbeddingProvider()
    if name == "bgem3":
        print(
            "[错误] EMBEDDING_PROVIDER=bgem3 为阶段二占位实现，尚未启用；"
            "请改用 'hash'（缺省）或 'bailian'。",
            file=sys.stderr,
        )
        sys.exit(1)
    return HashEmbeddingProvider()  # 缺省（含 'hash'）：确定性哈希嵌入


def _cmd_build_embeddings(args: argparse.Namespace) -> int:
    """执行 build_embeddings 子命令（函数，增量回填 / 全量重建统一入口）。

    说明：
        1. --batch 与默认不同时先覆盖 settings.EMBEDDING_BATCH_SIZE
          （BailianEmbeddingProvider 构造时读取批大小，必须先于 provider 构造）；
        2. 显式构造 provider（不走单例工厂，失败不静默降级）；
        3. 目标空间 = --model 或 provider.space_name；
        4. 增量模式：仅调 ensure_embeddings 幂等回填（其内部 commit）；
        5. 重建模式：同一会话内先用 sqlalchemy delete 删除目标空间的
          verified 行（🔴 绝不触碰 ai_private 行——用户创新菜向量 ensure
          不会回填，删除即永久丢失；其他空间行也不碰），再调
          ensure_embeddings（其内部 commit 连带提交删除；失败时内部
          rollback 把删除一并回滚，旧行不丢）；
        6. ensure_embeddings 失败不抛错（内部捕获返回已写计数），故以
          「written==0 且 deleted>0」作为可疑信号打印 WARNING。

    参数：
        args：argparse 解析结果（rebuild / model / batch 字段）。

    返回值：
        int：进程退出码（0 成功；1 提供方配置缺失）。

    异常：
        EmbeddingUnavailableError：bailian 构造失败（向上交 main 兜底）；
        SQLAlchemyError：数据库连接/查询异常（向上交 main 兜底）。
    """
    # --batch 覆盖：必须发生在 provider 构造之前（Bailian 构造时读取批大小）
    if args.batch is not None:
        if args.batch < 1:
            print(f"[错误] --batch 必须 >= 1，收到 {args.batch}。", file=sys.stderr)
            return 2
        settings.EMBEDDING_BATCH_SIZE = args.batch
        print(f"批大小已覆盖为 {args.batch}（EMBEDDING_BATCH_SIZE）。")

    provider = _build_provider()
    target_space = args.model or provider.space_name

    with SessionLocal() as session:
        deleted = 0
        if args.rebuild:
            # 只删目标空间的 verified 行：ai_private 属用户创新菜向量，
            # ensure 不会回填它们，删除即永久丢失；其他空间行一律不碰。
            result = session.execute(
                delete(RecipeEmbedding)
                .where(RecipeEmbedding.source == "verified")
                .where(RecipeEmbedding.embedding_model == target_space)
            )
            deleted = int(result.rowcount or 0)

        # ensure_embeddings 内部 commit（连带提交上面的删除）；
        # 失败时内部 rollback（删除一并回滚，旧行不丢）并返回已写计数。
        written = ensure_embeddings(session, provider, space_name=target_space)

    if args.rebuild:
        print(f"重建完成：删除旧行 {deleted}，新回填 {written} 行（空间={target_space}）")
        if written == 0 and deleted > 0:
            # ensure_embeddings 吞错不抛：删除已回滚但回填可能没成功，提示排查
            print(
                "WARNING: --rebuild 删除后回填 0 行，请检查 EMBEDDING_PROVIDER/API 凭证是否可用。",
                file=sys.stderr,
            )
    else:
        print(f"增量回填完成：本次新回填 {written} 行（空间={target_space}）")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    """构造 CLI 参数解析器（函数，含子命令注册与 GAP-8 epilog）。

    说明：
        formatter_class 用 RawDescriptionHelpFormatter 保留 epilog 原始换行
        （GAP-8 运维指引含多行 SQL，不可被 argparse 重排）。

    参数：
        无。

    返回值：
        argparse.ArgumentParser：已注册 build_embeddings 子命令的解析器。

    异常：
        无。
    """
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description="AI Cook 运维 CLI（嵌入向量重建等）。",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_build = sub.add_parser(
        "build_embeddings",
        help="回填/重建 published 官方菜谱的嵌入向量（《05-操作手册》§5.5）",
        description="为全部 published 官方菜谱回填当前嵌入空间的 verified 向量（幂等增量或全量重建）。",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_build.add_argument(
        "--rebuild",
        action="store_true",
        help="全量重建：先删除目标空间的 verified 向量行再回填（ai_private 行绝不触碰）",
    )
    p_build.add_argument(
        "--model",
        metavar="NAME",
        default=None,
        help=(
            "目标嵌入空间标识（写入 recipe_embedding.embedding_model 列）；"
            "缺省取当前 provider.space_name。应与当前 EMBEDDING_PROVIDER 实际产出的模型一致，"
            "否则空间标签与向量内容不符"
        ),
    )
    p_build.add_argument(
        "--batch",
        type=int,
        metavar="N",
        default=None,
        help="覆盖嵌入请求单批文本条数（EMBEDDING_BATCH_SIZE）；缺省用配置值",
    )
    p_build.set_defaults(func=_cmd_build_embeddings)
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI 主入口（函数，解析子命令并统一异常兜底）。

    说明：
        解析 argv（None 时取 sys.argv[1:]），分发给子命令处理函数；
        EmbeddingUnavailableError（bailian 配置缺失/不可用）与数据库异常
        （SQLAlchemyError）统一打印错误并返回退出码 1，保证运维脚本可依据
        退出码判断成败。

    参数：
        argv：命令行参数列表；None 表示使用 sys.argv[1:]。

    返回值：
        int：进程退出码（0 成功；1 提供方/数据库异常；2 参数不合法）。

    异常：
        不抛出（已知异常类别全部兜底转退出码）。
    """
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except EmbeddingUnavailableError as exc:
        print(f"[错误] 嵌入提供方不可用：{exc}", file=sys.stderr)
        return 1
    except SQLAlchemyError as exc:
        print(f"[错误] 数据库操作失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
