"""后端菜品图片链路测试（spec: add-home-entries-and-covers）。

覆盖：
    - find_dish_image 图片定位优先级：同名精确 → 成品.jpg → 文件名排序第一张
      → 无图 None（含目录不存在 / 仅 .md）；
    - copy_cover 文件名生成：md5(title)[:12] + 原扩展名小写；目标已存在跳过
      复制（幂等）；无图返回 None；
    - 媒体服务：GET /v1/media/recipe-covers/{已存在文件} 200、不存在 404；
    - schema：RecommendResultItem 支持 cover_image_url 字段（缺省 None）；
    - 详情端点：cover_image_url / cover_image_source 两键存在且逻辑一致；
    - 存量回填幂等：import_corpus 对 cover_image_url 为空的存量菜谱补 UPDATE
      （fake session 断言），已填过 / 语料无图时不产生 UPDATE。
"""

from __future__ import annotations

import hashlib
import uuid

from fastapi.testclient import TestClient

import app.seed.corpus_howtocook as cch
from app.models import Ingredient, IngredientAlias, Recipe
from app.schemas.recommend import RecommendResultItem


def _md5_12(title: str) -> str:
    """计算封面文件名哈希（函数）。

    说明：
        与 copy_cover 同口径：md5(title utf-8) 前 12 位。

    参数：
        title：菜名。

    返回值：
        str：12 位十六进制哈希。

    异常：
        无。
    """
    return hashlib.md5(title.encode("utf-8")).hexdigest()[:12]


# ==================== 图片定位优先级 ====================


def test_find_dish_image_priority_exact_name(tmp_path) -> None:
    """同名图优先于 成品.jpg 与数字图（函数）。

    参数：
        tmp_path：pytest 临时目录。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    dish_dir = tmp_path / "dish"
    dish_dir.mkdir()
    (dish_dir / "000.jpg").write_bytes(b"a")
    (dish_dir / "成品.jpg").write_bytes(b"b")
    (dish_dir / "宫保鸡丁.png").write_bytes(b"c")
    hit = cch.find_dish_image(dish_dir, "宫保鸡丁")
    assert hit is not None and hit.name == "宫保鸡丁.png"


def test_find_dish_image_priority_chengpin(tmp_path) -> None:
    """无同名图时 成品.jpg 优先于数字图（函数）。

    参数：
        tmp_path：pytest 临时目录。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    dish_dir = tmp_path / "dish"
    dish_dir.mkdir()
    (dish_dir / "000.jpg").write_bytes(b"a")
    (dish_dir / "成品.jpg").write_bytes(b"b")
    hit = cch.find_dish_image(dish_dir, "宫保鸡丁")
    assert hit is not None and hit.name == "成品.jpg"


def test_find_dish_image_priority_first_sorted(tmp_path) -> None:
    """仅散图时取文件名排序第一张（函数）。

    参数：
        tmp_path：pytest 临时目录。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    dish_dir = tmp_path / "dish"
    dish_dir.mkdir()
    (dish_dir / "1.jpeg").write_bytes(b"a")
    (dish_dir / "000.jpg").write_bytes(b"b")
    (dish_dir / "abc.webp").write_bytes(b"c")
    (dish_dir / "宫保鸡丁.md").write_text("# x", encoding="utf-8")  # md 不参与
    hit = cch.find_dish_image(dish_dir, "宫保鸡丁")
    assert hit is not None and hit.name == "000.jpg"


def test_find_dish_image_none_cases(tmp_path) -> None:
    """目录不存在 / 空目录 / 仅 md / 大写扩展名兼容（函数）。

    参数：
        tmp_path：pytest 临时目录。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    assert cch.find_dish_image(tmp_path / "no_such_dir", "宫保鸡丁") is None
    empty = tmp_path / "empty"
    empty.mkdir()
    assert cch.find_dish_image(empty, "宫保鸡丁") is None
    md_only = tmp_path / "md_only"
    md_only.mkdir()
    (md_only / "宫保鸡丁.md").write_text("# x", encoding="utf-8")
    assert cch.find_dish_image(md_only, "宫保鸡丁") is None
    upper = tmp_path / "upper"
    upper.mkdir()
    (upper / "回锅肉.JPG").write_bytes(b"a")  # 大写扩展名仍可命中
    hit = cch.find_dish_image(upper, "回锅肉")
    assert hit is not None and hit.name == "回锅肉.JPG"


# ==================== copy_cover 文件名与幂等 ====================


def test_copy_cover_filename_hash_and_ext(tmp_path, monkeypatch) -> None:
    """文件名 = md5(title)[:12] + 原扩展名小写；URL 前缀正确（函数）。

    参数：
        tmp_path：pytest 临时目录。
        monkeypatch：pytest 夹具。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    covers = tmp_path / "covers"
    monkeypatch.setattr(cch, "COVERS_DIR", covers)
    dish_dir = tmp_path / "dish"
    dish_dir.mkdir()
    (dish_dir / "宫保鸡丁.PNG").write_bytes(b"img")  # 大写扩展名 → 落盘小写
    url = cch.copy_cover(dish_dir, "宫保鸡丁")
    digest = _md5_12("宫保鸡丁")
    assert url == f"/v1/media/recipe-covers/{digest}.png"
    assert (covers / f"{digest}.png").read_bytes() == b"img"


def test_copy_cover_idempotent_existing_target(tmp_path, monkeypatch) -> None:
    """目标文件已存在时跳过复制，不被覆盖（幂等）（函数）。

    参数：
        tmp_path：pytest 临时目录。
        monkeypatch：pytest 夹具。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    covers = tmp_path / "covers"
    monkeypatch.setattr(cch, "COVERS_DIR", covers)
    dish_dir = tmp_path / "dish"
    dish_dir.mkdir()
    (dish_dir / "红烧肉.jpg").write_bytes(b"NEW")
    digest = _md5_12("红烧肉")
    target = covers / f"{digest}.jpg"
    assert cch.copy_cover(dish_dir, "红烧肉") == f"/v1/media/recipe-covers/{digest}.jpg"
    target.write_bytes(b"OLD")  # 模拟目标已存在（内容不同）
    url_second = cch.copy_cover(dish_dir, "红烧肉")
    assert url_second == f"/v1/media/recipe-covers/{digest}.jpg"
    assert target.read_bytes() == b"OLD", "已存在目标不应被覆盖"


def test_copy_cover_no_image_returns_none(tmp_path, monkeypatch) -> None:
    """无图返回 None 且不建目录（函数）。

    参数：
        tmp_path：pytest 临时目录。
        monkeypatch：pytest 夹具。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    covers = tmp_path / "covers"
    monkeypatch.setattr(cch, "COVERS_DIR", covers)
    dish_dir = tmp_path / "dish"
    dish_dir.mkdir()
    (dish_dir / "凉拌菜.md").write_text("# 凉拌菜", encoding="utf-8")
    assert cch.copy_cover(dish_dir, "凉拌菜") is None
    assert not covers.exists(), "无图时不应创建封面目录"


# ==================== 媒体服务 ====================


def test_media_serving_ok_and_404(client: TestClient) -> None:
    """已存在文件 200、不存在文件 404（函数）。

    说明：
        向真实封面资产目录写入唯一命名临时文件，测试结束后清理。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    fname = f"test_{uuid.uuid4().hex[:10]}.jpg"
    target = cch.COVERS_DIR / fname
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"\xff\xd8fake")
    try:
        resp = client.get(f"/v1/media/recipe-covers/{fname}")
        assert resp.status_code == 200
        assert resp.content == b"\xff\xd8fake"
    finally:
        target.unlink(missing_ok=True)
    missing = client.get(f"/v1/media/recipe-covers/missing_{uuid.uuid4().hex[:10]}.jpg")
    assert missing.status_code == 404


# ==================== Schema 与详情端点 ====================


def test_recommend_result_item_cover_field() -> None:
    """RecommendResultItem 支持 cover_image_url 且缺省 None（函数）。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    item = RecommendResultItem(
        recipe_id=1, title="宫保鸡丁", match_level="can_cook_now",
        cover_image_url="/v1/media/recipe-covers/abc123.jpg",
    )
    assert item.cover_image_url == "/v1/media/recipe-covers/abc123.jpg"
    bare = RecommendResultItem(recipe_id=2, title="凉拌菜", match_level="need_more")
    assert bare.cover_image_url is None


def test_recipe_detail_cover_keys(client: TestClient) -> None:
    """详情响应含 cover_image_url / cover_image_source 且逻辑一致（函数）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败（需先执行 python -m app.seed）。
    """
    resp = client.get("/v1/recipes", params={"page_size": 5})
    assert resp.status_code == 200
    ids = [item["id"] for item in resp.json()["items"]]
    assert ids, "库内无菜谱（环境前置条件）"
    data = client.get(f"/v1/recipes/{ids[0]}").json()
    assert "cover_image_url" in data
    assert "cover_image_source" in data
    if data["cover_image_url"]:
        assert data["cover_image_source"] == "HowToCook 语料配图（Unlicense 公有领域）"
    else:
        assert data["cover_image_source"] is None


# ==================== 存量回填幂等 ====================


class _FakeReadQuery:
    """只读查询桩（辅助类）。

    属性：
        _rows：query(...).all() 返回的行列表。

    异常：
        无。
    """

    def __init__(self, rows: list) -> None:
        self._rows = rows

    def all(self) -> list:
        """返回预置行。

        返回值：
            list：预置行列表。

        异常：
            无。
        """
        return self._rows


class _FakeUpdateQuery:
    """UPDATE 查询桩（辅助类），记录 update 调用。

    属性：
        _sink：外层收集器列表。

    异常：
        无。
    """

    def __init__(self, sink: list) -> None:
        self._sink = sink

    def filter(self, *args, **kwargs) -> _FakeUpdateQuery:
        """透传 filter（不校验条件）。

        参数：
            args/kwargs：filter 条件（忽略）。

        返回值：
            _FakeUpdateQuery：自身。

        异常：
            无。
        """
        return self

    def update(self, values: dict, synchronize_session: str | None = None) -> int:
        """记录一次 UPDATE 调用。

        参数：
            values：待更新字段字典。
            synchronize_session：同步策略（忽略）。

        返回值：
            int：固定 1（模拟命中一行）。

        异常：
            无。
        """
        self._sink.append(dict(values))
        return 1


class _FakeSession:
    """import_corpus 最小会话桩（辅助类）。

    说明：
        仅支撑存量回填分支所需查询：Ingredient/IngredientAlias（空表）、
        (Recipe.title, Recipe.cover_image_url) 组合查询、query(Recipe).update()。

    属性：
        cover_rows：存量 (title, cover_image_url) 行。
        updates：捕获的 UPDATE 字典列表。

    异常：
        收到意外查询时抛 AssertionError。
    """

    def __init__(self, cover_rows: list) -> None:
        self.cover_rows = cover_rows
        self.updates: list[dict] = []

    def query(self, *models) -> object:
        """按查询首元素分发桩行为。

        参数：
            models：query 传入的模型/列元组。

        返回值：
            object：对应查询桩。

        异常：
            意外查询抛 AssertionError。
        """
        first = models[0]
        if first is Ingredient:
            return _FakeReadQuery([])
        if first is IngredientAlias:
            return _FakeReadQuery([])
        if first is Recipe.title:  # (title, cover_image_url) 组合查询
            return _FakeReadQuery(self.cover_rows)
        if first is Recipe:
            return _FakeUpdateQuery(self.updates)
        raise AssertionError(f"意外查询: {models}")


_MIN_MD = "# 回填菜的做法\n\n## 必备原料和工具\n\n- 土豆\n\n## 计算\n\n- 土豆 200g\n\n## 操作\n\n1. 切丝\n"


def _make_corpus_tree(tmp_path, title: str = "回填菜", with_image: bool = True) -> None:
    """构造最小语料目录树（辅助函数）。

    说明：
        tmp_path/dishes/{分类}/{菜}/{菜}.md（可解析最小结构）+ 可选同名图。

    参数：
        tmp_path：pytest 临时目录。
        title：菜名（目录与 md 标题同名）。
        with_image：是否放置同名 .jpg。

    返回值：
        None。

    异常：
        无。
    """
    dish_dir = tmp_path / "dishes" / "测试分类" / title
    dish_dir.mkdir(parents=True)
    (dish_dir / f"{title}.md").write_text(_MIN_MD, encoding="utf-8")
    if with_image:
        (dish_dir / f"{title}.jpg").write_bytes(b"img")


def _patch_corpus(tmp_path, monkeypatch) -> None:
    """语料导入隔离补丁（辅助函数）。

    说明：
        ensure_corpus 恒真、DISHES_DIR/COVERS_DIR 指向 tmp_path，杜绝测试
        触网与污染真实资产目录。

    参数：
        tmp_path：pytest 临时目录。
        monkeypatch：pytest 夹具。

    返回值：
        None。

    异常：
        无。
    """
    monkeypatch.setattr(cch, "ensure_corpus", lambda: True)
    monkeypatch.setattr(cch, "DISHES_DIR", tmp_path / "dishes")
    monkeypatch.setattr(cch, "COVERS_DIR", tmp_path / "covers")


def test_import_corpus_backfills_missing_cover(tmp_path, monkeypatch) -> None:
    """存量封面为空且语料有图 → 复制文件并 UPDATE 一次（函数）。

    说明：
        同目录第二个同菜名 md 再命中回填分支时，因本批已回填不再重复 UPDATE
        （幂等断言）。

    参数：
        tmp_path：pytest 临时目录。
        monkeypatch：pytest 夹具。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    _make_corpus_tree(tmp_path)
    # 第二个同菜名 md（不同目录），验证批内幂等：只 UPDATE 一次
    dup_dir = tmp_path / "dishes" / "另一分类" / "回填菜"
    dup_dir.mkdir(parents=True)
    (dup_dir / "回填菜.md").write_text(_MIN_MD, encoding="utf-8")
    _patch_corpus(tmp_path, monkeypatch)
    session = _FakeSession(cover_rows=[("回填菜", None)])
    stats = cch.import_corpus(session)  # type: ignore[arg-type]
    digest = _md5_12("回填菜")
    expected_url = f"/v1/media/recipe-covers/{digest}.jpg"
    assert stats["cover_backfilled"] == 1
    assert session.updates == [{Recipe.cover_image_url: expected_url}]
    assert (tmp_path / "covers" / f"{digest}.jpg").read_bytes() == b"img"


def test_import_corpus_backfill_skips_filled_and_imageless(tmp_path, monkeypatch) -> None:
    """已填封面 / 语料无图 → 零 UPDATE（函数）。

    参数：
        tmp_path：pytest 临时目录。
        monkeypatch：pytest 夹具。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    digest = _md5_12("回填菜")
    # 语料有图但存量已填过 → 不动
    _make_corpus_tree(tmp_path, with_image=True)
    _patch_corpus(tmp_path, monkeypatch)
    filled = _FakeSession(cover_rows=[("回填菜", f"/v1/media/recipe-covers/{digest}.jpg")])
    stats_filled = cch.import_corpus(filled)  # type: ignore[arg-type]
    assert stats_filled["cover_backfilled"] == 0
    assert filled.updates == []
    # 存量封面为空但语料无图 → 无法回填，零 UPDATE
    tree2 = tmp_path / "tree2"
    tree2.mkdir()
    _make_corpus_tree(tree2, with_image=False)
    monkeypatch.setattr(cch, "DISHES_DIR", tree2 / "dishes")
    imageless = _FakeSession(cover_rows=[("回填菜", None)])
    stats_imageless = cch.import_corpus(imageless)  # type: ignore[arg-type]
    assert stats_imageless["cover_backfilled"] == 0
    assert imageless.updates == []
