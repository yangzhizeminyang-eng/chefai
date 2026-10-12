"""修补根 README 中指向已迁移菜品的旧链接。

背景：
    迁移把 `dishes/<cat>/<dish>.md` 移入 `dishes/<cat>/<dish>/<dish>.md`，
    需同步改写 README 索引。首次迁移中断导致部分链接未改写，本脚本做收敛补齐。

规则：
    对 README 中形如 `(dishes/<cat>/<name>.md)` 的链接，若同名的
    `dishes/<cat>/<name>/<name>.md` 实际存在，则改写为新路径。
"""

from __future__ import annotations

import re
from pathlib import Path

README = Path(r"D:/Code_Work/AI_Cook/backend/data/HowToCook/README.md")
DISHES = Path(r"D:/Code_Work/AI_Cook/backend/data/HowToCook/dishes")

LINK_RE = re.compile(r"\(dishes/([^/()]+)/([^/()]+)\.md\)")


def main() -> None:
    """改写 README 中的过期菜品链接。"""
    text = README.read_text(encoding="utf-8")
    changed = 0

    def _sub(m: re.Match[str]) -> str:
        nonlocal changed
        cat, name = m.group(1), m.group(2)
        target = DISHES / cat / name / f"{name}.md"
        if target.exists():
            changed += 1
            return f"(dishes/{cat}/{name}/{name}.md)"
        return m.group(0)

    new_text = LINK_RE.sub(_sub, text)
    README.write_text(new_text, encoding="utf-8", newline="")
    print(f"README 链接改写：{changed} 条")

    # 复核：是否仍有指向已迁移菜品的旧链接
    leftover = [
        m.group(0)
        for m in LINK_RE.finditer(new_text)
        if (DISHES / m.group(1) / m.group(2) / f"{m.group(2)}.md").exists()
    ]
    print(f"复核剩余过期链接：{len(leftover)}")
    for x in leftover[:10]:
        print("   ", x)


if __name__ == "__main__":
    main()
