"""菜谱向量嵌入模块（Task 8：pgvector 混合检索 R-1 收敛；向量模型升级扩展）。

职责：
    - EmbeddingProvider 抽象：统一 embed(texts) 接口（1024 维、L2 归一化，点积即余弦）；
    - HashEmbeddingProvider：确定性哈希嵌入（阶段一默认，纯标准库，无模型下载）；
    - BGEM3Provider：bge-m3 本地部署占位（阶段二启用，实例化即抛 NotImplementedError）；
    - BailianEmbeddingProvider：阿里云百炼 qwen3.7-text-embedding 远程嵌入提供方
      （OpenAI 兼容协议，EMBEDDING_PROVIDER='bailian' 时启用，失败回落 hash）；
    - EmbeddingUnavailableError：百炼嵌入调用失败的统一包装异常（检索层捕获降级）；
    - get_embedding_provider 工厂：按 EMBEDDING_PROVIDER（'hash' 缺省 | 'bailian' | 'bgem3'）
      选择实现（进程内单例）；
    - 查询嵌入 LRU 缓存（模块级，_cache_get/_cache_put，容量 512，启动预热与工厂
      单例共享同一缓存）；
    - probe_pgvector：pgvector 扩展 + recipe_embedding.embedding 向量列双重探测（模块级缓存）；
    - ensure_embeddings：published 官方菜谱向量回填（幂等，embedding_json 便携列存储，
      pgvector 可用时同步双写向量列；按嵌入空间 embedding_model 列过滤，GAP-4）；
    - upsert_embedding：单条向量 upsert（供 Task 7 创新链路写入 source='ai_private' 行）。

嵌入空间标识说明（GAP-4）：
    EmbeddingProvider.space_name 是嵌入空间标识（如 'hash-v1'、'qwen3.7-text-embedding'），
    写入 recipe_embedding.embedding_model 列；检索与回填都按当前 provider.space_name
    过滤——不同空间的向量绝不允许混用余弦相似度（维度/语义均不可比），模型升级后
    旧空间行自然失效，回填按新空间幂等重建。

确定性说明：
    HashEmbeddingProvider 基于字符 bigram + 单字 TF 哈希（md5 → 桶索引），同文本
    永远产出同一向量、纯 Python 计算（390 菜谱 × ~30 特征毫秒级完成），满足演示
    与回归测试的稳定性要求；语义质量由百炼/ bge-m3 替换（接口不变，调用方无感）。
"""

from __future__ import annotations

import hashlib
import math
import threading
from abc import ABC, abstractmethod
from collections import OrderedDict

import openai
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import engine
from app.core.logging import get_logger
from app.models import Ingredient, Recipe, RecipeEmbedding, RecipeIngredient

logger = get_logger(__name__)

# 嵌入向量维度（与迁移 b8d3f5a21c60 的 embedding vector(1024) 列对齐）
EMBEDDING_DIMENSION = 1024

# pgvector 探测结果模块级缓存（None=未探测；进程内只探一次，迁移后重启生效）
_probe_cache: bool | None = None
_probe_lock = threading.Lock()

# 惰性回填进程锁：防止并发请求在 verified 计数=0 时重复回填
_BACKFILL_LOCK = threading.Lock()

# 嵌入提供方进程级单例（回填与查询必须使用同一嵌入空间）
_PROVIDER_SINGLETON: EmbeddingProvider | None = None
_PROVIDER_LOCK = threading.Lock()

# 查询嵌入 LRU 缓存容量（普通查询文本条数远小于此；防极端输入撑爆内存）
_EMBED_CACHE_CAPACITY = 512
# 模块级缓存（而非实例级）：启动预热的临时实例与 get_embedding_provider() 单例共享，
# 避免同一查询文本被重复调用远程嵌入 API
_embed_cache: OrderedDict[str, list[float]] = OrderedDict()
_embed_cache_lock = threading.Lock()


class EmbeddingUnavailableError(RuntimeError):
    """嵌入提供方不可用异常（模型类）。

    说明：
        统一包装百炼嵌入 API 的网络/超时/鉴权/维度不符等失败，
        检索层捕获后降级关键词路径（接口恒 200），CLI 显式失败退出。

    异常：
        无。
    """


def _cache_get(key: str) -> list[float] | None:
    """从模块级 LRU 缓存读取查询向量（函数）。

    说明：
        命中时把键移动到有序字典末尾（标记为最近使用），配合 _cache_put
        的容量淘汰实现 LRU 语义；全程持模块级锁，保证多线程安全。

    参数：
        key：缓存键（空间名 + 归一化文本拼接）。

    返回值：
        list[float] | None：命中返回归一化向量的拷贝；未命中返回 None。

    异常：
        无。
    """
    with _embed_cache_lock:
        vec = _embed_cache.get(key)
        if vec is None:
            return None
        _embed_cache.move_to_end(key)  # 命中即提升为最近使用
        return list(vec)


def _cache_put(key: str, vec: list[float]) -> None:
    """向模块级 LRU 缓存写入查询向量（函数）。

    说明：
        超容量时淘汰最旧（有序字典头部）键；全程持模块级锁。
        缓存仅用于查询侧加速，回填批量向量不进缓存（一次性、量大且不再复用）。

    参数：
        key：缓存键（空间名 + 归一化文本拼接）。
        vec：已 L2 归一化的嵌入向量（1024 维）。

    返回值：
        None。

    异常：
        无。
    """
    with _embed_cache_lock:
        _embed_cache[key] = list(vec)
        _embed_cache.move_to_end(key)
        while len(_embed_cache) > _EMBED_CACHE_CAPACITY:
            _embed_cache.popitem(last=False)  # 淘汰最旧的缓存项


def _tokenize(text_value: str) -> list[str]:
    """把文本切分为哈希特征 token 列表（函数）。

    说明：
        阶段一不引入 jieba 等分词依赖：中文按「单字 + 相邻字符 bigram」、
        英文/数字按连续词切分，兼顾召回面与确定性。

    参数：
        text_value：待切分文本。

    返回值：
        list[str]：特征 token 列表（含重复，供 TF 统计）。

    异常：
        无。
    """
    normalized = "".join(text_value.split()).lower()
    tokens: list[str] = list(normalized)  # 单字特征
    tokens.extend(normalized[i] + normalized[i + 1] for i in range(len(normalized) - 1))  # 字符 bigram
    # 连续 ASCII 字母/数字词（如 "salad"、"100"）作为整词特征
    word: list[str] = []
    for ch in normalized:
        if ch.isascii() and ch.isalnum():
            word.append(ch)
        elif word:
            tokens.append("".join(word))
            word = []
    if word:
        tokens.append("".join(word))
    return tokens


def _to_vector_literal(vector: list[float]) -> str:
    """把向量序列化为 pgvector 字面量（函数）。

    参数：
        vector：浮点向量（1024 维）。

    返回值：
        str：形如 "[0.1,0.2,...]" 的 pgvector 可 CAST 字符串。

    异常：
        无。
    """
    return "[" + ",".join(f"{x:.6f}" for x in vector) + "]"


class EmbeddingProvider(ABC):
    """嵌入向量提供方抽象基类（模型类）。

    说明：
        统一约定：embed 返回与输入等长的向量列表，每条维度为 dimension
        （1024）且已 L2 归一化——点积即余弦相似度，检索层无需再归一化。

    属性：
        dimension：向量维度（默认 1024）。
        space_name：嵌入空间标识（如 'hash-v1'）——写入 recipe_embedding.embedding_model
          列，检索/回填按其过滤（GAP-4）：不同嵌入空间的向量不混用余弦相似度。

    异常：
        无。
    """

    dimension: int = EMBEDDING_DIMENSION
    # 嵌入空间标识：写入 embedding_model 列；检索/回填按其过滤（GAP-4，模型升级防混用）
    space_name: str = "hash-v1"

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """批量文本嵌入（抽象方法）。

        参数：
            texts：文本列表（可为空列表，返回空列表）。

        返回值：
            list[list[float]]：与 texts 等长的归一化向量列表（每条 dimension 维）。

        异常：
            实现方自定义（网络/模型异常向上抛出，由调用方降级）。
        """


class HashEmbeddingProvider(EmbeddingProvider):
    """确定性哈希嵌入提供方（模型类，阶段一默认演示实现）。

    说明：
        特征 = 单字 + 字符 bigram + ASCII 词；每个特征经 md5 哈希映射到
        [0, 1024) 桶并累加 TF 权重，最后 L2 归一化。同文本永远同向量
        （确定性），纯标准库实现，满足离线/无模型环境的向量链路演示。
    """

    def embed(self, texts: list[str]) -> list[list[float]]:
        """批量确定性哈希嵌入（函数）。

        参数：
            texts：文本列表。

        返回值：
            list[list[float]]：归一化后的 1024 维向量列表（与 texts 等长、顺序一致）。

        异常：
            无。
        """
        vectors: list[list[float]] = []
        for item in texts:
            buckets = [0.0] * self.dimension
            for token in _tokenize(item):
                digest = hashlib.md5(token.encode("utf-8")).hexdigest()
                index = int(digest[:8], 16) % self.dimension
                buckets[index] += 1.0
            norm = math.sqrt(sum(x * x for x in buckets))
            if norm > 0:
                buckets = [x / norm for x in buckets]
            vectors.append(buckets)
        return vectors


class BGEM3Provider(EmbeddingProvider):
    """bge-m3 本地部署嵌入提供方（模型类，阶段二占位）。

    说明：
        阶段一不下载向量模型（spec D5），实例化即抛 NotImplementedError。
        阶段二启用方式：
            1. pip install FlagEmbedding（或 sentence-transformers）；
            2. 本地加载：from FlagEmbedding import BGEM3FlagModel;
               model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True)；
            3. embed 返回 model.encode(texts)["dense_vecs"]（1024 维），
               逐条 L2 归一化后返回；
            4. 环境变量 EMBEDDING_PROVIDER=bgem3 切换，检索/回填链路无需改动。
    """

    def __init__(self) -> None:
        """构造函数：阶段一强制占位（函数）。

        异常：
            NotImplementedError：bge-m3 本地部署属阶段二范围，未启用前禁止实例化。
        """
        raise NotImplementedError(
            "BGEM3Provider 为阶段二占位实现：需 pip install FlagEmbedding 并本地加载 "
            "BAAI/bge-m3（dense 1024 维）后启用；阶段一请使用默认 HashEmbeddingProvider。"
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        """批量 bge-m3 嵌入（占位，函数）。

        参数：
            texts：文本列表。

        返回值：
            list[list[float]]：归一化向量列表（阶段二实现）。

        异常：
            NotImplementedError：占位未实现。
        """
        raise NotImplementedError("BGEM3Provider.embed 阶段二实现（见类 docstring 启用步骤）。")


class BailianEmbeddingProvider(EmbeddingProvider):
    """阿里云百炼 qwen3.7-text-embedding 嵌入提供方（模型类，OpenAI 兼容协议远程调用）。

    说明：
        - API BASE/KEY 缺省回落 VISION_BASE_URL/VISION_API_KEY（百炼同一凭证）；
        - space_name 取 EMBEDDING_MODEL_NAME（缺省 'qwen3.7-text-embedding'），
          写入 recipe_embedding.embedding_model 列，检索/回填按其过滤（GAP-4）；
        - embed 逐条 L2 归一化，保证「点积即余弦」；
        - 请求携带 dimensions=1024，与 vector(1024) 列严格对齐（维度不符立即抛错）；
        - 查询文本经模块级 LRU 缓存（_cache_get/_cache_put），预热实例与工厂单例共享。
    """

    def __init__(self) -> None:
        """构造函数：装配 OpenAI 兼容客户端（函数）。

        说明：
            EMBEDDING_API_BASE/EMBEDDING_API_KEY 缺省回落 VISION_BASE_URL/VISION_API_KEY；
            两者拼接后仍为空则视为配置缺失，直接抛 EmbeddingUnavailableError
            （工厂捕获后回落 hash 提供方）。

        参数：
            无。

        返回值：
            None。

        异常：
            EmbeddingUnavailableError：API BASE 与 API KEY 均为空（配置缺失）。
        """
        base_url = settings.EMBEDDING_API_BASE.strip() or settings.VISION_BASE_URL.strip()
        api_key = settings.EMBEDDING_API_KEY.strip() or settings.VISION_API_KEY.strip()
        if not base_url or not api_key:
            raise EmbeddingUnavailableError(
                "百炼嵌入配置缺失：EMBEDDING_API_BASE/KEY 与 VISION_BASE_URL/KEY 均为空"
            )
        self._client = openai.OpenAI(
            base_url=base_url, api_key=api_key, timeout=settings.EMBEDDING_TIMEOUT_SECONDS
        )
        # 单批请求文本条数上限（max(1,..) 防止错误配置出 0 导致 range 异常）
        self._batch = max(1, int(settings.EMBEDDING_BATCH_SIZE))
        # 嵌入空间标识：同值写入 embedding_model 列并作为嵌入请求的 model 参数
        self.space_name = settings.EMBEDDING_MODEL_NAME.strip() or "qwen3.7-text-embedding"

    def embed(self, texts: list[str]) -> list[list[float]]:
        """批量远程嵌入（函数，LRU 缓存 + 分批请求 + L2 归一化）。

        说明：
            缓存键 = 空间名 + 归一化空白后的文本（' '.join(t.split())），
            命中的条目不重复请求；未命中者去重后按 EMBEDDING_BATCH_SIZE 分批
            调用 OpenAI 兼容 embeddings 接口（dimensions=1024），响应按 index
            对齐回原输入顺序；任何网络/超时/鉴权异常统一包装为
            EmbeddingUnavailableError（缓存命中部分不受影响）。

        参数：
            texts：待嵌入文本列表（可为空列表）。

        返回值：
            list[list[float]]：与 texts 等长、顺序一致的 1024 维 L2 归一化向量列表。

        异常：
            EmbeddingUnavailableError：百炼调用失败（网络/超时/鉴权）或返回维度 != 1024。
        """
        if not texts:
            return []
        # 逐条查缓存：命中直接取用；未命中的按「空间名\x00归一化文本」去重收集
        results: list[list[float] | None] = [None] * len(texts)
        miss_keys: list[str] = []   # 未命中条目的缓存键（保序、去重）
        for idx, item in enumerate(texts):
            key = f"{self.space_name}\x00{' '.join(item.split())}"
            cached = _cache_get(key)
            if cached is not None:
                results[idx] = cached
            elif key not in miss_keys:
                miss_keys.append(key)
        if miss_keys:
            try:
                fetched: dict[str, list[float]] = {}  # 缓存键 → 归一化向量
                # 分批请求：每批 ≤ EMBEDDING_BATCH_SIZE 条（防单请求超限）
                for start in range(0, len(miss_keys), self._batch):
                    batch_keys = miss_keys[start : start + self._batch]
                    # 缓存键含 '\x00' 分隔符，取其后的归一化文本作为请求 input
                    batch_texts = [key.split("\x00", 1)[1] for key in batch_keys]
                    resp = self._client.embeddings.create(
                        model=self.space_name,
                        input=batch_texts,
                        dimensions=1024,
                        encoding_format="float",
                    )
                    # 响应 data 顺序不保证与输入一致，按 index 对齐回本批文本
                    for item in sorted(resp.data, key=lambda d: d.index):
                        vec = [float(x) for x in item.embedding]
                        if len(vec) != 1024:
                            # 防错维度向量写库（与 vector(1024) 列不对齐即失败）
                            raise EmbeddingUnavailableError(
                                f"百炼嵌入返回维度 {len(vec)} != 1024，拒绝写库"
                            )
                        # L2 归一化：保证「点积即余弦」
                        norm = math.sqrt(sum(x * x for x in vec))
                        if norm > 0:
                            vec = [x / norm for x in vec]
                        fetched[batch_keys[item.index]] = vec
                for key in miss_keys:
                    vec = fetched.get(key)
                    if vec is None:
                        # 服务端必须回满输入条数，缺失视为不可用（防御性兜底）
                        raise EmbeddingUnavailableError(
                            f"百炼嵌入响应缺失条目: {key.split(chr(0), 1)[-1][:50]}"
                        )
                    _cache_put(key, vec)
                # 按原输入顺序组装返回（缓存命中与本次请求合并）
                for idx, item in enumerate(texts):
                    if results[idx] is None:
                        key = f"{self.space_name}\x00{' '.join(item.split())}"
                        results[idx] = fetched[key]
            except EmbeddingUnavailableError:
                raise
            except Exception as exc:  # noqa: BLE001 —— 网络等异常统一包装为不可用
                raise EmbeddingUnavailableError(f"百炼嵌入调用失败: {exc}") from exc
        return [vec for vec in results if vec is not None]


def get_embedding_provider() -> EmbeddingProvider:
    """嵌入提供方工厂（函数，进程内单例）。

    说明：
        读取 settings.EMBEDDING_PROVIDER（取值 'hash'（缺省）| 'bailian' | 'bgem3'）：
        - 'bailian'：构造 BailianEmbeddingProvider，失败（配置缺失等）记 WARNING
          回落 HashEmbeddingProvider，保证检索主链路不因远程配置问题中断；
        - 'bgem3'：BGEM3Provider 阶段二占位，实例化即抛 NotImplementedError 原样向上；
        回填与查询必须共享同一嵌入空间，故进程内缓存单例。

    返回值：
        EmbeddingProvider：嵌入提供方实例。

    异常：
        NotImplementedError：EMBEDDING_PROVIDER=bgem3 且阶段二未启用时向上抛出
        （检索路径内已捕获降级，不影响接口 200）。
    """
    global _PROVIDER_SINGLETON
    if _PROVIDER_SINGLETON is not None:
        return _PROVIDER_SINGLETON
    with _PROVIDER_LOCK:
        if _PROVIDER_SINGLETON is not None:
            return _PROVIDER_SINGLETON
        name = settings.EMBEDDING_PROVIDER.strip().lower()
        provider: EmbeddingProvider
        if name == "bgem3":
            provider = BGEM3Provider()  # 阶段二占位：NotImplementedError 原样向上抛
        elif name == "bailian":
            try:
                provider = BailianEmbeddingProvider()
            except Exception as exc:  # noqa: BLE001 —— 百炼配置缺失/异常回落 hash
                logger.warning("bailian provider init failed, fallback to hash: %s", exc)
                provider = HashEmbeddingProvider()
        else:
            provider = HashEmbeddingProvider()  # 缺省（含 'hash'）
        _PROVIDER_SINGLETON = provider
        return provider


def probe_pgvector(db_engine=engine) -> bool:
    """探测 pgvector 是否可用于 raw SQL 向量检索（函数，模块级缓存）。

    说明：
        双重探测（缺一即 False）：① pg_extension 存在 'vector' 扩展；
        ② information_schema 中 recipe_embedding 表存在 'embedding' 列
        （向量列仅由迁移 b8d3f5a21c60 在扩展可用时创建，不进 ORM）。
        结果缓存于模块级变量——迁移安装扩展后需重启进程生效。

    参数：
        db_engine：SQLAlchemy Engine（默认 app.core.db.engine）。

    返回值：
        bool：扩展与向量列均就绪返回 True；否则 False（探测异常同样降级为 False）。

    异常：
        不抛出（数据库异常捕获后返回 False）。
    """
    global _probe_cache
    if _probe_cache is not None:
        return _probe_cache
    with _probe_lock:
        if _probe_cache is not None:
            return _probe_cache
        try:
            with db_engine.connect() as conn:
                has_ext = conn.execute(
                    text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
                ).first() is not None
                has_column = conn.execute(
                    text(
                        "SELECT 1 FROM information_schema.columns "
                        "WHERE table_name = 'recipe_embedding' AND column_name = 'embedding'"
                    )
                ).first() is not None
                _probe_cache = bool(has_ext and has_column)
        except Exception as exc:  # noqa: BLE001 —— 探测失败按无 pgvector 降级
            logger.warning("probe pgvector failed, fallback to json dot-product: %s", exc)
            _probe_cache = False
    return _probe_cache


def _recipe_embed_text(session: Session, recipe_id: int, title: str) -> str:
    """组装菜谱的嵌入源文本（函数）。

    说明：
        文本 = 菜名 + 主料/辅料食材名（排除调味料，避免「盐/生抽」稀释语义）。

    参数：
        session：数据库会话。
        recipe_id：菜谱 ID。
        title：菜谱名称。

    返回值：
        str：拼接后的嵌入文本。

    异常：
        查询异常向上抛出（由调用方统一捕获）。
    """
    rows = session.execute(
        select(Ingredient.name)
        .join(RecipeIngredient, RecipeIngredient.ingredient_id == Ingredient.id)
        .where(RecipeIngredient.recipe_id == recipe_id)
        .where(RecipeIngredient.amount_type != "seasoning")
    ).scalars().all()
    return f"{title} {' '.join(rows)}".strip()


def ensure_embeddings(
    session: Session, provider: EmbeddingProvider | None = None, *, space_name: str | None = None
) -> int:
    """为全部已发布官方菜谱回填向量（幂等，函数）。

    说明：
        目标集 = recipe.status='published' 的菜谱；为每个尚无「目标嵌入空间」
        verified 向量行的菜谱生成 1024 维向量，写入 recipe_embedding（source='verified'，
        embedding_json 便携列，embedding_model=目标空间；pgvector 可用时经 raw SQL
        同步双写向量列）。幂等：已存在目标空间 verified 行（按 recipe_id 判定）
        的菜谱跳过，重复调用不增行；模型升级后旧空间行不被复用、不冲突（GAP-4）。

    参数：
        session：数据库会话（写入并 commit）。
        provider：嵌入提供方；None 时用 get_embedding_provider() 单例。
        space_name：目标嵌入空间标识；None 时取 provider.space_name
          （供 CLI --model 显式覆盖，如指定旧空间补数）。

    返回值：
        int：本次新回填的向量行数（0 表示无可回填项）。

    异常：
        不抛出（任何失败记 WARNING 并返回已写入计数，绝不阻断检索主链路）。
    """
    written = 0
    try:
        if provider is None:
            provider = get_embedding_provider()
        space = space_name or provider.space_name  # 目标嵌入空间（GAP-4：按空间过滤与写入）
        published = session.execute(
            select(Recipe.id, Recipe.title).where(Recipe.status == "published")
        ).all()
        existing = {
            int(rid)
            for (rid,) in session.execute(
                select(RecipeEmbedding.recipe_id)
                .where(RecipeEmbedding.source == "verified")
                .where(RecipeEmbedding.embedding_model == space)
                .where(RecipeEmbedding.recipe_id.is_not(None))
            ).all()
        }
        targets = [(int(rid), title) for rid, title in published if int(rid) not in existing]
        if not targets:
            return 0

        texts = [_recipe_embed_text(session, rid, title) for rid, title in targets]
        vectors = provider.embed(texts)
        use_pgvector = probe_pgvector(engine)

        new_rows: list[tuple[RecipeEmbedding, list[float]]] = []
        for (rid, _title), vec in zip(targets, vectors, strict=True):
            row = RecipeEmbedding(
                recipe_id=rid, source="verified", embedding_json=vec, embedding_model=space
            )
            session.add(row)
            new_rows.append((row, vec))
        session.flush()

        # pgvector 可用时双写向量列（ORM 不映射该列，仅 raw SQL 访问）
        if use_pgvector and new_rows:
            session.execute(
                text("UPDATE recipe_embedding SET embedding = CAST(:v AS vector) WHERE id = :id"),
                [{"v": _to_vector_literal(vec), "id": int(row.id)} for row, vec in new_rows],
            )
        session.commit()
        written = len(new_rows)
        logger.info("ensure_embeddings backfilled %s verified vectors", written)
        return written
    except Exception as exc:  # noqa: BLE001 —— 回填失败不阻断检索（惰性下次重试）
        logger.warning("ensure_embeddings failed: %s", exc)
        try:
            session.rollback()
        except Exception:  # noqa: BLE001
            pass
        return written


def lazy_backfill(session: Session) -> None:
    """verified 向量缺失时的惰性回填入口（函数，进程锁防并发重复）。

    说明：
        触发条件：use_vector 检索发现「当前嵌入空间（provider.space_name）」的
        verified 向量计数为 0 且存在 published 菜谱；持锁后双重检查计数，
        避免并发重复回填。计数按 embedding_model 过滤——旧空间残留行不阻断
        新空间回填（GAP-4）。

    参数：
        session：数据库会话（复用检索会话写入）。

    返回值：
        None。

    异常：
        不抛出（失败记 WARNING，检索继续走既有关键词路径）。
    """
    try:
        provider = get_embedding_provider()  # 当前嵌入空间唯一来源（进程单例）
        verified_count = session.execute(
            select(func.count()).select_from(RecipeEmbedding)
            .where(RecipeEmbedding.source == "verified")
            .where(RecipeEmbedding.embedding_model == provider.space_name)
        ).scalar()
        if verified_count:
            return
        published_count = session.execute(
            select(func.count()).select_from(Recipe).where(Recipe.status == "published")
        ).scalar()
        if not published_count:
            return
        if _BACKFILL_LOCK.locked():
            return  # 其他线程正在回填，本次跳过（不阻塞检索）
        with _BACKFILL_LOCK:
            verified_count = session.execute(
                select(func.count()).select_from(RecipeEmbedding)
                .where(RecipeEmbedding.source == "verified")
                .where(RecipeEmbedding.embedding_model == provider.space_name)
            ).scalar()
            if verified_count:
                return
            ensure_embeddings(session, provider)
    except Exception as exc:  # noqa: BLE001 —— 回填失败降级，检索主链路不受影响
        logger.warning("lazy embedding backfill failed: %s", exc)


def upsert_embedding(
    session: Session,
    recipe_id: int | None = None,
    owner_user_id: int | None = None,
    source: str = "verified",
    provider: EmbeddingProvider | None = None,
    innovation_recipe_id: int | None = None,
    embed_text: str | None = None,
) -> int:
    """单条向量 upsert（函数，供创新链路 T7 调用）。

    说明：
        - source='verified'：按 recipe_id 幂等（已存在 verified 行则更新向量）；
        - source='ai_private'：owner_user_id 与 innovation_recipe_id 必填
          （表 CHECK 红线），按 innovation_recipe_id 幂等；
        - 向量源文本：embed_text 显式传入优先；否则 verified 行取「菜名+食材」、
          ai_private 行取创新菜名称；
        - pgvector 可用时同步双写向量列；写入即 commit。

    参数：
        session：数据库会话。
        recipe_id：菜谱 ID（verified 必填；ai_private 可空）。
        owner_user_id：归属用户 ID（ai_private 必填）。
        source：向量行来源（'verified' | 'ai_private'）。
        provider：嵌入提供方；None 时用进程单例。
        innovation_recipe_id：创新菜 ID（ai_private 必填，供 T7 传入）。
        embed_text：显式嵌入文本（如创新菜「名称+食材」拼接）；None 时自动组装。

    返回值：
        int：写入/更新的 recipe_embedding 行 id。

    异常：
        ValueError：source='ai_private' 缺 owner_user_id/innovation_recipe_id，
        或 recipe_id/innovation_recipe_id 均未提供且无 embed_text。
    """
    if provider is None:
        provider = get_embedding_provider()
    if source == "ai_private" and (owner_user_id is None or innovation_recipe_id is None):
        raise ValueError("source='ai_private' 的向量行必须携带 owner_user_id 与 innovation_recipe_id")

    if embed_text is None:
        if recipe_id is not None:
            title = session.execute(
                select(Recipe.title).where(Recipe.id == recipe_id)
            ).scalar_one_or_none() or ""
            embed_text = _recipe_embed_text(session, int(recipe_id), title)
        elif innovation_recipe_id is not None:
            from app.models import InnovationRecipe  # 局部导入：创新域模型按需加载

            embed_text = session.execute(
                select(InnovationRecipe.name).where(InnovationRecipe.id == innovation_recipe_id)
            ).scalar_one_or_none() or ""
        else:
            raise ValueError("recipe_id / innovation_recipe_id 至少提供一个（或显式传入 embed_text）")

    vec = provider.embed([embed_text])[0]

    row: RecipeEmbedding | None = None
    if source == "verified" and recipe_id is not None:
        row = session.execute(
            select(RecipeEmbedding)
            .where(RecipeEmbedding.source == "verified")
            .where(RecipeEmbedding.recipe_id == recipe_id)
        ).scalar_one_or_none()
    elif source == "ai_private" and innovation_recipe_id is not None:
        row = session.execute(
            select(RecipeEmbedding)
            .where(RecipeEmbedding.source == "ai_private")
            .where(RecipeEmbedding.innovation_recipe_id == innovation_recipe_id)
        ).scalar_one_or_none()

    if row is None:
        row = RecipeEmbedding(
            recipe_id=recipe_id,
            owner_user_id=owner_user_id,
            innovation_recipe_id=innovation_recipe_id,
            source=source,
            embedding_json=vec,
            embedding_model=provider.space_name,  # 写入当前嵌入空间标识（GAP-4）
        )
        session.add(row)
        session.flush()
    else:
        row.embedding_json = vec
        # 向量重算即随当前嵌入空间（模型升级后旧行重算归属新空间，GAP-4）
        row.embedding_model = provider.space_name
        session.flush()

    # pgvector 可用时双写向量列（ORM 不映射该列，仅 raw SQL 访问）
    if probe_pgvector(engine):
        session.execute(
            text("UPDATE recipe_embedding SET embedding = CAST(:v AS vector) WHERE id = :id"),
            {"v": _to_vector_literal(vec), "id": int(row.id)},
        )
    session.commit()
    return int(row.id)
