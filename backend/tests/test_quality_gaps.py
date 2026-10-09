"""质量门槛补强测试（Task 6.2，覆盖率 ≥80%）。

针对既有 50 条测试未覆盖的分支补测，达成 05-V1.1 §3.4 质量门槛
（app/safety 全模块与 app/ability/ranking.py 行覆盖率 ≥80%）：
    - app/safety/logger.py：sanitize_digest 空输入/异常兜底、write_risk_log 失败回滚；
    - app/safety/sensitive_words.py：sanitize 空输入/命中替换/正则异常兜底；
    - app/safety/engine.py：指纹查询失败、非法规则不命中、scan 异常 → UNKNOWN、话术兜底；
    - app/core/migrations.py：ensure_schema 三分支决策（upgrade/stamp）与失败上抛（mock，不碰真库）；
    - app/ability/ranking.py：hard_filter 忌口/难度/异常降级、load_weights 冷启动与回退、
      weighted_rank 冷启动权重摊派/理由分支/单条异常跳过/三档 tier 边界。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import app.core.migrations as migrations_mod
import app.safety.engine as engine_mod
import app.safety.logger as logger_mod
import app.safety.sensitive_words as sensitive_words_mod
from app.ability.ranking import DEFAULT_WEIGHTS, hard_filter, load_weights, weighted_rank
from app.ability.retrieval import retrieve_candidates
from app.core.db import SessionLocal
from app.core.migrations import ensure_schema
from app.safety.engine import RiskEngine
from app.safety.logger import sanitize_digest, write_risk_log
from app.safety.sensitive_words import sanitize
from app.safety.types import SafetyProfile
from tests.conftest import unique_request_id


# ----------------------------------------------------------------------
# 通用测试替身
# ----------------------------------------------------------------------
class _ExplodingPattern:
    """findall/sub 时抛异常的假正则（类）。

    说明：
        用于模拟正则引擎异常，验证各兜底分支「不向调用方抛出」的契约。

    异常：
        sub / findall 恒抛 RuntimeError。
    """

    @staticmethod
    def sub(_repl: str, _text: str) -> str:
        """替换接口（函数）。

        异常：
            恒抛 RuntimeError("regex boom")。
        """
        raise RuntimeError("regex boom")

    @staticmethod
    def findall(_text: str) -> list[str]:
        """查找接口（函数）。

        异常：
            恒抛 RuntimeError("regex boom")。
        """
        raise RuntimeError("regex boom")


class _BoomSession:
    """execute 即抛异常的假会话（类）。

    说明：
        模拟数据库层故障，验证 load_weights / hard_filter 的降级分支。

    异常：
        execute 恒抛 RuntimeError。
    """

    def execute(self, *_args, **_kwargs):
        """执行 SQL（函数）。

        异常：
            恒抛 RuntimeError("db down")。
        """
        raise RuntimeError("db down")


def _boom_session_factory(*_args, **_kwargs):
    """返回即抛异常的会话工厂（函数）。

    说明：
        替换 engine_mod.SessionLocal 后，任何 `with SessionLocal()` 都会失败，
        用于触发风控引擎的 UNKNOWN 兜底与指纹查询失败分支。

    异常：
        调用即抛 RuntimeError。
    """
    raise RuntimeError("db unreachable")


def _make_candidate(**overrides) -> dict:
    """构造排序函数输入的最小候选字典（函数）。

    参数：
        **overrides：覆盖默认字段的键值对。

    返回值：
        dict：含 weighted_rank / hard_filter 所需全部字段的候选字典。
    """
    base = {
        "recipe_id": 1,
        "title": "番茄炒蛋",
        "difficulty": 2,
        "time_minutes": 15,
        "calories_kcal": 200.0,
        "allergen_codes": [],
        "ingredient_allergen_codes": [],
        "dietary_flags": [],
        "equipment": [],
        "covered_count": 2,
        "covered_names": ["番茄", "鸡蛋"],
        "main_ingredient_names": ["番茄", "鸡蛋"],
        "seasoning_names": [],
        "matched_by_title": False,
    }
    base.update(overrides)
    return base


def _load_all_candidates() -> list[dict]:
    """加载全量已发布菜谱候选（函数）。

    说明：
        空食材 + 空文本 → 冷启动全量召回（retrieve_candidates 保证）。

    返回值：
        list[dict]：候选菜谱字典列表。

    异常：
        数据库异常向上抛出（环境前置条件）。
    """
    with SessionLocal() as session:
        return retrieve_candidates(session, [], query_text=None, limit=200)


# ----------------------------------------------------------------------
# app/safety/logger.py
# ----------------------------------------------------------------------
class TestSanitizeDigest:
    """脱敏摘要 sanitize_digest 的边界与异常分支（类）。"""

    def test_empty_and_none_return_empty(self) -> None:
        """空串与 None 均返回空串（函数）。

        说明：
            覆盖 `if not text` 分支：脱敏对空输入直接短路。

        异常：
            不应抛出（None 输入按设计返回空串）。
        """
        assert sanitize_digest("") == ""
        assert sanitize_digest(None) == ""

    def test_masks_phone_id_and_truncates(self) -> None:
        """手机号/身份证脱敏且摘要截断到 60 字符（函数）。

        说明：
            脱敏在先、截断在后：尾部身份证号被掩码后仍不超长。

        异常：
            断言失败即测试失败。
        """
        long_text = "联系 13800138000 领取，身份证 11010119900307777X，" + "补" * 80
        digest = sanitize_digest(long_text)
        assert "13800138000" not in digest
        assert "11010119900307777X" not in digest
        assert len(digest) <= 60

    def test_regex_error_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """脱敏正则异常时返回 [digest_error]（函数）。

        说明：
            覆盖 sanitize_digest 的 except 分支：脱敏失败绝不落原文。

        参数：
            monkeypatch：替换模块级 _PHONE_RE 为异常正则。

        异常：
            断言失败即测试失败。
        """
        monkeypatch.setattr(logger_mod, "_PHONE_RE", _ExplodingPattern)
        assert sanitize_digest("正常文本13800138000") == "[digest_error]"


class TestWriteRiskLog:
    """风控日志落库失败分支（类）。"""

    def test_commit_failure_returns_false_and_rolls_back(self) -> None:
        """commit 失败 → 回滚并返回 False（函数）。

        说明：
            覆盖 except 主分支：留痕失败绝不阻断主链路。

        异常：
            断言失败即测试失败。
        """
        session = MagicMock()
        session.commit.side_effect = RuntimeError("db down")
        ok = write_risk_log(
            session,
            unique_request_id(),
            "input",
            {"rule_code": "FS-001", "category": "food_safety_high_risk", "risk_level": "critical", "message_id": "MSG-FS-001"},
            "用户输入文本",
            "blocked",
        )
        assert ok is False
        session.rollback.assert_called_once()

    def test_rollback_failure_still_returns_false(self) -> None:
        """回滚本身也失败时仍返回 False（函数）。

        说明：
            覆盖内层 rollback except 分支：双重故障不向调用方抛出。

        异常：
            断言失败即测试失败。
        """
        session = MagicMock()
        session.commit.side_effect = RuntimeError("db down")
        session.rollback.side_effect = RuntimeError("rollback down")
        assert write_risk_log(session, unique_request_id(), "output", {}, "文本", "passed") is False


# ----------------------------------------------------------------------
# app/safety/sensitive_words.py
# ----------------------------------------------------------------------
class TestSensitiveWordsSanitize:
    """出口敏感词 sanitize 的分支（类）。"""

    def test_empty_input(self) -> None:
        """空文本返回 ("", [])（函数）。

        异常：
            断言失败即测试失败。
        """
        assert sanitize("") == ("", [])

    def test_hits_rewrite_and_record(self) -> None:
        """多类禁令命中：文本改写且逐类记录（函数）。

        说明：
            覆盖命中分支（violations.append + pattern.sub）；
            「最好的」「减肥」「绝对安全」分别命中绝对化/功效/安全承诺。

        异常：
            断言失败即测试失败。
        """
        clean, violations = sanitize("这是最好的减肥食谱，吃了绝对安全")
        assert clean and "最好的" not in clean and "减肥" not in clean and "绝对安全" not in clean
        categories = {v["category"] for v in violations}
        assert {"absolute", "effect_claim", "safety_promise"} <= categories

    def test_regex_error_returns_original(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """正则异常时返回原文（函数）。

        说明：
            覆盖 sanitize 的 except 分支：兜底过滤失败不阻断出口。

        参数：
            monkeypatch：替换 _BAN_RULES 为含异常正则的单条规则表。

        异常：
            断言失败即测试失败。
        """
        monkeypatch.setattr(
            sensitive_words_mod, "_BAN_RULES", [("absolute", _ExplodingPattern, "替换")]
        )
        original = "这是最好的食谱"
        assert sanitize(original) == (original, [])


# ----------------------------------------------------------------------
# app/safety/engine.py
# ----------------------------------------------------------------------
class TestRiskEngineResilience:
    """风控引擎异常兜底与话术查询分支（类）。"""

    def test_scan_db_failure_returns_unknown(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """规则库不可达 → UNKNOWN（保守模式）（函数）。

        说明：
            覆盖 _compute_fingerprint 异常（指纹返回 None）与 scan 全捕获
            转 UNKNOWN 两个分支；UNKNOWN 绝不放行、绝不误报。

        参数：
            monkeypatch：替换模块级 SessionLocal 为抛异常工厂。

        异常：
            断言失败即测试失败。
        """
        monkeypatch.setattr(engine_mod, "SessionLocal", _boom_session_factory)
        verdict = RiskEngine().scan("input", "番茄炒蛋怎么做", SafetyProfile())
        assert verdict.status == "UNKNOWN"
        assert verdict.hit is False

    def test_match_rule_invalid_groups_not_hit(self) -> None:
        """非法 trigger_condition（groups 不可迭代）按不命中处理（函数）。

        说明：
            覆盖 _match_rule 的 except 分支：坏规则不影响整体扫描。

        异常：
            断言失败即测试失败。
        """
        bad_rule = {"trigger_condition": {"keywords": ["蛋"], "mode": "all_groups", "groups": 123}}
        assert RiskEngine._match_rule(bad_rule, "蛋炒饭", "蛋炒饭") is False

    def test_get_message_none_and_builtin(self) -> None:
        """话术查询：空 ID 返回 None，内置注入话术直取内存（函数）。

        异常：
            断言失败即测试失败。
        """
        engine = RiskEngine()
        assert engine.get_message(None) is None
        builtin = engine.get_message(engine_mod._INJECTION_MESSAGE["message_id"])
        assert builtin is not None
        assert builtin["message_id"] == engine_mod._INJECTION_MESSAGE["message_id"]

    def test_get_message_db_failure_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """话术库查询失败返回 None（函数）。

        说明：
            覆盖 get_message 的 except 分支：话术缺失由调用方兜底默认文案。

        参数：
            monkeypatch：替换模块级 SessionLocal 为抛异常工厂。

        异常：
            断言失败即测试失败。
        """
        monkeypatch.setattr(engine_mod, "SessionLocal", _boom_session_factory)
        assert RiskEngine().get_message("MSG-FS-001") is None


# ----------------------------------------------------------------------
# app/core/migrations.py（mock，不碰真库）
# ----------------------------------------------------------------------
class _FakeInspector:
    """按场景返回表存在性的假 inspector（类）。

    参数：
        has_version：alembic_version 表是否存在。
        has_business：业务表（user/recipe）是否存在。
    """

    def __init__(self, has_version: bool, has_business: bool) -> None:
        """初始化假 inspector（函数）。

        参数：
            has_version：alembic_version 表存在性。
            has_business：业务表存在性。
        """
        self._has_version = has_version
        self._has_business = has_business

    def has_table(self, name: str) -> bool:
        """判断表是否存在（函数）。

        参数：
            name：表名。

        返回值：
            bool：alembic_version 按 _has_version，其余按 _has_business。
        """
        if name == "alembic_version":
            return self._has_version
        return self._has_business


class _FakeEngine:
    """可 dispose 的假引擎（类）。"""

    def dispose(self) -> None:
        """释放连接（函数）。"""


def _patch_migrations(
    monkeypatch: pytest.MonkeyPatch,
    has_version: bool,
    has_business: bool,
    fail: bool = False,
) -> list[tuple[str, str]]:
    """打桩 ensure_schema 的全部外部依赖（函数）。

    参数：
        monkeypatch：pytest 打桩器。
        has_version：alembic_version 表存在性。
        has_business：业务表存在性。
        fail：True 时 alembic command 执行抛异常。

    返回值：
        list[tuple[str, str]]：记录的 command 调用 [(动作, revision), ...]。

    异常：
        fail=True 时 upgrade 调用抛 RuntimeError（供 re-raise 断言）。
    """
    calls: list[tuple[str, str]] = []

    def _upgrade(_cfg, revision: str) -> None:
        """模拟 alembic upgrade（函数）。"""
        calls.append(("upgrade", revision))
        if fail:
            raise RuntimeError("migration failed")

    def _stamp(_cfg, revision: str) -> None:
        """模拟 alembic stamp（函数）。"""
        calls.append(("stamp", revision))

    monkeypatch.setattr(migrations_mod, "_build_alembic_config", lambda: SimpleNamespace())
    monkeypatch.setattr(migrations_mod, "create_engine", lambda *_a, **_k: _FakeEngine())
    monkeypatch.setattr(
        migrations_mod, "inspect", lambda _engine: _FakeInspector(has_version, has_business)
    )
    monkeypatch.setattr(migrations_mod, "command", SimpleNamespace(upgrade=_upgrade, stamp=_stamp))
    return calls


class TestEnsureSchema:
    """ensure_schema 三分支决策与失败上抛（类）。"""

    def test_build_alembic_config_real(self) -> None:
        """真实构造 Alembic 配置：script_location 指向 backend/alembic（函数）。

        说明：
            纯文件操作不碰数据库：验证 ini 存在性假设与「跳过 fileConfig」语义。

        异常：
            断言失败即测试失败。
        """
        from pathlib import Path

        cfg = migrations_mod._build_alembic_config()
        assert Path(cfg.get_main_option("script_location")).is_dir()
        assert cfg.config_file_name is None

    def test_upgrade_when_already_versioned(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """已纳管库（alembic_version 存在）→ upgrade head（函数）。

        参数：
            monkeypatch：pytest 打桩器。

        异常：
            断言失败即测试失败。
        """
        calls = _patch_migrations(monkeypatch, has_version=True, has_business=True)
        assert ensure_schema() == "upgrade"
        assert calls == [("upgrade", "head")]

    def test_stamp_legacy_create_all_db(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """存量 create_all 库（无版本表、有业务表）→ stamp head（函数）。

        说明：
            兼容分支：只登记版本，不改动既有表与数据。

        参数：
            monkeypatch：pytest 打桩器。

        异常：
            断言失败即测试失败。
        """
        calls = _patch_migrations(monkeypatch, has_version=False, has_business=True)
        assert ensure_schema() == "stamp"
        assert calls == [("stamp", "head")]

    def test_upgrade_empty_db(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """空库（两枚举表均缺）→ upgrade head 全量建表（函数）。

        参数：
            monkeypatch：pytest 打桩器。

        异常：
            断言失败即测试失败。
        """
        calls = _patch_migrations(monkeypatch, has_version=False, has_business=False)
        assert ensure_schema() == "upgrade"
        assert calls == [("upgrade", "head")]

    def test_migration_failure_reraises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """迁移执行失败：中文记日志后原样上抛（函数）。

        参数：
            monkeypatch：pytest 打桩器。

        异常：
            断言 ensure_schema 将 RuntimeError 原样上抛。
        """
        _patch_migrations(monkeypatch, has_version=False, has_business=False, fail=True)
        with pytest.raises(RuntimeError, match="migration failed"):
            ensure_schema()


# ----------------------------------------------------------------------
# app/ability/ranking.py
# ----------------------------------------------------------------------
class TestHardFilterBranches:
    """hard_filter 忌口/难度分支与异常降级（类）。"""

    def test_dietary_and_difficulty_counts_and_filter(self) -> None:
        """忌口 + 难度上限：计数准确且过滤后集合合规（函数）。

        说明：
            覆盖 dietary/difficulty 计数与叠加过滤分支；
            种子保证含 vegetarian 标记与难度 >2 的菜谱均存在。

        异常：
            断言失败即测试失败（或种子数据缺失）。
        """
        candidates = _load_all_candidates()
        assert candidates, "种子菜谱为空，请先执行 python -m app.seed"
        profile = SafetyProfile(
            user_allergen_codes=["egg"],
            dietary_restrictions=["vegetarian"],
            difficulty_cap=2,
        )
        with SessionLocal() as session:
            filtered, counts = hard_filter(session, candidates, profile)

        expected_diet = sum(1 for c in candidates if "vegetarian" in (c.get("dietary_flags") or []))
        expected_diff = sum(1 for c in candidates if int(c.get("difficulty") or 0) > 2)
        assert counts["dietary_restriction"] == expected_diet
        assert counts["difficulty"] == expected_diff
        assert all(
            "vegetarian" not in (c.get("dietary_flags") or []) and int(c["difficulty"]) <= 2
            for c in filtered
        )

    def test_db_error_fallback_to_empty(self) -> None:
        """过滤查询失败 → 空集 + 宁少不错降级（函数）。

        说明：
            覆盖 hard_filter 的 except 分支：任何异常返回空结果集。

        异常：
            断言失败即测试失败。
        """
        candidates = _load_all_candidates()
        assert candidates, "种子菜谱为空，请先执行 python -m app.seed"
        filtered, counts = hard_filter(
            _BoomSession(), candidates, SafetyProfile(user_allergen_codes=["egg"])
        )
        assert filtered == []
        assert counts["allergen"] >= 0  # 计数保持初始值语义，不抛异常


class TestLoadWeights:
    """排序权重加载的冷启动与回退分支（类）。"""

    def test_self_managed_session(self) -> None:
        """session=None 时自建短会话读取权重（函数）。

        说明：
            覆盖 load_weights 的自建会话分支（真库读 rank.weights 或回退默认）。

        异常：
            断言失败即测试失败。
        """
        weights = load_weights(None)
        assert isinstance(weights, dict)
        assert set(weights) == set(DEFAULT_WEIGHTS)

    def test_db_error_fallback_to_defaults(self) -> None:
        """权重查询失败 → 回退默认权重（函数）。

        说明：
            覆盖 load_weights 的 except 分支：链路可降级。

        异常：
            断言失败即测试失败。
        """
        assert load_weights(_BoomSession()) == dict(DEFAULT_WEIGHTS)


class TestWeightedRankBranches:
    """weighted_rank 冷启动权重、理由与异常分支（类）。"""

    def test_cold_start_history_weight_redistribution(self) -> None:
        """冷启动：history 权重按既有比例摊派（函数）。

        说明：
            覆盖 denom>0 摊派与 denom==0 直接并入 coverage 两条分支；
            history 权重归零后排序仍正常产出。

        异常：
            断言失败即测试失败。
        """
        zero_denom = dict(DEFAULT_WEIGHTS, coverage=0.0, popularity=0.0, history=0.10)
        out = weighted_rank([_make_candidate(recipe_id=1)], SafetyProfile(), zero_denom)
        assert out
        nonzero_denom = dict(DEFAULT_WEIGHTS, coverage=0.3, popularity=0.1, history=0.10)
        out2 = weighted_rank([_make_candidate(recipe_id=2)], SafetyProfile(), nonzero_denom)
        assert out2

    def test_match_level_tier_boundaries(self) -> None:
        """三档匹配边界：missing=0/2/3 → can_cook_now/missing_1_2/need_more（函数）。

        异常：
            断言失败即测试失败。
        """
        c_now = _make_candidate(recipe_id=10)
        c_1_2 = _make_candidate(
            recipe_id=11, main_ingredient_names=["牛腩", "土豆"], covered_count=0, covered_names=[]
        )
        c_more = _make_candidate(
            recipe_id=12,
            main_ingredient_names=["牛腩", "土豆", "胡萝卜", "青椒"],
            covered_count=0,
            covered_names=[],
        )
        levels = {x["recipe_id"]: x["match_level"] for x in weighted_rank([c_now, c_1_2, c_more], SafetyProfile(), None)}
        assert levels == {10: "can_cook_now", 11: "missing_1_2", 12: "need_more"}

    def test_reasons_matched_by_title_and_fallback(self) -> None:
        """理由分支：菜名直连命中与无理由兜底文案（函数）。

        说明：
            覆盖 matched_by_title 理由与 reasons 为空时的兜底分支；
            兜底候选需同时满足：无覆盖、missing≥3、难度>2、耗时>20、无菜名命中。

        异常：
            断言失败即测试失败。
        """
        title_hit = _make_candidate(recipe_id=1, matched_by_title=True)
        fallback = _make_candidate(
            recipe_id=2,
            covered_count=0,
            covered_names=[],
            main_ingredient_names=["牛腩", "土豆", "胡萝卜", "青椒"],
            difficulty=5,
            time_minutes=60,
        )
        out = weighted_rank([title_hit, fallback], SafetyProfile(), None)
        reasons_by_id = {x["recipe_id"]: x["rank_reasons"] for x in out}
        assert any("菜名" in s for s in reasons_by_id[1])
        assert reasons_by_id[2] == ["综合匹配你的食材组合"]

    def test_single_bad_candidate_skipped(self) -> None:
        """单条候选异常被跳过，不中断整体排序（函数）。

        说明：
            覆盖 weighted_rank 的单条 except 分支：坏候选不拖垮其余结果。

        异常：
            断言失败即测试失败。
        """
        bad = _make_candidate(recipe_id=3, covered_count="not-a-number")  # int() 抛 ValueError → 跳过
        good = _make_candidate(recipe_id=4)
        out = weighted_rank([bad, good], SafetyProfile(), None)
        assert [x["recipe_id"] for x in out] == [4]
