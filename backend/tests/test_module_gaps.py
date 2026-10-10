"""B/C/H/I 模块完成度差距固化测试（进度报告 §3 判据级补齐）。

覆盖（真实 PostgreSQL aicook 库；anon_gap_ 前缀唯一匿名用户自建数据、测试自清理，
不触碰共享种子数据；通过 X-Anonymous-Id 头隔离身份）：
    - C 档案（级联删除判据）：创建带成员的家庭档案 → 删除成员 → 断言
      204 / 列表不再返回 / DB 行软删留痕（deleted_at 非空）/ 重复删除 404 /
      同家庭其余成员不受影响 / 数据导出不含软删成员（无孤儿引用）；
    - H 库存（合规红线 RL-3 判据）：GET /v1/inventory、/v1/inventory/expiring、
      /v1/home 响应体中递归字段名与文案值均无可食性判定字段/表述
      （edible/safe/fresh_* 及「还能吃/不能吃/可食用」等），仅允许中性到期提醒；
    - I 个人中心（数据导出/注销链路判据）：存在交易订单时 DELETE /v1/me → 409
      且订单与用户数据保留；无订单注销 → 反馈工单脱敏保留（user_id 置 NULL）→
      同匿名 ID 再造为新用户（user.id 变化、业务数据不串号）。
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.db import SessionLocal
from app.models import Family, FamilyMember, Feedback, InventoryItem, Order, User

# ---------------------------------------------------------------------------
# 通用工具
# ---------------------------------------------------------------------------

def _headers(anon: str) -> dict[str, str]:
    """构造携带匿名身份的请求头（函数）。

    参数：
        anon：匿名会话 ID。

    返回值：
        dict[str, str]：{X-Anonymous-Id: anon}。

    异常：
        无。
    """
    return {"X-Anonymous-Id": anon}


def _cleanup_user(anon: str) -> None:
    """按匿名 ID 清理测试用户及其自建数据（函数）。

    说明：
        order.user_id 无级联（交易凭证语义）且本模块会自造订单 → 先删订单行；
        feedback.user_id 可空 → 按唯一 content 标记删测试自建工单（覆盖注销前
        挂 user 与注销后已脱敏两种状态）；family.user_id 无级联 → 先删家庭
        （成员行含软删行经 FK 级联清理）；最后删 user（其余业务表
        ON DELETE CASCADE 级联清理）。清理失败仅遗留数据，不掩盖断言结果。

    参数：
        anon：待清理的匿名会话 ID。

    返回值：
        None。

    异常：
        不向外抛出（清理异常吞掉，不干扰测试判定）。
    """
    try:
        with SessionLocal() as db:
            user = db.execute(select(User).where(User.anonymous_id == anon)).scalar_one_or_none()
            if user is not None:
                uid = int(user.id)
                db.execute(delete(Order).where(Order.user_id == uid))
                db.execute(delete(Family).where(Family.user_id == uid))
            # 反馈工单按唯一 content 标记删（注销后 user_id 已置 NULL，按 user 删不到）
            db.execute(delete(Feedback).where(Feedback.content == f"[gap-test {anon}] 希望菜谱详情页支持收藏分组重命名"))
            if user is not None:
                db.delete(user)
            db.commit()
    except Exception:  # noqa: BLE001 —— 清理失败不掩盖测试断言结果
        pass


@pytest.fixture()
def anon_id() -> str:
    """唯一匿名 ID fixture（函数）。

    说明：
        anon_gap_ 前缀 + uuid4 短串；测试结束后兜底自清理（幂等）。

    返回值：
        str：唯一匿名 ID。

    异常：
        清理失败向上抛出（与既有测试模块约定一致）。
    """
    value = f"anon_gap_{uuid.uuid4().hex[:10]}"
    yield value
    _cleanup_user(value)


def _today_iso() -> str:
    """取本地时区今日日期 ISO 字符串（函数）。

    返回值：
        str：YYYY-MM-DD。

    异常：
        无。
    """
    from datetime import date

    return date.today().isoformat()


# ---------------------------------------------------------------------------
# C 档案：成员删除级联语义（软删 + 无孤儿引用）
# ---------------------------------------------------------------------------

def test_member_delete_soft_delete_no_orphan_refs(client: TestClient, anon_id: str) -> None:
    """删除家庭成员：软删留痕、读取端无孤儿引用（函数）。

    说明：
        删除语义为软删（deleted_at 置位，合规留痕）：档案列表与个人数据导出
        两条对外读取链路均不再返回被删成员；同家庭其余成员不受影响；
        对已删成员重复删除返回 404。

    参数：
        client：TestClient fixture（真实本地库）。
        anon_id：唯一匿名身份 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    # 建档（无家庭自动建档）+ 两个成员（过敏原三选一：一段给编码 / 一段给暂无）
    family = client.get("/v1/profile/family", headers=_headers(anon_id)).json()
    kept = client.post(
        "/v1/profile/members", json={"name": "留存的本人", "allergen_codes": ["peanut"]}, headers=_headers(anon_id)
    ).json()
    removed = client.post(
        "/v1/profile/members", json={"name": "待删成员", "no_known_allergen": True}, headers=_headers(anon_id)
    ).json()
    assert kept["id"] != removed["id"]

    # 删除成员 → 204
    assert client.delete(f"/v1/profile/members/{removed['id']}", headers=_headers(anon_id)).status_code == 204

    # 档案列表：被删成员不再出现，其余成员保留
    after = client.get("/v1/profile/family", headers=_headers(anon_id)).json()
    member_ids = [m["id"] for m in after["members"]]
    assert removed["id"] not in member_ids
    assert kept["id"] in member_ids

    # 重复删除 → 404（软删行经归属 JOIN 过滤，等同不存在）
    assert client.delete(f"/v1/profile/members/{removed['id']}", headers=_headers(anon_id)).status_code == 404

    # DB 层：软删留痕（deleted_at 非空），行仍挂原家庭（无物理孤儿引用，仅读取端过滤）
    with SessionLocal() as db:
        row = db.get(FamilyMember, int(removed["id"]))
        assert row is not None
        assert row.deleted_at is not None
        assert int(row.family_id) == int(family["family_id"])

    # 导出（对外读取第二链路）：不含软删成员，未删成员正常导出
    export = client.get("/v1/me/export", headers=_headers(anon_id)).json()
    exported_names = [m["nickname"] for m in export["profile"]["members"]]
    assert "待删成员" not in exported_names
    assert "留存的本人" in exported_names


# ---------------------------------------------------------------------------
# H 库存：RL-3 红线（响应体/文案无可食性判定）
# ---------------------------------------------------------------------------

# 可食性判定字段名 token（响应体递归字段名，小写子串匹配）
_EDIBLE_FIELD_TOKENS: tuple[str, ...] = (
    "edible", "eatable", "edibility", "safe", "fresh_ok", "freshness", "spoiled", "spoilage", "rotten",
)

# 可食性判定文案 token（响应体字符串值中出现即违规；均为「判定可否食用」表述）
_EDIBLE_TEXT_TOKENS: tuple[str, ...] = (
    "还能吃", "不能吃", "可以吃", "能吃", "可食用", "不可食用", "不能食用",
    "已变质", "未变质", "变质了", "安全食用",
)


def _collect_keys_and_texts(payload: object) -> tuple[set[str], list[str]]:
    """递归收集 JSON 结构中的全部字段名与字符串值（函数）。

    参数：
        payload：任意可 JSON 化的响应体（dict/list/标量）。

    返回值：
        tuple[set[str], list[str]]：(字段名集合（小写），字符串值列表)。

    异常：
        无。
    """
    keys: set[str] = set()
    texts: list[str] = []

    def _walk(node: object) -> None:
        """深度优先遍历 JSON 节点（内部函数）。

        参数：
            node：当前节点。

        返回值：
            None。

        异常：
            无。
        """
        if isinstance(node, dict):
            for key, value in node.items():
                keys.add(str(key).lower())
                _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)
        elif isinstance(node, str):
            texts.append(node)

    _walk(payload)
    return keys, texts


def test_inventory_and_home_no_edibility_judgment(client: TestClient, anon_id: str) -> None:
    """RL-3 红线：库存/临期/首页响应不含可食性判定字段与文案（函数）。

    说明：
        造两条库存（一条今日到期、一条无到期日）后核验三条响应链：
        GET /v1/inventory、GET /v1/inventory/expiring、GET /v1/home ——
        字段名与文案值均不得出现可食性判定（到期信息仅中性提醒）。

    参数：
        client：TestClient fixture（真实本地库）。
        anon_id：唯一匿名身份 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    # 自建数据：今日到期条目（触发临期链路）+ 无到期日条目
    created = client.post(
        "/v1/inventory",
        json={"ingredient_id": 1, "quantity_level": "mid", "expire_date": _today_iso()},
        headers=_headers(anon_id),
    )
    assert created.status_code == 201
    assert client.post(
        "/v1/inventory", json={"ingredient_id": 2, "quantity_level": "plenty"}, headers=_headers(anon_id)
    ).status_code == 201

    checked_endpoints: dict[str, object] = {
        "/v1/inventory": client.get("/v1/inventory", headers=_headers(anon_id)).json(),
        "/v1/inventory/expiring": client.get("/v1/inventory/expiring", params={"days": 3}, headers=_headers(anon_id)).json(),
        "/v1/home": client.get("/v1/home", headers=_headers(anon_id)).json(),
    }

    for endpoint, body in checked_endpoints.items():
        keys, texts = _collect_keys_and_texts(body)
        bad_fields = sorted(k for k in keys if any(token in k for token in _EDIBLE_FIELD_TOKENS))
        bad_texts = sorted({t for t in texts for token in _EDIBLE_TEXT_TOKENS if token in t})
        assert not bad_fields, f"{endpoint} 响应含可食性判定字段：{bad_fields}"
        assert not bad_texts, f"{endpoint} 响应文案含可食性判定表述：{bad_texts}"

    # 临期分组文案为中性描述（仅「距到期 X 天」，不做判定）
    expiring = checked_endpoints["/v1/inventory/expiring"]
    labels = [g["label"] for g in expiring["groups"]]
    assert all(label.startswith("距到期") for label in labels)


# ---------------------------------------------------------------------------
# I 个人中心：注销链路（订单 409 / 反馈脱敏 / 匿名再造不串号）
# ---------------------------------------------------------------------------

def test_delete_me_with_order_returns_409_and_keeps_order(client: TestClient, anon_id: str) -> None:
    """存在交易订单时拒绝注销：409 且订单/用户数据原样保留（函数）。

    说明：
        order 为交易凭证（不随用户删除且 user_id 无级联）→ 存在订单时注销
        返回 409 STATE_CONFLICT，不发生任何数据清理。

    参数：
        client：TestClient fixture（真实本地库）。
        anon_id：唯一匿名身份 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    # 造一条用户数据，用于断言 409 后数据未被清理
    inv = client.post(
        "/v1/inventory", json={"ingredient_id": 1, "quantity_level": "mid"}, headers=_headers(anon_id)
    ).json()
    order_no = f"gaptest{uuid.uuid4().hex[:24]}"
    with SessionLocal() as db:
        uid = int(db.execute(select(User.id).where(User.anonymous_id == anon_id)).scalar_one())
        db.add(Order(order_no=order_no, user_id=uid, product_type="membership", amount_cents=990, status="paid"))
        db.commit()

    resp = client.delete("/v1/me", headers=_headers(anon_id))
    assert resp.status_code == 409
    assert resp.json()["code"] == "STATE_CONFLICT"

    # 订单、用户、业务数据均保留（注销未执行）
    with SessionLocal() as db:
        order = db.execute(select(Order).where(Order.order_no == order_no)).scalar_one()
        assert int(order.user_id) == uid
        assert order.status == "paid"
        assert db.get(User, uid) is not None
        assert db.get(InventoryItem, int(inv["id"])) is not None


def test_delete_me_anonymizes_feedback_and_reanon_no_carryover(client: TestClient, anon_id: str) -> None:
    """注销：反馈工单脱敏保留 + 同匿名 ID 再造新用户不串号（函数）。

    说明：
        注销删除用户行并级联清理业务数据；feedback.user_id 置 NULL（工单
        脱敏保留）；之后同 anonymous_id 再来由 auth upsert 新建用户
        （新 user.id），旧收藏等业务数据不会出现在新用户视图。

    参数：
        client：TestClient fixture（真实本地库）。
        anon_id：唯一匿名身份 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    # 造收藏 + 反馈工单（content 携带唯一标记，供注销后按行定位）
    assert client.post("/v1/favorites", json={"recipe_id": 1}, headers=_headers(anon_id)).status_code == 201
    content = f"[gap-test {anon_id}] 希望菜谱详情页支持收藏分组重命名"
    feedback_resp = client.post("/v1/feedback", json={"content": content, "type": "other"}, headers=_headers(anon_id))
    assert feedback_resp.status_code == 201

    with SessionLocal() as db:
        uid_old = int(db.execute(select(User.id).where(User.anonymous_id == anon_id)).scalar_one())
        fb_id = int(db.execute(select(Feedback.id).where(Feedback.content == content)).scalar_one())

    # 注销 → 204
    assert client.delete("/v1/me", headers=_headers(anon_id)).status_code == 204

    with SessionLocal() as db:
        # 反馈工单保留且脱敏（user_id 置 NULL）
        fb_row = db.get(Feedback, fb_id)
        assert fb_row is not None
        assert fb_row.user_id is None
        # 用户行已删
        assert db.get(User, uid_old) is None

    # 同匿名 ID 再造：视为新用户（user.id 变化），旧业务数据不串号
    relogin = client.post("/v1/auth/anonymous", json={"anonymous_id": anon_id})
    assert relogin.status_code == 200
    with SessionLocal() as db:
        uid_new = int(db.execute(select(User.id).where(User.anonymous_id == anon_id)).scalar_one())
    assert uid_new != uid_old

    favorites = client.get("/v1/favorites", headers=_headers(anon_id)).json()
    assert favorites["items"] == []
