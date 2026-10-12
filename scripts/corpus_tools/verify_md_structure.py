"""校验改动后的 md 仍满足种子解析所需的结构锚点。

背景：
    本次为 189 道菜插入了图片引用行（第 3 行），并把 172 个 md 移入同名子目录。
    corpus_howtocook.py 的解析依赖固定结构锚点，且用 RE_IMAGE_LINE 剥离图片行。
    本脚本确认：① 每个 md 仍有 H1 标题；② 仍有「必备原料和工具」小节；
    ③ 仍有「操作/步骤」小节；④ 新插入的图片行可被 RE_IMAGE_LINE 正确剥离。

参数：
    无。

返回值：
    无（打印校验结果）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

DISHES = Path(r"D:/Code_Work/AI_Cook/backend/data/HowToCook/dishes")
MANIFEST = Path(r"/tmp/htc_manifest.json")

# 与 corpus_howtocook.RE_IMAGE_LINE 保持一致的剥离规则
RE_IMAGE_LINE = re.compile(r"!\[[^\]]*\]\([^)]*\)")


def main() -> None:
    """对清单内 189 个 md 逐项检查结构锚点。"""
    items = json.loads(MANIFEST.read_text(encoding="utf-8"))
    bad: list[str] = []
    for item in items:
        p = DISHES / item["cat"] / item["dish"] / f"{item['dish']}.md"
        if not p.exists():
            bad.append(f"{item['cat']}/{item['dish']} 文件缺失")
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        has_h1 = bool(re.search(r"^#\s+\S", text, re.M))
        has_ing = "必备原料" in text or "原料" in text
        has_step = "操作" in text or "步骤" in text
        # 图片行可被剥离：剥离后不应再残留 md 图片语法
        stripped = RE_IMAGE_LINE.sub("", text)
        no_img_left = "![" not in stripped
        if not (has_h1 and has_ing and has_step and no_img_left):
            bad.append(
                f"{item['cat']}/{item['dish']}: h1={has_h1} 原料={has_ing} "
                f"步骤={has_step} 图片行可剥离={no_img_left}"
            )

    print(f"检查 {len(items)} 个 md，结构异常 {len(bad)}")
    for b in bad[:20]:
        print("   ", b)


if __name__ == "__main__":
    main()
