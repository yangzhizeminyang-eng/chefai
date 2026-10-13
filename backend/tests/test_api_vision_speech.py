"""识别与语音接口测试（spec Task 5 模块 D）。

覆盖：
    - POST /v1/vision/recognize：开关关闭 403 / 正常识别 quota 扣减 /
      全低置信不扣额度 / provider 异常降级 200 degraded / 额度耗尽 429；
    - POST /v1/vision/confirm：真实食材 added / 伪食材 skipped / 别名命中；
    - POST /v1/speech/asr：mock 演示文本返回 / provider 异常降级 200；
    - MockVisionProvider 直测：返回项必为 ingredient 表真实存在的名字；
    - ability.uploads.cleanup_uploads：超期文件清理（tmp_path 新旧文件断言）。

说明：
    router.py 的注册行由主控统一接线（Task 5 禁改 router.py），测试模块导入期
    幂等 include vision/speech 路由以保证端点可测；主控落位注册行后本 include
    自动跳过（按 path 判重）。
"""

from __future__ import annotations

import os
import time
import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.ability.providers import (
    MOCK_ASR_TEXT,
    MockASRProvider,
    MockVisionProvider,
    RecognizedItem,
    VisionProvider,
)
from app.ability.uploads import cleanup_uploads
from app.api.v1 import speech as speech_module
from app.api.v1 import vision as vision_module
from app.core.db import SessionLocal
from app.main import app
from app.models import Ingredient, RemoteConfig, User

# ---- 路由接线（幂等）：router.py 注册行由主控落位，测试期确保端点可达 ----
# （/v1 前缀在 router.py 的 api_router 上，此处 include 时显式补齐）
if not any(getattr(r, "path", None) == "/v1/vision/recognize" for r in app.routes):
    app.include_router(vision_module.router, prefix="/v1")
    app.include_router(speech_module.router, prefix="/v1")


class _StubHighProvider(VisionProvider):
    """桩视觉 provider（测试用）：恒定返回 1 个 high + 1 个 low 识别项（模型类）。"""

    def recognize(self, image_bytes: bytes) -> list[RecognizedItem]:
        """返回固定识别项（函数）。

        参数：
            image_bytes：图片字节（忽略）。

        返回值：
            list[RecognizedItem]：1 个 high（番茄）+ 1 个 low（未知物体）。

        异常：
            无。
        """
        return [
            RecognizedItem(name="番茄", confidence="high", ingredient_id=1),
            RecognizedItem(name="未知物体", confidence="low", ingredient_id=None),
        ]


class _StubAllLowProvider(VisionProvider):
    """桩视觉 provider（测试用）：恒定返回全 low 识别项（模型类）。"""

    def recognize(self, image_bytes: bytes) -> list[RecognizedItem]:
        """返回全低置信识别项（函数）。

        参数：
            image_bytes：图片字节（忽略）。

        返回值：
            list[RecognizedItem]：单项 low。

        异常：
            无。
        """
        return [RecognizedItem(name="疑似食材", confidence="low", ingredient_id=None)]


class _StubErrorProvider(VisionProvider):
    """桩视觉 provider（测试用）：恒定抛异常，模拟真实模型故障（模型类）。"""

    def recognize(self, image_bytes: bytes) -> list[RecognizedItem]:
        """模拟 provider 故障（函数）。

        参数：
            image_bytes：图片字节（忽略）。

        返回值：
            无（恒抛出）。

        异常：
            RuntimeError：模拟模型调用失败。
        """
        raise RuntimeError("mock vision provider boom")


def _anon_headers() -> dict[str, str]:
    """生成唯一匿名用户请求头（函数）。

    返回值：
        dict：X-Anonymous-Id 请求头（每次调用唯一，保证测试可重复执行）。

    异常：
        无。
    """
    return {"X-Anonymous-Id": f"anon_t5_{uuid.uuid4().hex[:10]}"}


_UPLOAD_IMAGE = {"file": ("photo.jpg", b"\xff\xd8\xff\xe0fake-jpeg-bytes-for-mock", "image/jpeg")}


def _set_vision_switch(value: bool) -> None:
    """写 remote_config 的 switch.vision 开关（函数）。

    说明：
        直接更新种子行（不新增行）；测试负责在 finally 中恢复 True。

    参数：
        value：开关目标值。

    返回值：
        None。

    异常：
        数据库异常向上抛出（环境前置条件不满足）。
    """
    with SessionLocal() as session:
        row = session.execute(
            select(RemoteConfig).where(RemoteConfig.config_key == "switch.vision")
        ).scalar_one_or_none()
        if row is not None:
            row.value = value
            session.commit()


def test_vision_disabled_403(client: TestClient) -> None:
    """switch.vision=false 时识别接口返回 403（函数）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    _set_vision_switch(False)
    try:
        resp = client.post("/v1/vision/recognize", files=_UPLOAD_IMAGE, headers=_anon_headers())
        assert resp.status_code == 403
        body = resp.json()
        assert body["code"] == "FORBIDDEN"
        assert body["message"] == "识别功能暂未开放，请手动选择食材"
    finally:
        _set_vision_switch(True)


def test_vision_recognize_quota_deduction(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """正常识别（含 high 项）扣减额度，重复调用累加（函数）。

    参数：
        client：TestClient fixture。
        monkeypatch：替换 vision 模块的 provider 工厂。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    monkeypatch.setattr(vision_module, "get_vision_provider", lambda: _StubHighProvider())
    headers = _anon_headers()
    resp = client.post("/v1/vision/recognize", files=_UPLOAD_IMAGE, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["degraded"] is False
    assert "番茄" in [item["name"] for item in body["recognized"]]
    assert body["quota"]["used"] == 1
    assert body["quota"]["limit"] in (3, 10)
    assert body["quota"]["remaining"] == body["quota"]["limit"] - 1

    # 第二次调用：同一用户额度继续扣减
    resp2 = client.post("/v1/vision/recognize", files=_UPLOAD_IMAGE, headers=headers)
    assert resp2.status_code == 200
    assert resp2.json()["quota"]["used"] == 2


def test_vision_all_low_confidence_no_consume(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """全低置信（无 high 项）不扣额度（函数）。

    参数：
        client：TestClient fixture。
        monkeypatch：替换 vision 模块的 provider 工厂。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    monkeypatch.setattr(vision_module, "get_vision_provider", lambda: _StubAllLowProvider())
    resp = client.post("/v1/vision/recognize", files=_UPLOAD_IMAGE, headers=_anon_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["degraded"] is False
    assert body["quota"]["used"] == 0
    assert body["message"]


def test_vision_provider_error_degraded(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """provider 异常降级为 200 degraded 且不扣额度（函数）。

    参数：
        client：TestClient fixture。
        monkeypatch：替换 vision 模块的 provider 工厂。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    monkeypatch.setattr(vision_module, "get_vision_provider", lambda: _StubErrorProvider())
    resp = client.post("/v1/vision/recognize", files=_UPLOAD_IMAGE, headers=_anon_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["degraded"] is True
    assert body["recognized"] == []
    assert body["message"] == "识别暂时不可用，请手动选择食材"
    assert body["quota"]["used"] == 0


def test_vision_quota_exhausted_429(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """额度耗尽返回 429（含 quota 三元组）（函数）。

    说明：
        预置用户当日用量=免费上限 3，识别请求应直接 429 且不触达 provider。

    参数：
        client：TestClient fixture。
        monkeypatch：替换 vision 模块的 provider 工厂。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    monkeypatch.setattr(vision_module, "get_vision_provider", lambda: _StubErrorProvider())
    anon = f"anon_t5_quota_{uuid.uuid4().hex[:10]}"
    today = date.today().isoformat()
    with SessionLocal() as session:
        user = User(anonymous_id=anon, preferences={"vision_usage": {"date": today, "used": 3}})
        session.add(user)
        session.commit()
        user_id = int(user.id)
    try:
        resp = client.post("/v1/vision/recognize", files=_UPLOAD_IMAGE, headers={"X-Anonymous-Id": anon})
        assert resp.status_code == 429
        body = resp.json()
        assert body["code"] == "QUOTA_EXCEEDED"
        assert body["message"] == "今日识别次数已用完"
        assert body["quota"]["remaining"] == 0
        assert body["quota"]["limit"] == 3
    finally:
        with SessionLocal() as session:
            row = session.get(User, user_id)
            if row is not None:
                session.delete(row)
                session.commit()


def test_vision_quota_boundary_three_ok_then_reject(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """额度真实边界：第 1~3 次识别成功，第 4 次拒绝 429（函数）。

    说明：
        区别于预置 used=3 的用例（test_vision_quota_exhausted_429），本用例
        连续真实扣减 3 次验证逐次递减与第 3 次仍 200（remaining=0）的边界。

    参数：
        client：TestClient fixture。
        monkeypatch：替换 vision 模块的 provider 工厂。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    monkeypatch.setattr(vision_module, "get_vision_provider", lambda: _StubHighProvider())
    headers = _anon_headers()
    for expected_used in range(1, 4):
        resp = client.post("/v1/vision/recognize", files=_UPLOAD_IMAGE, headers=headers)
        assert resp.status_code == 200, f"第 {expected_used} 次识别应成功"
        quota = resp.json()["quota"]
        assert quota["used"] == expected_used
        assert quota["remaining"] == 3 - expected_used
        if expected_used == 3:
            assert quota["remaining"] == 0  # 第 3 次成功后额度恰好耗尽

    resp4 = client.post("/v1/vision/recognize", files=_UPLOAD_IMAGE, headers=headers)
    assert resp4.status_code == 429
    body = resp4.json()
    assert body["code"] == "QUOTA_EXCEEDED"
    assert body["quota"]["remaining"] == 0
    assert body["quota"]["limit"] == 3


def test_vision_confirm_repeat_idempotent(client: TestClient) -> None:
    """confirm 重复确认行为：同一批名字重复调用结果稳定、无副作用（函数）。

    说明：
        confirm 为纯存在性校验（后端不入库），重复确认同一批真实食材两次
        均应 added 一致且 skipped 为空；重复伪食材两次均稳定 skipped。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    names = ["番茄", "土豆"]
    fake = ["绝对不存在的伪食材xyz"]
    first = client.post("/v1/vision/confirm", json={"names": names + fake}).json()
    second = client.post("/v1/vision/confirm", json={"names": names + fake}).json()
    assert first == second, "重复 confirm 响应应稳定一致（幂等语义）"
    assert first["added"] == 2
    assert first["skipped"] == fake


def test_vision_recognize_triggers_lazy_cleanup(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """recognize 调用触发 uploads 惰性清理，成功识别顺带留档（函数）。

    说明：
        将 vision 模块的留档根目录指向 tmp_path：预置一个 mtime 超 24h 的
        过期文件，识别成功后应被顺手清理；同时当天留档文件应存在
        （high 项场景落盘，日期子目录 {yyyymmdd}）。

    参数：
        client：TestClient fixture。
        monkeypatch：替换 provider 工厂与留档根目录。
        tmp_path：pytest 临时目录 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    monkeypatch.setattr(vision_module, "get_vision_provider", lambda: _StubHighProvider())
    monkeypatch.setattr(vision_module, "_UPLOAD_BASE_DIR", tmp_path)
    expired = tmp_path / "20260101"
    expired.mkdir()
    old_file = expired / "old.jpg"
    old_file.write_bytes(b"expired-image")
    old_ts = time.time() - 25 * 3600
    os.utime(old_file, (old_ts, old_ts))

    resp = client.post("/v1/vision/recognize", files=_UPLOAD_IMAGE, headers=_anon_headers())
    assert resp.status_code == 200

    assert not old_file.exists(), "超 24h 的过期留档应被惰性清理"
    today_dir = tmp_path / date.today().strftime("%Y%m%d")
    archived = list(today_dir.glob("*.jpg")) if today_dir.exists() else []
    assert len(archived) == 1, "成功识别（有 high 项）应留档 1 张当天图片"


def test_vision_confirm_real_and_fake(client: TestClient) -> None:
    """confirm：真实食材计入 added，伪食材列入 skipped（函数）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    resp = client.post(
        "/v1/vision/confirm",
        json={"names": ["番茄", "土豆", "绝对不存在的伪食材xyz"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["added"] == 2
    assert body["skipped"] == ["绝对不存在的伪食材xyz"]


def test_vision_confirm_alias_hit(client: TestClient) -> None:
    """confirm：别名（西红柿→番茄）命中不计入 skipped（函数）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    resp = client.post("/v1/vision/confirm", json={"names": ["西红柿"]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["added"] == 1
    assert body["skipped"] == []


def test_mock_vision_provider_returns_real_ingredients() -> None:
    """MockVisionProvider 直测：返回项必为 ingredient 表真实存在的食材名（函数）。

    说明：
        识别项数量 3~6、confidence 两档合法、ingredient_id 非空且名字在库。

    参数：
        无。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    items = MockVisionProvider().recognize(b"deterministic-test-image-bytes")
    assert 3 <= len(items) <= 6
    with SessionLocal() as session:
        db_names = {str(name) for (name,) in session.execute(select(Ingredient.name)).all()}
    for item in items:
        assert item.name in db_names, f"mock 识别名 {item.name} 不在 ingredient 表"
        assert item.confidence in ("high", "low")
        assert item.ingredient_id is not None
    # 确定性：同一图片字节两次识别结果一致
    again = MockVisionProvider().recognize(b"deterministic-test-image-bytes")
    assert [(i.name, i.confidence, i.ingredient_id) for i in items] == [
        (i.name, i.confidence, i.ingredient_id) for i in again
    ]


def test_speech_asr_returns_mock_text(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """ASR 正常返回 mock 演示文本（函数）。

    说明：
        显式指定 MockASRProvider：.env 将 SPEECH_PROVIDER 切为 bailian 后
        默认工厂会构建真实 provider（fake 音频走降级路径），本用例只测 mock
        文本契约，与部署配置解耦。

    参数：
        client：TestClient fixture。
        monkeypatch：替换 speech 模块的 provider 工厂。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    monkeypatch.setattr(speech_module, "get_speech_provider", lambda: MockASRProvider())
    resp = client.post(
        "/v1/speech/asr",
        files={"file": ("voice.webm", b"fake-audio-bytes-in-memory", "audio/webm")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["text"] == MOCK_ASR_TEXT
    assert body["degraded"] is False


def test_speech_asr_provider_error_degraded(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """ASR provider 异常降级为 200 空文本（函数）。

    参数：
        client：TestClient fixture。
        monkeypatch：替换 speech 模块的 provider 工厂。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """

    def _boom() -> VisionProvider:
        """抛异常的工厂（内部函数）。

        返回值：
            无（恒抛出）。

        异常：
            RuntimeError：模拟 ASR 服务故障。
        """
        raise RuntimeError("mock asr boom")

    monkeypatch.setattr(speech_module, "get_speech_provider", _boom)
    resp = client.post(
        "/v1/speech/asr",
        files={"file": ("voice.webm", b"fake-audio", "audio/webm")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["text"] == ""
    assert body["degraded"] is True
    assert body["message"] == "语音识别暂不可用，请使用文字输入"


def test_cleanup_uploads_removes_expired_files(tmp_path) -> None:
    """清理函数删除超期文件并顺带移除空子目录，保留新文件（函数）。

    参数：
        tmp_path：pytest 临时目录 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    old_dir = tmp_path / "20260101"
    old_dir.mkdir()
    old_file = old_dir / "old.jpg"
    old_file.write_bytes(b"old-image")
    nested_old = old_dir / "nested.jpg"
    nested_old.write_bytes(b"old-image-2")
    new_file = tmp_path / "new.jpg"
    new_file.write_bytes(b"fresh-image")

    old_ts = time.time() - 25 * 3600  # 25 小时前 > 24h 阈值
    os.utime(old_file, (old_ts, old_ts))
    os.utime(nested_old, (old_ts, old_ts))

    removed = cleanup_uploads(tmp_path, max_age_hours=24)

    assert removed == 2
    assert not old_file.exists()
    assert not nested_old.exists()
    assert new_file.exists()
    assert not old_dir.exists()  # 清空的日期子目录顺带移除


def test_cleanup_uploads_missing_dir(tmp_path) -> None:
    """清理不存在的目录安全返回 0（函数）。

    参数：
        tmp_path：pytest 临时目录 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    removed = cleanup_uploads(tmp_path / "not-exist", max_age_hours=24)
    assert removed == 0
