"""conftest 离线守卫测试（fail-closed 强制覆盖验证）。

职责：
    验证 backend/tests/conftest.py 在 pytest 进程内对离线 Provider 环境变量
    的强制覆盖行为：无论调用者（shell / CI / IDE）向测试进程预设了什么
    Provider 配置（哪怕指向真实付费 API），conftest 都必须在 app.settings
    首次导入前将其覆写为确定性离线值，杜绝外部预设穿透 setdefault。

设计（避免「用被测行为验证自己」的循环论证）：
    本文件不直接断言自身进程的 os.environ（自身进程的环境已由 conftest
    设定，断言它等于循环验证）；而是用 subprocess 以「恶意预设」重新拉起
    一个最小 pytest 运行：
        1. 在 backend/tests/ 下动态生成探针文件 test_zz_offline_guard_probe.py
          （位于 tests/ 下才能触发真实 backend/tests/conftest.py）；
        2. 子进程环境注入恶意预设（LLM_BASE_URL 指向真实 api.deepseek.com、
           EMBEDDING_PROVIDER=zhipu、MCP/语音开关全开等）；
        3. 探针断言 os.environ 与 app.core.config.settings 单例读到的均为
           离线值（settings 断言锁定导入时机：conftest 的覆盖必须发生在
           config 单例构造之前）；
        4. finally 删除探针文件，不污染测试目录。
    conftest 未强制覆盖（setdefault 穿透）时，探针读到恶意值 → 子 pytest
    失败 → 本测试失败（Red）；改为强制赋值后子 pytest 全绿（Green）。

边界：
    PAYMENT_PROVIDER 不在 config.py Settings 字段中（payment.py 工厂直接读
    进程环境变量），故仅在 os.environ 层断言，不做 settings 字段断言。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# backend 根目录（tests/ 的上级；subprocess 的 cwd 与 pytest 运行起点）
_BACKEND_ROOT = Path(__file__).resolve().parents[1]

# 探针文件名（zz 前缀保证排序在最后；动态生成、跑完即删）
_PROBE_NAME = "test_zz_offline_guard_probe.py"
_PROBE_PATH = Path(__file__).resolve().parent / _PROBE_NAME

# 恶意预设：模拟调用者误将真实 Provider / 开关预设进测试进程环境
# （值本身为伪造占位，非真实凭证；仅用于验证 conftest 是否强制覆盖）
_MALICIOUS_PRESET: dict[str, str] = {
    "LLM_BASE_URL": "https://api.deepseek.com",
    "LLM_API_KEY": "sk-fake-preset-should-be-overridden",
    "EMBEDDING_PROVIDER": "zhipu",
    "VISION_PROVIDER": "vlm",
    "SPEECH_PROVIDER": "real",
    "TTS_PROVIDER": "real",
    "PAYMENT_PROVIDER": "wechat",
    "MCP_ENABLED": "on",
    "EMBEDDING_WARMUP": "on",
    "VOICE_INTENT_ENABLED": "on",
    "COOKING_HELP_AGENT_ENABLED": "on",
}

# conftest 必须强制生效的离线值（与 conftest._OFFLINE_ENV 语义对齐）
_OFFLINE_EXPECTED: dict[str, str] = {
    "LLM_BASE_URL": "http://127.0.0.1:9",
    "LLM_API_KEY": "test-offline",
    "VISION_PROVIDER": "mock",
    "SPEECH_PROVIDER": "mock",
    "TTS_PROVIDER": "mock",
    "PAYMENT_PROVIDER": "mock",
    "EMBEDDING_PROVIDER": "hash",
    "EMBEDDING_WARMUP": "off",
    "MCP_ENABLED": "off",
    "VOICE_INTENT_ENABLED": "off",
    "COOKING_HELP_AGENT_ENABLED": "off",
}

# 探针文件源码模板（os.environ 层 + settings 单例层双重断言；
# expected 以 JSON 字面量注入，避免嵌套引号转义问题）
_PROBE_TEMPLATE = '''"""conftest 离线守卫探针（动态生成，跑完即删，勿提交）。

由 test_conftest_offline_guard.py 在子 pytest 中运行：
断言本进程 os.environ 与 app.core.config.settings 单例均为离线值。
"""

from __future__ import annotations

import json
import os

# 环境变量层期望值（conftest 强制覆盖后的离线值）
_EXPECTED_ENV = json.loads(r"""{expected_env}""")

# settings 单例字段 ↔ 环境变量键映射（PAYMENT_PROVIDER 非 Settings 字段，
# 仅在 os.environ 层断言，故不在此映射中）
_SETTINGS_FIELDS = json.loads(r"""{settings_fields}""")


def test_probe_os_environ_offline() -> None:
    """断言 os.environ 关键键均为 conftest 强制的离线值（函数）。

    说明：
        恶意预设未被覆盖时此断言失败（setdefault 穿透取证点）。

    返回值：
        None。

    异常：
        AssertionError：任一键值非离线期望值。
    """
    for key, want in _EXPECTED_ENV.items():
        got = os.environ.get(key)
        assert got == want, "os.environ[{key!r}]={got!r} != offline {want!r} (preset leak)".format(
            key=key, got=got, want=want
        )


def test_probe_settings_singleton_offline() -> None:
    """断言 settings 单例字段均为离线值（锁定导入时机，函数）。

    说明：
        settings 在 config 模块导入时构造；若 conftest 的 env 覆盖晚于
        app 首次导入，settings 会固化恶意预设值，此断言即失败。

    返回值：
        None。

    异常：
        AssertionError：settings 字段值非离线期望值。
    """
    from app.core.config import settings

    for env_key, field in _SETTINGS_FIELDS.items():
        got = getattr(settings, field)
        want = _EXPECTED_ENV[env_key]
        assert got == want, "settings.{field}={got!r} != offline {want!r} (env key {key!r})".format(
            field=field, got=got, want=want, key=env_key
        )
'''.replace("{expected_env}", json.dumps(_OFFLINE_EXPECTED, ensure_ascii=False)).replace(
    "{settings_fields}", json.dumps({k: k for k in _OFFLINE_EXPECTED if k != "PAYMENT_PROVIDER"})
)


def _run_probe_pytest() -> subprocess.CompletedProcess[str]:
    """以恶意预设环境在子进程运行探针 pytest（函数）。

    说明：
        子进程 env = 当前环境 + 恶意预设覆盖；cwd 固定 backend 根；
        -p no:cacheprovider 隔离缓存副作用。

    返回值：
        subprocess.CompletedProcess[str]：子 pytest 运行结果（已捕获 stdout）。

    异常：
        subprocess.TimeoutExpired：子 pytest 超过 300s 未结束（向上抛出）。
    """
    child_env = {**os.environ, **_MALICIOUS_PRESET, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [sys.executable, "-m", "pytest", f"tests/{_PROBE_NAME}", "-q", "-p", "no:cacheprovider"],
        cwd=str(_BACKEND_ROOT),
        env=child_env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )


def test_conftest_forces_offline_env_over_malicious_preset() -> None:
    """恶意预设穿透验证：conftest 必须强制覆盖为离线值（函数）。

    说明：
        生成探针 → 子 pytest（恶意预设 env）运行 → 断言子 pytest 通过
        （即探针读到的 os.environ 与 settings 全部为离线值）→ finally
        删除探针文件。子 pytest 失败时把输出并入断言消息便于取证。

    返回值：
        None。

    异常：
        AssertionError：子 pytest 非零退出（存在预设穿透或探针异常）。
        subprocess.TimeoutExpired：子 pytest 超时。
    """
    _PROBE_PATH.write_text(_PROBE_TEMPLATE, encoding="utf-8")
    try:
        result = _run_probe_pytest()
    finally:
        _PROBE_PATH.unlink(missing_ok=True)
    assert result.returncode == 0, (
        "conftest 未强制离线（恶意预设穿透 setdefault）或探针异常：\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )
    # 收集健全性：子 pytest 必须真的收集并运行了 2 个探针用例
    assert "2 passed" in result.stdout, f"探针未按预期收集运行（stdout）：\n{result.stdout}"
