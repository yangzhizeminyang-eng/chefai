from __future__ import annotations

from app.core.recipe_covers import resolve_recipe_cover_url


def test_resolves_seeded_cover_when_database_url_is_missing(tmp_path) -> None:
    (tmp_path / "a4c72f21f718.jpg").write_bytes(b"cover")

    assert resolve_recipe_cover_url("蚝油生菜", covers_dir=tmp_path) == (
        "/v1/media/recipe-covers/a4c72f21f718.jpg"
    )


def test_database_cover_url_takes_precedence(tmp_path) -> None:
    assert resolve_recipe_cover_url(
        "蚝油生菜",
        "/v1/media/recipe-covers/custom.webp",
        covers_dir=tmp_path,
    ) == "/v1/media/recipe-covers/custom.webp"


def test_missing_title_or_asset_returns_no_cover(tmp_path) -> None:
    assert resolve_recipe_cover_url("", covers_dir=tmp_path) is None
    assert resolve_recipe_cover_url("不存在的菜", covers_dir=tmp_path) is None
