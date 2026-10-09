"""远程开关与管理员账号种子数据模块。

职责：
    - remote_config：5 个模块开关（switch.recommend/vision/qa/payment/innovation，
      默认全开，05-V1.1 §4.4）+ 排序权重 rank.weights（7 因子，合计 1.00），
      按 config_key upsert（60s 内生效语义，spec D6）；
    - admin_user：内置管理员 admin（passlib pbkdf2_sha256 加盐哈希），
      密码来自环境变量 ADMIN_PASSWORD（缺省 Admin@123456）。
"""

import os

from passlib.context import CryptContext

# pbkdf2_sha256 上下文：纯 Python 实现，不依赖系统 crypt（Python 3.13 已移除 crypt 模块）
_pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

# passlib 哈希前缀（用于识别存量库中旧格式哈希并平滑升级）
PASSLIB_HASH_PREFIX = "$pbkdf2-sha256$"

# 阶段一远程开关（05-V1.1 §4.4：5 个模块开关默认开）
REMOTE_CONFIGS: list[tuple[str, object]] = [
    ("switch.recommend", True),
    ("switch.vision", True),
    ("switch.qa", True),
    ("switch.payment", True),
    # switch.innovation：05-V1.1 §4.4 第 5 个远程开关（模块 O「AI 菜品创新」）；
    # 模块 O 属阶段二（CR-20261008-01 甲方确认 Q15 不纳入阶段一），
    # 阶段一仅按文档口径下发该配置，不做任何业务实现。
    ("switch.innovation", True),
    # 7 因子排序权重（spec Task 2.4：0.30/0.15/0.15/0.15/0.10/0.10/0.05）
    (
        "rank.weights",
        {
            "coverage": 0.30,     # 食材覆盖率
            "expiring": 0.15,     # 临期优先
            "taste": 0.15,        # 口味匹配
            "goal": 0.15,         # 饮食目标
            "difficulty": 0.10,   # 难度适配
            "history": 0.10,      # 历史偏好
            "popularity": 0.05,   # 热度
        },
    ),
]

# 内置管理员账号（仅本地 PoC 演示用；密码可由环境变量 ADMIN_PASSWORD 覆盖）
ADMIN_USERNAME = "admin"
ADMIN_DEFAULT_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin@123456")
ADMIN_ROLE = "super_admin"


def hash_password(password: str) -> str:
    """生成管理员密码哈希（函数）。

    说明：
        使用 passlib 的 pbkdf2_sha256 方案（随机盐，自动迭代次数），
        存储格式 $pbkdf2-sha256$<rounds>$<salt>$<hash>（passlib 标准）。

    参数：
        password：明文密码。

    返回值：
        str：可存储于 admin_user.password_hash 字段的哈希串。

    异常：
        无。
    """
    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """校验明文密码与哈希是否匹配（函数）。

    参数：
        password：待校验明文密码。
        password_hash：库中存储的 passlib 哈希串。

    返回值：
        bool：匹配返回 True；不匹配或哈希格式非法返回 False。

    异常：
        无。
    """
    try:
        return _pwd_context.verify(password, password_hash)
    except Exception:  # noqa: BLE001 —— 旧格式/损坏哈希统一按不匹配处理
        return False


def is_passlib_hash(password_hash: str) -> bool:
    """判断哈希串是否为 passlib pbkdf2_sha256 格式（函数）。

    参数：
        password_hash：库中存储的哈希串。

    返回值：
        bool：passlib 标准格式返回 True（旧 hashlib 手写格式返回 False）。

    异常：
        无。
    """
    return str(password_hash).startswith(PASSLIB_HASH_PREFIX)
