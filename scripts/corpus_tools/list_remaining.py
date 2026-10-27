"""列出清单中尚未生成标准封面的菜品（供批量生成时对照）。"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

DISHES = Path(__file__).resolve().parents[2] / "backend" / "data" / "HowToCook" / "dishes"
MANIFEST = Path(tempfile.gettempdir()) / "htc_manifest.json"


def main() -> None:
    """打印剩余菜品，按分类分组并带全局序号。"""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    remaining = []
    for item in manifest:
        p = DISHES / item["cat"] / item["dish"] / f"{item['dish']}.jpg"
        if not p.exists():
            remaining.append(item)

    print(f"剩余待生成：{len(remaining)}")
    current = None
    for idx, item in enumerate(remaining, 1):
        if item["cat"] != current:
            current = item["cat"]
            print(f"--- {current} ---")
        print(f"{idx}\t{item['dish']}")

    # 便于后续脚本按序号取用
    out = Path(tempfile.gettempdir()) / "htc_remaining.json"
    out.write_text(json.dumps(remaining, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n已写出 {out}")


if __name__ == "__main__":
    main()
