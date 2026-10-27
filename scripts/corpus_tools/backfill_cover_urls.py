"""回填 recipes.cover_image_url（数据库列）——封面落盘后的必要收尾步骤。

背景：
    封面资源落盘规则为 backend/assets/recipe_covers/{md5(title)[:12]}{ext}，
    接口层有两套取值路径：

        ① resolve_recipe_cover_url(title, stored_url)
           —— 按文件存在性动态补全（recipes 列表/详情、day_menu 使用）；
        ② 直接读 Recipe.cover_image_url 列
           —— 不做补全（recommend、seasonal 使用）。

    因此「图片文件存在」并不等于「所有接口都能显示」：只要 DB 列仍为 NULL，
    走 ② 的接口就会回落「暂无实拍」占位图。本脚本把所有「文件已存在但列为
    NULL」的行回填为真实 URL，使两套路径结果一致。

幂等性：
    只处理 stored_url 为空的行，已有值的行一律不动；重复执行无副作用。

用法：
    python scripts/corpus_tools/backfill_cover_urls.py --dry-run   # 只报告
    python scripts/corpus_tools/backfill_cover_urls.py --apply     # 实际写入
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.core.db import SessionLocal  # noqa: E402
from app.core.recipe_covers import COVERS_DIR, resolve_recipe_cover_url  # noqa: E402
from app.models.recipe import Recipe  # noqa: E402


def main() -> int:
    """执行回填并打印统计（函数）。"""
    parser = argparse.ArgumentParser(description="回填 recipes.cover_image_url")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="只报告，不写库")
    group.add_argument("--apply", action="store_true", help="实际写入数据库")
    args = parser.parse_args()

    if not COVERS_DIR.is_dir():
        print(f"[fatal] 封面目录不存在：{COVERS_DIR}")
        return 2

    session = SessionLocal()
    try:
        rows = session.query(Recipe.id, Recipe.title, Recipe.cover_image_url).order_by(Recipe.id).all()
        total = len(rows)
        null_rows = [r for r in rows if not r[2]]
        fillable: list[tuple[int, str, str]] = []
        unfillable: list[tuple[int, str]] = []

        for rid, title, stored in null_rows:
            resolved = resolve_recipe_cover_url(title, stored)
            if resolved:
                fillable.append((int(rid), str(title), resolved))
            else:
                unfillable.append((int(rid), str(title)))

        print(f"[stat] 菜谱总数          {total}")
        print(f"[stat] DB 列为 NULL       {len(null_rows)}")
        print(f"[stat] 可回填（文件已存在） {len(fillable)}")
        print(f"[stat] 不可回填（真缺图）   {len(unfillable)}")

        if unfillable:
            print("\n[warn] 以下菜谱确实没有封面文件，需先补图：")
            for rid, title in unfillable:
                print(f"  {rid:>4} {title}")

        if args.dry_run:
            print("\n[dry-run] 未写入数据库。前 10 条待回填：")
            for rid, title, url in fillable[:10]:
                print(f"  {rid:>4} {title:<12} -> {url}")
            return 0

        updated = 0
        for rid, _title, url in fillable:
            updated += session.query(Recipe).filter(Recipe.id == rid).update(
                {Recipe.cover_image_url: url}, synchronize_session=False
            )
        session.commit()
        print(f"\n[apply] 已回填 {updated} 行")

        # 回填后复验：不应再有「列 NULL 但文件存在」的行
        remain = [
            r for r in session.query(Recipe.id, Recipe.title, Recipe.cover_image_url).all()
            if not r[2] and resolve_recipe_cover_url(r[1], r[2])
        ]
        print(f"[verify] 仍存在『列 NULL 但文件存在』的行：{len(remain)}")
        return 0 if not remain else 1
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
