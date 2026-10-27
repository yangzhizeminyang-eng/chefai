"""一次性迁移脚本：为 HowToCook 语料中缺图的 189 道菜建立「同名子目录」结构。

背景与约束：
    - 上游约定：带图菜品形如 dishes/<cat>/<dish>/<dish>.md + 图片同目录；
      无图菜品 md 直接位于 dishes/<cat>/<dish>.md（本脚本处理对象）。
    - seed 侧安全：corpus_howtocook.py 用 DISHES_DIR.rglob("*.md") 递归发现语料，
      并用 RE_IMAGE_LINE 剥离图片行 —— 改目录与加图片引用均不影响解析。
    - 相对链接：md 移动后目录加深一级，非 http 相对链接需补一级 "../" 以保持原解析目标。
    - README：根 README 链接为仓库相对路径，需同步改写到新路径。

幂等：目录已存在且 md 已在其中时跳过；图片引用已存在时不重复插入。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from pathlib import Path

DISHES = Path(__file__).resolve().parents[2] / "backend" / "data" / "HowToCook" / "dishes"
README = Path(__file__).resolve().parents[2] / "backend" / "data" / "HowToCook" / "README.md"
MANIFEST = Path(tempfile.gettempdir()) / "htc_manifest.json"

# 需要补 "../" 的链接前缀黑名单（外链/锚点不处理）
SKIP_PREFIX = ("http://", "https://", "#", "mailto:")

LINK_RE = re.compile(r"\]\(([^)]+)\)")
H1_RE = re.compile(r"^#\s+\S")


def adjust_links(text: str, dish: str) -> tuple[str, int]:
    """为移动后的 md 补一级相对路径。

    参数：
        text：md 全文。
        dish：菜名（新插入的图片引用需排除，避免被误改）。

    返回值：
        (新文本, 调整条数)。
    """
    changed = 0

    def _sub(match: re.Match[str]) -> str:
        nonlocal changed
        raw = match.group(1)
        url = raw.strip()
        if url.startswith(SKIP_PREFIX):
            return match.group(0)
        # 图片引用（本脚本新插入的同目录兄弟文件）不调整
        if url == f"./{dish}.jpg":
            return match.group(0)
        changed += 1
        fixed = f"../{url}".replace(".././", "../")
        return match.group(0).replace(raw, fixed, 1)

    return LINK_RE.sub(_sub, text), changed


def insert_image_ref(text: str, dish: str) -> tuple[str, bool]:
    """在 H1 标题后插入预览图引用（对齐上游主流约定：第 3 行）。

    参数：
        text：md 全文（CRLF 保留）。
        dish：菜名。

    返回值：
        (新文本, 是否插入)。
    """
    if f"./{dish}.jpg" in text:
        return text, False
    lines = text.split("\r\n") if "\r\n" in text else text.split("\n")
    nl = "\r\n" if "\r\n" in text else "\n"
    for i, line in enumerate(lines):
        if H1_RE.match(line):
            ins = i + 2 if i + 1 < len(lines) and not lines[i + 1].strip() else i + 1
            ref = [f"![{dish}-预览图-1](./{dish}.jpg)", ""]
            lines[ins:ins] = ref
            return nl.join(lines), True
    return text, False


def main() -> None:
    """执行迁移并输出统计（支持 --dry-run / --limit）。"""
    parser = argparse.ArgumentParser(description="为缺图菜品建立同名子目录结构")
    parser.add_argument("--dry-run", action="store_true", help="只打印不落盘")
    parser.add_argument("--limit", type=int, default=0, help="仅处理前 N 条（0=全部）")
    parser.add_argument("--verbose", action="store_true", help="逐条打印目标路径")
    args = parser.parse_args()

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if args.limit:
        manifest = manifest[: args.limit]
    moved = inplace = skipped = link_fixed = ref_added = 0
    readme_text = README.read_text(encoding="utf-8")
    readme_hits = 0

    for item in manifest:
        cat, dish = item["cat"], item["dish"]
        src = DISHES / cat / f"{dish}.md"
        folder = DISHES / cat / dish
        dst = folder / f"{dish}.md"

        # 情形 A：md 位于分类顶层 → 建目录、移入、修链接、插引用
        if src.exists():
            text = src.read_text(encoding="utf-8")
            text, n_fix = adjust_links(text, dish)
            text, added = insert_image_ref(text, dish)
            if not args.dry_run:
                folder.mkdir(parents=True, exist_ok=True)
                dst.write_text(text, encoding="utf-8", newline="")
                src.unlink()
            if args.dry_run:
                print(f"[DRY][MOVE] {cat}/{src.name} -> {cat}/{dish}/{dish}.md "
                      f"(链接修正 {n_fix}, 插入引用 {added})")
            moved += 1
            link_fixed += n_fix
            ref_added += 1 if added else 0

            old_link = f"(dishes/{cat}/{dish}.md)"
            new_link = f"(dishes/{cat}/{dish}/{dish}.md)"
            if old_link in readme_text:
                readme_text = readme_text.replace(old_link, new_link)
                readme_hits += 1
            continue

        # 情形 B：md 已在同名子目录内（仅缺图）→ 就地插引用，不动目录
        if dst.exists():
            text = dst.read_text(encoding="utf-8")
            text, added = insert_image_ref(text, dish)
            if added and not args.dry_run:
                dst.write_text(text, encoding="utf-8", newline="")
            if args.dry_run:
                print(f"[DRY][INPLACE] {cat}/{dish}/{dish}.md (插入引用 {added})")
            inplace += 1
            ref_added += 1 if added else 0
            continue

        skipped += 1
        print(f"[WARN] 源 md 与目标 md 均不存在：{cat}/{dish}")

    if not args.dry_run:
        README.write_text(readme_text, encoding="utf-8", newline="")
    print(f"{'[DRY-RUN] ' if args.dry_run else ''}迁移完成：移入子目录 {moved}，"
          f"就地插引用 {inplace}，异常 {skipped}，链接修正 {link_fixed} 处，"
          f"插入图片引用 {ref_added}，README 链接改写 {readme_hits}")


if __name__ == "__main__":
    main()
