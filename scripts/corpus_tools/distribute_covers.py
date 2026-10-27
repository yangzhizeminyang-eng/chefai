"""封面分配脚本：把生成图按文件名中的菜名归位为 `<分类>/<菜名>/<菜名>.jpg`。

背景：
    图片生成并行调用时 output_dir 会被统一到同一个目录（实测 6 个不同 output_dir
    的图全部落进同一个菜品目录），因此采用「统一暂存 + 按文件名分配」策略：
    生成 prompt 固定以 `写实菜品成品摄影：<菜名>，...` 开头，
    生成文件名形如 `写实菜品成品摄影_<菜名>_<其余描述>_<时间戳>.png`。

匹配规则（消歧）：
    1. 取 `写实菜品成品摄影` 之后的第一个 `_` 分段作为候选名；
    2. 候选名与清单菜名精确相等 → 命中；
    3. 否则取「候选名以某菜名开头」中最长的那个 → 命中（如 红烧鱼头 优于 红烧鱼）；
    4. 仍不命中 → 查人工别名表（记录 prompt 与菜名不一致的情形）；
    5. 都不命中 → 报错列出，不猜测。

输出：
    - 转 JPEG（最长边 1536、quality 85）写入目标目录为 `<菜名>.jpg`；
    - 删除暂存原图。
"""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path

from PIL import Image

DISHES = Path(__file__).resolve().parents[2] / "backend" / "data" / "HowToCook" / "dishes"
STAGING = Path(__file__).resolve().parents[2] / ".tmp" / "corpus_covers"
MANIFEST = Path(tempfile.gettempdir()) / "htc_manifest.json"

PREFIX = "写实菜品成品摄影"
IMG_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif")
MAX_EDGE = 1536
JPEG_QUALITY = 85

# prompt 与正式菜名不一致的人工别名（仅记录已知偏差，不做模糊猜测）
ALIAS = {
    "葱姜蒸黑鳕鱼": "微波葱姜黑鳕鱼",
}


def load_dishes() -> dict[str, str]:
    """读取清单，返回 {菜名: 分类}。

    返回值：
        dict[str, str]：菜名到分类的映射。
    """
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {item["dish"]: item["cat"] for item in manifest}


def resolve(candidate: str, dishes: dict[str, str]) -> str | None:
    """把候选名解析为清单中的正式菜名。

    说明：
        生成文件名会把「（）：，」等标点替换为 `_`，故像「酸梅汤（半成品加工）」
        的候选名会退化为「酸梅汤」。因此匹配需**双向**：既支持候选名以菜名开头
        （红烧鱼头 > 红烧鱼），也支持菜名以候选名开头。

    参数：
        candidate：文件名首段提取出的候选名。
        dishes：菜名→分类映射。

    返回值：
        str | None：命中的正式菜名，未命中返回 None。
    """
    if not candidate:
        return None
    if candidate in dishes:
        return candidate
    if candidate in ALIAS and ALIAS[candidate] in dishes:
        return ALIAS[candidate]
    hits = [d for d in dishes if d.startswith(candidate) or candidate.startswith(d)]
    if hits:
        # 取最长者（如 红烧鱼头 优先于 红烧鱼；酸梅汤（半成品加工）优先于 酸梅汤）
        return max(hits, key=len)
    return None


def collect_sources() -> list[Path]:
    """收集待分配的生成图（暂存目录 + 语料内散落文件）。

    返回值：
        list[Path]：生成图路径列表。
    """
    found: list[Path] = []
    if STAGING.is_dir():
        found.extend(p for p in STAGING.iterdir() if p.is_file() and p.suffix.lower() in IMG_EXT)
    for p in DISHES.rglob(f"{PREFIX}*"):
        if p.is_file() and p.suffix.lower() in IMG_EXT:
            found.append(p)
    return sorted(found)


def main() -> None:
    """执行分配。"""
    parser = argparse.ArgumentParser(description="按文件名把生成图归位")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    dishes = load_dishes()
    sources = collect_sources()
    print(f"待分配生成图：{len(sources)}")

    ok = unmatched = 0
    unmatched_list: list[str] = []
    undeleted: list[Path] = []
    for src in sources:
        stem = src.stem
        parts = stem.split("_")
        candidate = parts[1] if len(parts) > 1 and parts[0] == PREFIX else stem
        dish = resolve(candidate, dishes)
        if dish is None:
            unmatched += 1
            unmatched_list.append(src.name)
            continue
        folder = DISHES / dishes[dish] / dish
        target = folder / f"{dish}.jpg"
        if args.dry_run:
            print(f"  [DRY] {src.name}  ->  {dishes[dish]}/{dish}/{dish}.jpg")
            ok += 1
            continue
        folder.mkdir(parents=True, exist_ok=True)
        with Image.open(src) as im:
            im = im.convert("RGB")
            if max(im.size) > MAX_EDGE:
                ratio = MAX_EDGE / max(im.size)
                im = im.resize((round(im.width * ratio), round(im.height * ratio)), Image.LANCZOS)
            im.save(target, "JPEG", quality=JPEG_QUALITY, optimize=True)
        # 删除暂存原图：环境的安全删除机制偶发失败，失败则登记待重试（不影响已交付的 jpg）
        try:
            src.unlink()
        except OSError as exc:
            print(f"  [WARN] 暂存图删除失败（已交付），稍后重试：{src.name} :: {exc}")
            undeleted.append(src)
        ok += 1
        print(f"  [OK] {dish}.jpg ({target.stat().st_size // 1024}KB)")

    # 重试未删除的暂存图
    still: list[Path] = []
    for p in undeleted:
        try:
            p.unlink()
        except OSError:
            still.append(p)

    if unmatched_list:
        print(f"\n未匹配 {unmatched} 个：")
        for n in unmatched_list:
            print("   ", n)
    if still:
        print(f"\n仍有 {len(still)} 个暂存图未能删除（需手工清理 {STAGING}）：")
        for p in still:
            print("   ", p.name)
    elif not args.dry_run and STAGING.is_dir() and not any(STAGING.iterdir()):
        shutil.rmtree(STAGING, ignore_errors=True)
    print(f"\n{'[DRY-RUN] ' if args.dry_run else ''}成功 {ok}，未匹配 {unmatched}，"
          f"暂存残留 {len(still)}")


if __name__ == "__main__":
    main()
