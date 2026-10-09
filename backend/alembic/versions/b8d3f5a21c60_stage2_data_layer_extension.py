"""stage2 data layer extension

Revision ID: b8d3f5a21c60
Revises: 3740c6411c8a
Create Date: 2026-10-09

说明：
    阶段二数据层扩展迁移（Task 1）：
    1. favorite_recipe 收藏表（软删 + partial unique index）；
    2. user.preferences JSONB 用户偏好列（字号/单位/提醒/语音开关）；
    3. 模块 O 四表：ingredient_property / flavor_pairing_rule / technique_library /
       innovation_recipe（AI 菜品创新）；
    4. recipe_embedding 升级：
       - pgvector 容错策略：CREATE EXTENSION vector 以 SAVEPOINT 包裹，
         扩展不可用时跳过向量列与 ivfflat 索引并打 WARNING，迁移绝不失败；
       - 原 embedding JSONB 占位列重命名为 embedding_json（1024 维浮点数组的
         便携存储，SQLite 测试与无扩展环境用）；
       - 主键由 recipe_id 改造为独立 id（BIGINT IDENTITY）：AI 私有向量行
         （source='ai_private'）无对应 recipe 行，recipe_id 改为可空外键；
       - 新增 owner_user_id / innovation_recipe_id / source 列与
         source 枚举、ai_private→owner 非空一致性 CHECK；
       - 扩展可用时加 embedding vector(1024) 列 + ivfflat(vector_cosine_ops,
         lists=100) 索引；向量列不进 ORM，检索层以 raw SQL 访问。

    downgrade 全量反向回滚：不留任何新表/新列/新索引/新约束残留。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b8d3f5a21c60'
down_revision: Union[str, Sequence[str], None] = '3740c6411c8a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _ensure_pgvector() -> bool:
    """确保 pgvector 扩展就绪（函数）。

    说明：
        向量列 embedding vector(1024) 依赖 pgvector 扩展。本函数按
        「已装 → 直接可用；可安装 → SAVEPOINT 包裹执行 CREATE EXTENSION
        （失败仅回滚 savepoint，不中止外层迁移事务）；不可安装 → False」
        三级探测，保证任何环境下迁移都不因向量扩展失败。

    返回值：
        bool：pgvector 就绪返回 True；不可用返回 False（跳过向量列与 ivfflat 索引）。

    异常：
        无（所有失败路径均被捕获降级为 False）。
    """
    conn = op.get_bind()
    # 已安装：直接可用
    already = conn.execute(
        sa.text("SELECT count(*) FROM pg_extension WHERE extname = 'vector'")
    ).scalar()
    if already:
        return True
    # 环境未提供 vector 扩展（contrib 包未安装）：直接降级
    installable = conn.execute(
        sa.text("SELECT count(*) FROM pg_available_extensions WHERE name = 'vector'")
    ).scalar()
    if not installable:
        print("[migration][WARNING] pgvector 扩展不可用（未安装 vector 包），"
              "跳过 embedding vector(1024) 列与 ivfflat 索引；"
              "向量便携存储 embedding_json(JSONB) 与表结构不受影响。")
        return False
    # 可安装：SAVEPOINT 包裹执行，CREATE EXTENSION 失败（权限/版本不匹配等）
    # 仅回滚到 savepoint，外层迁移事务保持健康——绝不让迁移失败
    try:
        with conn.begin_nested():
            conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
        return True
    except Exception as exc:  # noqa: BLE001 —— 扩展安装失败必须降级而非中断迁移
        print(f"[migration][WARNING] pgvector 扩展安装失败（{exc}），"
              "跳过 embedding vector(1024) 列与 ivfflat 索引。")
        return False


def _has_vector_column() -> bool:
    """探测 recipe_embedding 表是否存在 embedding vector 列（函数）。

    返回值：
        bool：存在返回 True（此时必为 pgvector 向量列），否则 False。

    异常：
        数据库查询异常向上抛出（downgrade 阶段应保持库可达）。
    """
    conn = op.get_bind()
    data_type = conn.execute(sa.text(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_name = 'recipe_embedding' AND column_name = 'embedding'"
    )).scalar()
    return data_type is not None and data_type != 'jsonb'


def upgrade() -> None:
    """升级到阶段二数据层结构（函数）。

    执行顺序：
        favorite_recipe → user.preferences → technique_library →
        ingredient_property → flavor_pairing_rule → innovation_recipe →
        recipe_embedding 升级（依赖 innovation_recipe，最后处理）。

    异常：
        数据库 DDL 失败时向上抛出（alembic 整体回滚，事务性 DDL 保证不留半成品）。
    """
    # ------------------------------------------------------------------
    # 1. favorite_recipe 收藏表（软删：partial unique index 保证未删行唯一）
    # ------------------------------------------------------------------
    op.create_table(
        'favorite_recipe',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('recipe_id', sa.BigInteger(), nullable=False),
        sa.Column('group_name', sa.String(length=64),
                  server_default='默认分组', nullable=False),
        sa.Column('note', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'],
                                name='fk_favorite_recipe_user_id_user', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['recipe_id'], ['recipe.id'],
                                name='fk_favorite_recipe_recipe_id_recipe', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='pk_favorite_recipe'),
    )
    # 软删语义：仅对未删除行保证 (user_id, recipe_id) 唯一（删除后可重新收藏）
    op.create_index(
        'uq_favorite_user_recipe', 'favorite_recipe',
        ['user_id', 'recipe_id'], unique=True,
        postgresql_where=sa.text('deleted_at IS NULL'),
    )

    # ------------------------------------------------------------------
    # 2. user.preferences 用户偏好列（字号/单位/提醒/语音开关等 JSONB）
    # ------------------------------------------------------------------
    op.add_column(
        'user',
        sa.Column('preferences', postgresql.JSONB(astext_type=sa.Text()),
                  server_default='{}', nullable=True),
    )

    # ------------------------------------------------------------------
    # 3. technique_library 技法白名单库（模块 O 创新技法校验依据）
    # ------------------------------------------------------------------
    op.create_table(
        'technique_library',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=False),
        sa.Column('in_whitelist', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_technique_library'),
        sa.UniqueConstraint('name', name='uq_technique_library_name'),
    )

    # ------------------------------------------------------------------
    # 4. ingredient_property 食材质地/含水量/风味/耐热/吸油 五属性表
    # ------------------------------------------------------------------
    op.create_table(
        'ingredient_property',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('ingredient_id', sa.BigInteger(), nullable=False),
        sa.Column('texture', sa.String(length=32), nullable=True),
        sa.Column('moisture', sa.String(length=16), nullable=True),
        sa.Column('flavor', sa.String(length=64), nullable=True),
        sa.Column('heat_tolerance', sa.String(length=16), nullable=True),
        sa.Column('oil_absorption', sa.String(length=16), nullable=True),
        sa.Column('source_note', sa.String(length=255),
                  server_default='启发式标注，需专家复核', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['ingredient_id'], ['ingredient.id'],
                                name='fk_ingredient_property_ingredient_id_ingredient',
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='pk_ingredient_property'),
        sa.UniqueConstraint('ingredient_id', name='uq_ingredient_property_ingredient_id'),
    )

    # ------------------------------------------------------------------
    # 5. flavor_pairing_rule 食材风味搭配规则表（recommend/conflict/taboo）
    # ------------------------------------------------------------------
    op.create_table(
        'flavor_pairing_rule',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('ingredient_a_id', sa.BigInteger(), nullable=False),
        sa.Column('ingredient_b_id', sa.BigInteger(), nullable=False),
        sa.Column('relation', sa.String(length=16), nullable=False),
        sa.Column('technique_suggestion', sa.String(length=128), nullable=True),
        sa.Column('rationale', sa.String(length=255), nullable=False),
        sa.Column('weight', sa.Numeric(precision=4, scale=2),
                  server_default='1.0', nullable=False),
        sa.Column('signed_by_expert', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("relation IN ('recommend','conflict','taboo')",
                           name='chk_relation'),
        sa.ForeignKeyConstraint(['ingredient_a_id'], ['ingredient.id'],
                                name='fk_flavor_pairing_rule_ingredient_a_id_ingredient',
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['ingredient_b_id'], ['ingredient.id'],
                                name='fk_flavor_pairing_rule_ingredient_b_id_ingredient',
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='pk_flavor_pairing_rule'),
        sa.UniqueConstraint('ingredient_a_id', 'ingredient_b_id', 'relation',
                            name='uq_pairing_a_b_relation'),
    )

    # ------------------------------------------------------------------
    # 6. innovation_recipe AI 创新菜表（模块 O）
    # ------------------------------------------------------------------
    op.create_table(
        'innovation_recipe',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('ingredients', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('steps', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('nutrition', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('basis', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('status', sa.String(length=16),
                  server_default='generated', nullable=False),
        sa.Column('is_ai_innovated', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('visibility', sa.String(length=16),
                  server_default='private', nullable=False),
        sa.Column('source_pairing_rule_ids',
                  postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('rating', sa.SmallInteger(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("status IN ('generated','adopted','indexed','removed')",
                           name='chk_status'),
        sa.CheckConstraint("visibility IN ('private')",
                           name='chk_visibility'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'],
                                name='fk_innovation_recipe_user_id_user', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='pk_innovation_recipe'),
    )
    op.create_index('idx_innovation_user', 'innovation_recipe', ['user_id', 'status'],
                    unique=False)

    # ------------------------------------------------------------------
    # 7. recipe_embedding 升级（pgvector 容错 + 主键改造 + 溯源列）
    # ------------------------------------------------------------------
    vector_ready = _ensure_pgvector()

    # 7.1 原 embedding JSONB 占位列重命名为 embedding_json（便携存储，语义升级）
    op.alter_column('recipe_embedding', 'embedding',
                    new_column_name='embedding_json',
                    existing_type=postgresql.JSONB(astext_type=sa.Text()),
                    existing_nullable=True)

    # 7.2 主键改造：recipe_id（PK, NOT NULL）→ 独立 id。
    #     理由：source='ai_private' 的 AI 私有向量行无对应 recipe 行
    #     （创新菜存于 innovation_recipe），recipe_id 必须可空，
    #     原「recipe_id 即主键」结构无法承载该类行。
    op.drop_constraint('pk_recipe_embedding', 'recipe_embedding', type_='primary')
    # IDENTITY 列：ALTER ADD COLUMN 场景下由 PG 自动生成序号，等价 BIGSERIAL 语义
    op.add_column('recipe_embedding',
                  sa.Column('id', sa.BigInteger(), sa.Identity(always=False),
                            nullable=False))
    op.alter_column('recipe_embedding', 'recipe_id',
                    existing_type=sa.BigInteger(), nullable=True)
    op.create_primary_key('pk_recipe_embedding', 'recipe_embedding', ['id'])
    # recipe_id 不再由 PK 索引覆盖，补常规索引（verified 菜谱向量检索主路径）
    op.create_index('idx_emb_recipe', 'recipe_embedding', ['recipe_id'], unique=False)

    # 7.3 溯源列：owner_user_id（AI 私有归属）/ innovation_recipe_id（来源创新菜）/ source
    op.add_column('recipe_embedding',
                  sa.Column('owner_user_id', sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        'fk_recipe_embedding_owner_user_id_user',
        'recipe_embedding', 'user', ['owner_user_id'], ['id'],
        ondelete='CASCADE',
    )
    op.add_column('recipe_embedding',
                  sa.Column('innovation_recipe_id', sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        'fk_recipe_embedding_innovation_recipe_id_innovation_recipe',
        'recipe_embedding', 'innovation_recipe', ['innovation_recipe_id'], ['id'],
        ondelete='CASCADE',
    )
    op.add_column('recipe_embedding',
                  sa.Column('source', sa.String(length=16),
                            server_default='verified', nullable=False))

    # 7.4 一致性 CHECK：source 枚举 + ai_private 行必须归属用户
    # （name 传短名，由 naming convention 生成 ck_recipe_embedding_chk_source 等最终名，
    #   与 ORM create_all 命名保持一致）
    op.create_check_constraint(
        'chk_source', 'recipe_embedding',
        "source IN ('verified','ai_private')",
    )
    op.create_check_constraint(
        'chk_ai_owner', 'recipe_embedding',
        "source <> 'ai_private' OR owner_user_id IS NOT NULL",
    )

    # 7.5 常规索引：来源/归属过滤维度
    op.create_index('idx_emb_source', 'recipe_embedding', ['source'], unique=False)
    op.create_index('idx_emb_owner', 'recipe_embedding', ['owner_user_id'], unique=False)
    op.create_index('idx_emb_innovation', 'recipe_embedding', ['innovation_recipe_id'],
                    unique=False)

    # 7.6 pgvector 就绪时：真实向量列 + ivfflat 余弦索引（lists=100）
    if vector_ready:
        from pgvector.sqlalchemy import Vector  # 局部导入：包缺失不影响其余迁移逻辑

        op.add_column('recipe_embedding',
                      sa.Column('embedding', Vector(1024), nullable=True))
        # ivfflat 的 ops/参数语法 alembic create_index 支持有限，手写 DDL 最可靠
        op.execute(
            "CREATE INDEX idx_emb_vector ON recipe_embedding "
            "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
        )


def downgrade() -> None:
    """回滚阶段二数据层扩展（函数）。

    说明：
        全量反向回滚至 3740c6411c8a：向量列/索引按存在性条件删除
        （pgvector 可能升级时装有、回滚时已卸载），其余新表/新列/新约束
        按依赖反序 drop，不留残留。

    异常：
        数据库 DDL 失败时向上抛出。
    """
    # ------------------------------------------------------------------
    # 7. recipe_embedding 回滚（先向量，再溯源列，最后主键还原）
    # ------------------------------------------------------------------
    # 7.6r 向量列与 ivfflat 索引：存在才删（跨扩展环境安全）
    if _has_vector_column():
        conn = op.get_bind()
        has_vec_idx = conn.execute(sa.text(
            "SELECT count(*) FROM pg_indexes "
            "WHERE indexname = 'idx_emb_vector'"
        )).scalar()
        if has_vec_idx:
            op.execute("DROP INDEX IF EXISTS idx_emb_vector")
        op.drop_column('recipe_embedding', 'embedding')

    # 7.5r 常规索引
    op.drop_index('idx_emb_innovation', table_name='recipe_embedding')
    op.drop_index('idx_emb_owner', table_name='recipe_embedding')
    op.drop_index('idx_emb_source', table_name='recipe_embedding')
    op.drop_index('idx_emb_recipe', table_name='recipe_embedding')

    # 7.4r 一致性 CHECK：按后缀匹配实际约束名后删除（兼容历史双层命名残留）
    _conn = op.get_bind()
    for _suffix in ("chk_ai_owner", "chk_source"):
        _rows = _conn.execute(sa.text(
            "SELECT conname FROM pg_constraint "
            "WHERE conrelid = 'recipe_embedding'::regclass AND contype = 'c' "
            "AND conname LIKE :pat"
        ), {"pat": f"%{_suffix}"}).fetchall()
        for (conname,) in _rows:
            op.execute(f'ALTER TABLE recipe_embedding DROP CONSTRAINT "{conname}"')

    # 7.3r 溯源列（列级联删除其 FK 约束）
    op.drop_column('recipe_embedding', 'source')
    op.drop_column('recipe_embedding', 'innovation_recipe_id')
    op.drop_column('recipe_embedding', 'owner_user_id')

    # 7.2r 主键还原：id → recipe_id
    op.drop_constraint('pk_recipe_embedding', 'recipe_embedding', type_='primary')
    op.drop_column('recipe_embedding', 'id')
    op.alter_column('recipe_embedding', 'recipe_id',
                    existing_type=sa.BigInteger(), nullable=False)
    op.create_primary_key('pk_recipe_embedding', 'recipe_embedding', ['recipe_id'])

    # 7.1r 列名还原：embedding_json → embedding
    op.alter_column('recipe_embedding', 'embedding_json',
                    new_column_name='embedding',
                    existing_type=postgresql.JSONB(astext_type=sa.Text()),
                    existing_nullable=True)

    # ------------------------------------------------------------------
    # 6. innovation_recipe
    # ------------------------------------------------------------------
    op.drop_index('idx_innovation_user', table_name='innovation_recipe')
    op.drop_table('innovation_recipe')

    # ------------------------------------------------------------------
    # 5~3. flavor_pairing_rule / ingredient_property / technique_library
    # ------------------------------------------------------------------
    op.drop_table('flavor_pairing_rule')
    op.drop_table('ingredient_property')
    op.drop_table('technique_library')

    # ------------------------------------------------------------------
    # 2. user.preferences
    # ------------------------------------------------------------------
    op.drop_column('user', 'preferences')

    # ------------------------------------------------------------------
    # 1. favorite_recipe
    # ------------------------------------------------------------------
    op.drop_index('uq_favorite_user_recipe', table_name='favorite_recipe')
    op.drop_table('favorite_recipe')
