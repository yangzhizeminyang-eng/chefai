"""上传文件目录管理模块。

职责：
    提供 uploads 目录的惰性清理能力（spec 模块 D）：识别图片按
    backend/uploads/{yyyymmdd}/{uuid}.jpg 落盘留档，仅作演示排查用途，
    每次识别调用时顺手清理超过 24h 的过期文件，避免磁盘无限增长。

设计约定：
    - 清理失败一律吞掉异常仅打日志（清理属旁路操作，绝不影响识别主链路）；
    - 只删过期文件，不递归删除非空目录；清空后的空日期子目录顺带移除
      （base 目录本身永不删除）。
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from app.core.logging import get_logger

logger = get_logger(__name__)


def cleanup_uploads(base_dir: str | Path, max_age_hours: float = 24) -> int:
    """清理上传目录中超过 max_age_hours 的过期文件（函数）。

    说明：
        os.walk 遍历 base_dir 下全部文件，按 mtime 判定过期并删除；
        随后自底向上移除清空后的空子目录（base 目录本身保留）。
        任何异常吞掉打日志（旁路操作不影响主链路）。

    参数：
        base_dir：上传根目录（如 backend/uploads）。
        max_age_hours：过期阈值小时数，默认 24。

    返回值：
        int：本次删除的文件数量（异常中断时返回已删数量）。

    异常：
        不抛出（目录不存在 / 权限不足等一律吞掉打日志）。
    """
    removed = 0
    base = Path(base_dir)
    if not base.exists():
        return 0
    cutoff = time.time() - max_age_hours * 3600
    try:
        # ① 删除过期文件
        for root, _dirs, files in os.walk(base):
            for fname in files:
                path = os.path.join(root, fname)
                try:
                    if os.path.getmtime(path) < cutoff:
                        os.remove(path)
                        removed += 1
                except OSError as exc:
                    logger.warning("cleanup_uploads skip file %s: %s", path, exc)
        # ② 自底向上移除空子目录（base 目录本身永不删除）
        for root, dirs, _files in os.walk(base, topdown=False):
            for dname in dirs:
                dir_path = os.path.join(root, dname)
                try:
                    os.rmdir(dir_path)  # 仅空目录可移除，非空抛 OSError 直接忽略
                except OSError:
                    pass
    except Exception as exc:  # noqa: BLE001 —— 清理为旁路操作，失败不影响主链路
        logger.warning("cleanup_uploads failed (base=%s): %s", base, exc)
    if removed:
        logger.info("cleanup_uploads removed %s expired files (base=%s)", removed, base)
    return removed
