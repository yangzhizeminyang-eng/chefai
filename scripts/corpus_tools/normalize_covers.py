"""图片归一化脚本：把生成图重命名/压缩为标准封面 `<菜名>.jpg`。

约定（对齐 HowToCook 上游）：
    - 主图命名为 `<菜名>.jpg`（上游主流：同名 94 例）；
    - md 中的引用为 `./<菜名>.jpg`。

处理规则：
    - 在菜品目录中查找「非标准命名」的图片文件（生成器输出的长文件名）；
    - 取尺寸最大的一张，转 JPEG（quality=85，最长边限制 1536）后写为 `<菜名>.jpg`；
    - 删除原始生成文件，避免语料体积膨胀（PNG 单张约 2.4MB → JPEG 约 200KB）。

幂等：目录内已存在 `<菜名>.jpg` 且无其他杂图时跳过。
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from PIL import Image

DISHES = Path(r"D:/Code_Work/AI_Cook/backend/data/HowToCook/dishes")
MANIFEST = Path(r"/tmp/htc_manifest.json")
IMG_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif")
MAX_EDGE = 1536
JPEG_QUALITY = 85


def normalize(folder: Path, dish: str, dry_run: bool = False) -> tuple[bool, str]:
    """把目录内非标准图片归一为 <dish>.jpg。

    参数：
        folder：菜品目录。
        dish：菜名。
        dry_run：只报告不落盘。

    返回值：
        (是否处理, 说明文本)。
    """
    if not folder.is_dir():
        return False, "目录不存在"
    target = folder / f"{dish}.jpg"
    candidates = [
        f for f in sorted(folder.iterdir())
        if f.is_file()
        and f.suffix.lower() in IMG_EXT
        and f.name != f"{dish}.jpg"
        and f.stem != dish
    ]
    if not candidates:
        return False, "无需处理"
    if target.exists() and not dry_run:
        # 已有标准图：仅清理杂图
        for f in candidates:
            f.unlink()
        return True, f"已存在 {target.name}，清理杂图 {len(candidates)}"

    # 取尺寸最大者作为主图
    best, best_px = None, -1
    for f in candidates:
        try:
            with Image.open(f) as im:
                px = im.width * im.height
        except Exception:  # noqa: BLE001 —— 损坏文件跳过
            continue
        if px > best_px:
            best, best_px = f, px
    if best is None:
        return False, "无可用图片"

    if dry_run:
        return True, f"[DRY] {best.name} -> {dish}.jpg ({best_px}px)"

    with Image.open(best) as im:
        im = im.convert("RGB")
        if max(im.size) > MAX_EDGE:
            ratio = MAX_EDGE / max(im.size)
            im = im.resize(
                (round(im.width * ratio), round(im.height * ratio)),
                Image.LANCZOS,
            )
        im.save(target, "JPEG", quality=JPEG_QUALITY, optimize=True)

    for f in candidates:
        if f != best:
            f.unlink()
    best.unlink()
    return True, f"{dish}.jpg ({target.stat().st_size // 1024}KB)"


def main() -> None:
    """批量归一化清单内所有菜品目录。"""
    parser = argparse.ArgumentParser(description="归一化菜品封面图片")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if args.limit:
        manifest = manifest[: args.limit]

    done = failed = 0
    for item in manifest:
        folder = DISHES / item["cat"] / item["dish"]
        ok, msg = normalize(folder, item["dish"], dry_run=args.dry_run)
        if ok:
            done += 1
            print(f"  [OK] {item['cat']}/{item['dish']}: {msg}")
        elif msg != "无需处理":
            failed += 1
            print(f"  [SKIP] {item['cat']}/{item['dish']}: {msg}")
    total_mb = 0.0
    for item in manifest:
        p = DISHES / item["cat"] / item["dish"] / f"{item['dish']}.jpg"
        if p.exists():
            total_mb += p.stat().st_size / 1024 / 1024
    print(f"{'[DRY-RUN] ' if args.dry_run else ''}处理 {done}，跳过/失败 {failed}，"
          f"标准图总体积 {total_mb:.1f}MB")


if __name__ == "__main__":
    main()
