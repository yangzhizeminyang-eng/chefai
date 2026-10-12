"""语料图片补齐后的整体校验。

校验项：
    1. 每个菜品 md 所在目录（含子目录）是否存在图片；
    2. md 中每一处 `![...](./相对路径)` 引用的文件是否真实存在（引用完整性）；
    3. 是否存在遗漏的生成图（长文件名 png）；
    4. 语料体积与图片总数统计。
"""

from __future__ import annotations

import os
import re
from pathlib import Path

DISHES = Path(r"D:/Code_Work/AI_Cook/backend/data/HowToCook/dishes")
IMG_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif")
REF_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


def main() -> None:
    """执行校验并打印结果。"""
    total = no_img = 0
    broken: list[tuple[str, str]] = []
    for dp, _dn, fn in os.walk(DISHES):
        for f in fn:
            if not f.endswith(".md"):
                continue
            total += 1
            d = Path(dp)
            has_img = any(
                x.lower().endswith(IMG_EXT)
                for r in [d, *d.rglob("*")]
                for x in ([r.name] if r == d else [])
            )
            if not has_img:
                has_img = any(
                    p.is_file() and p.suffix.lower() in IMG_EXT for p in d.rglob("*")
                )
            if not has_img:
                no_img += 1
                print(f"  [缺图] {d.relative_to(DISHES)}/{f}")

            text = (d / f).read_text(encoding="utf-8", errors="ignore")
            for url in REF_RE.findall(text):
                url = url.strip()
                if url.startswith(("http://", "https://", "#", "mailto:", "data:")):
                    continue
                target = (d / url).resolve()
                if not target.exists():
                    broken.append((str(d.relative_to(DISHES)) + "/" + f, url))

    imgs = [p for p in DISHES.rglob("*") if p.is_file() and p.suffix.lower() in IMG_EXT]
    strays = [p for p in imgs if p.stem.startswith("写实菜品成品摄影")]
    size_mb = sum(p.stat().st_size for p in imgs) / 1024 / 1024

    print(f"菜品 md 总数：{total}　缺图目录：{no_img}")
    print(f"图片文件总数：{len(imgs)}　总体积：{size_mb:.1f}MB")
    print(f"生成图残留（未归位）：{len(strays)}")
    print(f"md 引用破损：{len(broken)}")
    for f, u in broken[:20]:
        print(f"   {f} -> {u}")


if __name__ == "__main__":
    main()
