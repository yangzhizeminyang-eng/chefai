"""Resolve stable recipe-cover URLs for records with missing database metadata."""

from __future__ import annotations

import hashlib
from pathlib import Path

COVERS_DIR = Path(__file__).resolve().parents[2] / "assets" / "recipe_covers"
COVER_URL_PREFIX = "/v1/media/recipe-covers"
COVER_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


def resolve_recipe_cover_url(
    title: str | None,
    stored_url: str | None = None,
    *,
    covers_dir: Path = COVERS_DIR,
) -> str | None:
    """Use the stored URL, or recover the deterministic seed asset when present."""
    if stored_url:
        return stored_url
    normalized_title = (title or "").strip()
    if not normalized_title:
        return None

    digest = hashlib.md5(normalized_title.encode("utf-8")).hexdigest()[:12]
    for extension in COVER_EXTENSIONS:
        if (covers_dir / f"{digest}{extension}").is_file():
            return f"{COVER_URL_PREFIX}/{digest}{extension}"
    return None
