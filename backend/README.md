# AI 厨娘・智能烹饪助手 — 后端（阶段一 PoC）

FastAPI + LangGraph + PostgreSQL 后端。核心链路：**风控一票否决（11 类高危样本 100% 拦截）→ 受限问答 / 推荐编排 → 输出侧敏感词兜底**，全部服务端本地实现，不依赖外部模型即可完整演示（LLM 不可用时自动降级确定性路径）。

## 1. 目录结构

```
backend/
├── .env / .env.example        # 环境配置（数据库连接、LLM Key、EMBEDDING_MODE 等）
├── requirements.txt           # 固定版本依赖（含 ruff / pytest-cov）
├── ruff.toml                  # ruff 规则配置（E/F/W/I/B/UP，line-length 120）
├── alembic.ini / alembic/     # Alembic 迁移（initial revision：28 张业务表 + recipe_embedding 预留表）
├── app/
│   ├── main.py                # FastAPI 入口（CORS / request_id / 健康检查三路由 / 统一错误）
│   ├── core/                  # config（pydantic-settings）/ db / logging / idempotency / migrations（Alembic 程序化入口）
│   ├── models/                # SQLAlchemy 2.0 ORM：28 张业务表 + recipe_embedding 预留
│   ├── seed/                  # 幂等种子：ingredients / recipes / corpus_howtocook（HowToCook 语料）/ safety / configs
│   ├── api/v1/                # /v1 路由：ask+search / recommend / recipes / ingredients / cooking / trace / config / auth / consent
│   ├── safety/                # 风控引擎（DB 规则 + 内存注入规则）/ 敏感词兜底 / 风控日志
│   ├── ability/               # 检索 / 硬过滤 / 排序 / 营养估算 / LLM 客户端
│   ├── graph/                 # LangGraph 编排（supervisor / guards / qa / compose / finalize）
│   └── schemas/               # Pydantic v2 请求/响应模型
└── tests/                     # pytest（74 条：风控 / 硬过滤 / 排序 / 营养 / API 集成 / 质量补强）
```

## 2. 环境准备

Python 3.13（项目 `.venv` 已就绪；全新环境按以下步骤）：

```powershell
cd d:\Code_Work\AI_Cook\backend
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
```

复制 `.env.example` 为 `.env` 并填写真实值。当前开发环境配置：

- PostgreSQL：`localhost:5432`，用户 `postgres`，库 `aicook`
- LLM：OpenAI 兼容协议（DeepSeek）；不可达时主链路自动降级（D7 红线）

## 3. 数据库与 Alembic 迁移

**表结构统一由 Alembic 管理（02-V1.1 §10.1「禁止手工改表」），`create_all` 已废弃。**

日常初始化（推荐，一条命令完成「迁移 + 数据填充」）：

```powershell
.venv\Scripts\python.exe -m app.seed
```

`app.seed` 内部先调用 `app.core.migrations.ensure_schema()` 做分支决策（幂等，可重复执行）：

| 库状态 | 判定 | 动作 |
| --- | --- | --- |
| 已有 `alembic_version` 表 | 已被 Alembic 纳管 | `upgrade head`（落后则推进，已在 head 为 no-op） |
| 无版本表、但业务表已存在 | 历史 `create_all` 存量库 | `stamp head`（仅登记版本，不碰既有表与数据） |
| 空库 | 两者皆无 | `upgrade head`（一次建全 28 张业务表 + `recipe_embedding`） |

手动执行 Alembic 命令（连接串优先级：环境变量 `ALEMBIC_DATABASE_URL` > `alembic.ini` 的 `sqlalchemy.url`（默认留空）> `.env` 的 `settings.database_url`）：

```powershell
.venv\Scripts\python.exe -m alembic upgrade head          # 空库全量建表 / 推进版本
.venv\Scripts\python.exe -m alembic stamp head            # 存量库兼容登记
.venv\Scripts\python.exe -m alembic revision --autogenerate -m "描述变更"   # 修改 app/models 后生成迁移
```

**autogenerate 约定**：修改 `app/models/**` 后先 `alembic revision --autogenerate`，人工检查生成的脚本（autogenerate 不识别服务端默认值变更等边界），再 `alembic upgrade head`；禁止直接改已合入的迁移脚本。

## 4. 种子数据（幂等，来源标注）

`python -m app.seed` 依次填充（全部按存在性跳过，可重复执行）：

| 数据 | 规模 | 来源 / 说明 |
| --- | --- | --- |
| 食材 | 主数据 818 条（含别名 623、营养 356） | `app/seed/ingredients.py`；语料未命中原料自动补建 minimal 条目 |
| 菜谱 | 390 篇 published（手写 45 + 语料 345） | 手写 `app/seed/recipes.py`；语料见下行 |
| HowToCook 语料 | 345 篇（目标 ≥300） | [Anduin2017/HowToCook](https://github.com/Anduin2017/HowToCook)（Unlicense），`source_label = "HowToCook / 公开家常菜语料"`；用量全量化（区间归一化、调料「适量」按映射表量化，满足 CT-6）、自动聚合致敏原；语料缓存克隆至 `backend/data/HowToCook`，下载失败时跳过语料导入 |
| 风控规则 / 话术 | 24 条 / 24 条 | FS 食品安全 / SP 特殊人群 / MR 医疗 / PS 伪科学 / OB 输出侧 |
| 远程开关 | 5 个 | `switch.recommend / vision / qa / payment / innovation`（05-V1.1 §4.4；`innovation` 为模块 O 预留开关，仅配置不实现） |

## 5. 启动方式（一键脚本）

项目根目录的 `scripts\manage.ps1` 提供全生命周期管理（`-Action setup|start|stop|status|test|smoke`）：

```powershell
# 在项目根目录（d:\Code_Work\AI_Cook）执行：
powershell -ExecutionPolicy Bypass -File scripts\manage.ps1 -Action start          # 一键启动（缺环境自动 setup）
powershell -ExecutionPolicy Bypass -File scripts\manage.ps1 -Action start -InitDb  # 启动前先迁移建表 + seed
powershell -ExecutionPolicy Bypass -File scripts\manage.ps1 -Action status         # 查看服务状态
powershell -ExecutionPolicy Bypass -File scripts\manage.ps1 -Action smoke          # 冒烟断言（需服务运行中）
powershell -ExecutionPolicy Bypass -File scripts\manage.ps1 -Action test           # 后端 pytest + 前端 vitest
powershell -ExecutionPolicy Bypass -File scripts\manage.ps1 -Action stop           # 停止并校验端口零监听
```

Windows 下也可以直接双击 `scripts\start.bat` 一键启动；启动失败时窗口会保留，并输出后端/前端日志，便于排查。

- 后端监听 `8000`（uvicorn `app.main:app`），前端固定 `5173`（`--strictPort` 不漂移）
- `start` 就绪探测与 `status` 统一走 `GET /v1/healthz`
- `smoke`（对齐 04-V1.1 §5.7 smoke-test.sh）：healthz 200 → 一票否决短路纯净性 → 11 类高危样本拦截率 100% → 医疗拒答 → 幂等重放一致，任一失败退出码非 0

手动启动后端：

```powershell
.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 6. 健康检查（三路由同一实现）

| 端点 | 口径 |
| --- | --- |
| `GET /v1/healthz` | 标准口径（05-V1.1 §9.5/§12.3），manage.ps1 探测用 |
| `GET /healthz` | 根级口径（04-V1.1 §7，docker healthcheck 用） |
| `GET /api/health` | 既有兼容口径（保持 200/503 语义不变） |

200 → `{"status":"ok","database":"up","version":"1.0.0"}`；数据库不可达 → 503 `database=down`。API 文档：`http://127.0.0.1:8000/docs`。

## 7. 接口速查（/v1）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/v1/anonymous` | 创建/复用匿名会话 |
| POST | `/v1/disclaimer` | 免责声明同意落库 |
| POST | `/v1/ask` | 自然语言主入口（闸门 → 意图路由 → 受限问答/推荐；命中阻断返回 G-01） |
| POST | `/v1/search` | **与 `/v1/ask` 同一实现**（02-V1.1 §9.1 #15 与 05-V1.1 §3.5/§12.3 两处文档口径并存） |
| POST | `/v1/recommend` | 推荐主接口（三档结果 + rank_reasons + filtered_by） |
| GET | `/v1/recipes/{recipe_id}` | 菜谱详情（支持 servings 缩放重算） |
| GET | `/v1/recipes/{recipe_id}/nutrition` | 营养估算（缺失项标注「未纳入统计」，不按 0 计） |
| POST/GET/PATCH | `/v1/cooking/sessions(...)` | 烹饪会话：创建（过敏原冲突检查）/ 详情 / 步骤推进 / finish |
| GET | `/v1/trace/{request_id}` | Agent 调度 trace 详情（W-06 面板数据源） |
| GET | `/v1/config/switches` | 远程开关（5 个布尔值） |

## 8. 测试与质量命令

```powershell
# 全量测试（74 条，连真实本地库 aicook，需先完成 seed）
.venv\Scripts\python.exe -m pytest tests -q

# 静态检查（质量门：0 error）
.venv\Scripts\python.exe -m ruff check app

# 覆盖率（质量门：app/safety 全模块与 app/ability/ranking.py ≥80%）
.venv\Scripts\python.exe -m pytest tests -q --cov=app/safety --cov=app/ability --cov=app/core/migrations --cov-report=term-missing
```

当前指标：`app/safety` 全模块 99%~100%、`app/ability/ranking.py` 98%、`migrations.py` 84%（数字可复现；单文件 `app/core/migrations` 的 `--cov` 路径在 pytest-cov 7.1 下不生效，如需单独查看请用 `--cov=app/core`）。

## 9. 接口变更（2026-10-10 缺陷修复批次）

> 本轮缺陷修复（Wave1）共 8 条变更，逐项记录如下。口径核对以 `http://127.0.0.1:8000/docs`（OpenAPI）为准；测试覆盖见 `tests/test_innovation_degrade.py`、`tests/test_api_recipes_search.py`、`tests/test_ask_ingredient_merge.py`、`tests/test_cooking_help_topics.py`、`tests/test_performance.py`。

### 9.1 变更明细

| # | 端点 / 位置 | 变更内容 |
| --- | --- | --- |
| 1 | `POST /v1/innovation/generate` | LLM 表达阶段新增 **25s 硬超时**（`LLM_HARD_TIMEOUT_SECONDS`，前端本接口专用 60s 超时，后端必须在其内返回）；超时/异常/量化违例时降级为「规则模板表达」（配比模板量化用量 + 技法白名单 + 搭配依据拼装），响应结构完整不变。生成来源以 **`basis.generated_by`** 标注：LLM 成功 = `"llm"`、降级 = `"template"`（枚举二值）；`is_ai_innovated=true` 与 `disclaimer` 恒带不变。改动：`graph/subgraphs/innovation.py` + `api/v1/innovation.py` |
| 2 | `GET /v1/recipes?q=&page=&page_size=` | **新增菜谱搜索端点**：`q` 模糊匹配菜名 ILIKE 或「菜谱引用了名称/别名命中 q 的食材」（仅 `published`）；菜名直接命中排在食材命中前。响应 `{items:[{id,title,difficulty,time_minutes,calories_kcal}], total, page, page_size}`；`page≥1`（默认 1）、`page_size 1~50`（默认 10），非法 422 统一错误体；查询类接口豁免幂等。改动：`api/v1/recipes.py` |
| 3 | `POST /v1/ask` | **recommend 意图检索增强**：从问句中按最长匹配提取命中食材名（含别名归一，`ability/retrieval.extract_ingredient_names_from_text`）并入推荐检索入参，提升「土豆和牛肉能一起做什么」类问法的召回覆盖。响应契约不变（`intent=recommend` 仍只回 `trace_id`，前端再调 `/v1/recommend`）。改动：`ability/retrieval.py` + `graph/subgraphs/recommend.py` |
| 4 | `POST /v1/cooking/sessions/{id}/help` | 求助**子智能体**（`ability/cooking_help_agent.py`）结合当前步骤与用户档案（过敏原/口味/厨艺/饮食目标）经主 LLM 生成 2~3 条针对性建议；不可用时诚实提示「暂时不可用」（模板降级已按产品决策移除）；拦截（input/output 闸门）与限次（每会话 3 次，429）语义不变。改动：`api/v1/cooking.py`、`ability/cooking_help_agent.py` |
| 5 | `POST /v1/cooking/sessions/{id}/finish` | 新增 **completed 会话评分补录**语义：会话已完成且本次请求显式携带 `rating` → 不再 409，补写 `recipe_feedback(feedback_type='cooked', rating, tags, session_id)`；每会话至多一条 cooked 评价，**重复补录 → 409「该次烹饪已完成评价」**。无评分负载（`rating=null`）的重复 finish 仍 409，幂等语义不变。补录响应 `{session, nutrition: null, meal_record_id: null}`（完成时已落餐次/营养，不重算）。改动：`api/v1/cooking.py` |
| 6 | `POST /v1/recommend/filtered` | 后端无改动；**前端修复了重放调用**（store `fetchFilteredItems`）。重放契约：请求 `ingredients ≥1` + 可选 `allergen_codes/dietary_restrictions/difficulty_cap/equipment`；响应 `{filtered:[{recipe_id, recipe_name, reason, reasons:[{type, detail}]}], total_filtered}`，`reason` 取 `reasons` 首项 `type`（归因类型：allergen/taboo/difficulty/equipment），候选为空返回空列表 |
| 7 | `POST /v1/vision/recognize` | **免费识别额度 4→3 次/日**（`api/v1/vision.py FREE_DAILY_LIMIT=3`；会员仍 10 次/日）。响应 `quota.{used, limit, remaining}` 同步口径；额度不足 429（响应体携带 quota）。降级/低置信不扣额度红线不变 |
| 8 | `POST /v1/recommend`（排序侧） | **缺料上限**（`ability/ranking.py MAX_MISSING_INGREDIENTS=8`）：`missing` 数量 >8 的菜谱在「需要多买几样」档档内截断前整条跳过，不入结果、不占 Top 8 名额；三档结构（`can_cook_now` / `missing_1_2` / `need_more`）与 `rank_reasons` 契约不变 |

### 9.2 向后兼容性说明

- **响应均为超集或新增端点**：#1 `basis.generated_by` 为新增字段、#2 为纯新增端点、#3/#4/#8 仅服务端行为增强（响应结构不变）、#6 后端无改动——旧前端可继续运行。
- **两处行为变化需前端感知**：#5 finish 从「completed + rating 一律 409」放宽为「补录成功一次、再重复才 409」；#7 免费额度收紧为 3 次/日（前端额度文案已同步）。
- **无字段删除/改名**，无鉴权口径变化；幂等、风控一票否决、降级（D7）等既有语义全部保持。

## 10. 已知限制

1. **bge-m3 本地向量检索未引入**：保留 `EMBEDDING_MODE` 配置语义与适配器接口（`recipe_embedding` 预留表已建）；数百篇语料规模下「关键词 + 别名 + 覆盖率」混合召回满足阶段一演示，引入 2GB+ 权重与 torch 依赖收益不匹配（05-V1.1 §12.2 将其定义为可切换项）。
2. **模块 O「AI 菜品创新」不纳入阶段一**：变更单 CR-20261008-01 未签字生效（其 §五约定未生效前不得开发）；阶段一仅落地第 5 个远程开关 `switch.innovation` 的配置，不实现 subgraph / 新表 / 页面。
3. **mypy 未引入**：存量代码类型注解不全，全仓改造范围不可控；静态检查暂由 ruff（E/F/W/I/B/UP）承担，mypy 列为后续改进项。
4. **`app/ability/retrieval.py` 覆盖率 55%**：文本召回分支（ILIKE/别名匹配）暂无独立单测，整体由 API 集成测试间接覆盖；不在质量门硬指标内（硬指标为 `app/safety` 全模块与 `ranking.py`），列为后续补测项。

## 11. 15 模块接口清单摘要

> 完整契约见 `http://127.0.0.1:8000/docs`（OpenAPI）。鉴权两种口径：
> - **用户侧 `/v1/**`**：`X-Anonymous-Id` 请求头携带匿名会话 ID（`/v1/auth/anonymous` 签发）；缺失时多数端点自动 upsert 匿名用户兜底（演示友好，正式接入应显式携带）。
> - **后台 `/admin/v1/**`**：`POST /admin/v1/auth/login`（username/password）换 JWT，后续请求 `Authorization: Bearer <access_token>`；内置账号 `admin`，密码取环境变量 `ADMIN_PASSWORD`（缺省 `Admin@123456`，**演示密钥，上线前务必改密**）；JWT 密钥取 `ADMIN_JWT_SECRET`（缺省仅限本地开发）。

### 11.1 用户侧 /v1（X-Anonymous-Id）

| Tag | 方法 路径 | 说明 |
| --- | --- | --- |
| 认证与同意 | POST `/v1/auth/anonymous` | 创建/复用匿名会话 |
| 认证与同意 | POST `/v1/consent/disclaimer` | 免责声明同意落库（幂等） |
| 认证与同意 | POST `/v1/consent/sensitive` | PIPL 敏感个人信息单独同意 |
| 档案 | GET/PUT `/v1/profile/family` | 家庭档案查询（自动建档）/改名 |
| 档案 | POST `/v1/profile/members` | 新增家庭成员（过敏原三选一必选） |
| 档案 | PUT/DELETE `/v1/profile/members/{id}` | 更新（增量）/软删成员 |
| 档案 | GET/PUT `/v1/profile/skill` | 厨艺等级与设备（13 项白名单） |
| 档案 | GET/PUT `/v1/profile/diet-goal` | 饮食目标（疾病相关附加健康提示） |
| 首页 | GET `/v1/home` | 首页聚合（开关/断点/临期/档案/当季/免责） |
| 食材 | GET `/v1/ingredients` | 食材库查询（分类/关键词含别名） |
| 识别与语音 | POST `/v1/vision/recognize` | 拍照识别（多模型回退，置信度门限） |
| 识别与语音 | POST `/v1/vision/confirm` | 识别结果确认（写入库存） |
| 识别与语音 | POST `/v1/speech/asr` | 语音转文字（mock ASR，音频不落盘） |
| 问答 | POST `/v1/ask` | 自然语言主入口（闸门→意图路由→受限问答/推荐） |
| 问答 | POST `/v1/search` | 菜名/问答搜索（与 ask 同实现） |
| 推荐 | POST `/v1/recommend` | 推荐主接口（三档结果+rank_reasons+filtered_by） |
| 菜谱 | GET `/v1/recipes/{id}` | 菜谱详情（servings 缩放重算） |
| 菜谱 | GET `/v1/recipes/{id}/nutrition` | 菜谱营养估算（缺失项不按 0 计） |
| 菜谱 | POST `/v1/recipes/{id}/feedback` | 菜谱反馈（like/dislike/cooked） |
| 烹饪 | POST `/v1/cooking/sessions` | 创建烹饪会话（过敏原冲突检查） |
| 烹饪 | GET/PATCH `/v1/cooking/sessions/{id}` | 会话详情（断点续做）/步骤推进（状态机） |
| 烹饪 | POST `/v1/cooking/sessions/{id}/help` | 烹饪求助（每会话限 3 次） |
| 烹饪 | POST `/v1/cooking/sessions/{id}/finish` | 完成会话（评分写 recipe_feedback） |
| 营养 | GET `/v1/nutrition/summary` | 营养汇总（按日/按餐聚合） |
| 营养 | POST `/v1/nutrition/manual` | 手动补录饮食记录（先过风控闸门） |
| 库存 | GET/POST `/v1/inventory` | 库存列表（临期优先）/新增条目 |
| 库存 | GET `/v1/inventory/expiring` | 临期查询（仅中性描述，RL-3） |
| 库存 | POST `/v1/inventory/deduct-suggest` | 扣减建议（两段式第一步） |
| 库存 | POST `/v1/inventory/deduct-confirm` | 扣减确认（两段式第二步，降档留痕） |
| 库存 | PATCH/DELETE `/v1/inventory/{id}` | 更新（状态机）/删除条目 |
| 库存 | GET/POST `/v1/shopping-list` | 购物清单查询/批量新增（合并去重） |
| 库存 | PATCH/DELETE `/v1/shopping-list/{id}` | 勾选/删除清单行 |
| 库存 | POST `/v1/shopping-list/{id}/to-inventory` | 清单项转入库存（low 档） |
| 个人中心 | GET/POST `/v1/favorites` | 收藏列表（分组）/收藏菜谱（幂等） |
| 个人中心 | DELETE `/v1/favorites/{recipe_id}` | 取消收藏（软删） |
| 个人中心 | GET `/v1/history` | 烹饪历史（完成倒序） |
| 个人中心 | GET `/v1/signature-dishes` | 拿手菜（做完≥2 次且均分≥4） |
| 个人中心 | GET/PUT `/v1/settings` | 用户设置查询/合并写入 |
| 个人中心 | GET `/v1/me/export` | 个人数据导出（JSON 附件） |
| 个人中心 | DELETE `/v1/me` | 注销账号（级联清理，订单保留） |
| 会员 | GET `/v1/member/plan` | 价目表预览（模拟支付，不真实扣款） |
| 会员 | GET `/v1/member/me` | 会员状态与当日识别额度 |
| 会员 | POST `/v1/member/orders` | 创建待支付订单（switch.payment 关闭 403） |
| 会员 | POST `/v1/member/orders/{order_no}/mock-pay` | 模拟支付回调（幂等状态机） |
| 会员 | GET `/v1/member/orders` | 本人订单列表 |
| 反馈 | POST `/v1/feedback` | 提交用户反馈（风控闸门+回执） |
| 反馈 | GET `/v1/feedback/{id}` | 反馈状态查询 |
| 创新 | POST `/v1/innovation/precheck` | AI 创新预检（高危/过敏原/特殊人群/taboo） |
| 创新 | POST `/v1/innovation/generate` | AI 创新生成（LLM 离线自动降级本地模板） |
| 创新 | GET `/v1/innovation/recipes/{id}` | 创新菜详情（本人私有） |
| 创新 | POST `/v1/innovation/recipes/{id}/adopt` | 采纳（generated→adopted） |
| 创新 | POST `/v1/innovation/recipes/{id}/index` | 入私有向量索引（adopted→indexed） |
| 创新 | POST `/v1/innovation/recipes/{id}/reuse` | 复用创新菜参与推荐 |
| 创新 | POST `/v1/innovation/recipes/{id}/feedback` | 创新菜评分回流（调整搭配权重） |
| 追溯 | GET `/v1/trace/{request_id}` | Agent 调度 trace 详情（W-06 面板） |
| 配置 | GET `/v1/config/switches` | 远程开关（5 模块布尔值） |

### 11.2 后台 /admin/v1（JWT Bearer）

| Tag | 方法 路径 | 说明 |
| --- | --- | --- |
| 认证 | POST `/admin/v1/auth/login` | 登录（用户名密码 → JWT，12h） |
| 认证 | GET `/admin/v1/auth/me` | 当前登录身份 |
| 成员权限 | GET/POST `/admin/v1/admin-users` | 管理员列表/创建（super_admin） |
| 成员权限 | PUT `/admin/v1/admin-users/{id}` | 更新管理员（角色/状态/密码） |
| 菜谱管理 | POST `/admin/v1/recipes/batch-import` | 批量导入（json/csv/md，成功行写 draft） |
| 菜谱管理 | GET/POST `/admin/v1/recipes` | 菜谱分页列表/创建（draft） |
| 菜谱管理 | GET/PUT `/admin/v1/recipes/{id}` | 菜谱详情/整卡更新 |
| 菜谱管理 | POST `/admin/v1/recipes/{id}/publish` | 发布（用量量化闸门） |
| 菜谱管理 | POST `/admin/v1/recipes/{id}/unpublish` | 下架（published→draft） |
| 菜谱管理 | POST `/admin/v1/recipes/{id}/rollback` | 按操作日志回滚内容 |
| 食材库 | GET/POST `/admin/v1/ingredients` | 食材分页列表/创建 |
| 食材库 | PUT/DELETE `/admin/v1/ingredients/{id}` | 更新/删除（被菜谱引用 409） |
| 食材库 | GET/POST `/admin/v1/ingredients/{id}/aliases` | 别名列表/新增 |
| 食材库 | DELETE `/admin/v1/ingredients/{id}/aliases/{alias_id}` | 删除别名 |
| 营养数据 | GET/PUT `/admin/v1/nutrition/{ingredient_id}` | 营养查询/upsert（data_source 必填） |
| 风控规则 | GET/POST `/admin/v1/risk-rules` | 规则列表（含停用）/创建 |
| 风控规则 | PUT `/admin/v1/risk-rules/{id}` | 更新规则 |
| 风控规则 | POST `/admin/v1/risk-rules/{id}/toggle` | 启停（热更新） |
| 风控规则 | POST `/admin/v1/risk-rules/rollback` | 按操作日志回滚 |
| 违禁词 | GET/PUT/POST/DELETE `/admin/v1/sensitive-words` | 敏感词查询/全量替换/追加/删除 |
| 日志 | GET `/admin/v1/trace-logs` | Agent 调用日志四维过滤查询 |
| 日志 | GET `/admin/v1/operation-logs` | 后台操作审计分页 |
| 反馈工单 | GET `/admin/v1/feedbacks` | 工单分页列表 |
| 反馈工单 | POST `/admin/v1/feedbacks/{id}/transition` | 工单流转（start/resolve） |
| 看板 | GET `/admin/v1/dashboard/cost` | 成本看板（agent_trace 按日聚合） |
| 看板 | GET `/admin/v1/dashboard/risk` | 风控看板（risk_log 按日聚合） |
| 远程开关 | GET/PUT `/admin/v1/config/switches` | 五模块开关查询/全量更新（version+1） |
| 远程开关 | POST `/admin/v1/config/switches/rollback` | 按操作日志回滚开关 |
| 订单管理 | GET `/admin/v1/orders` | 订单分页列表 |
| 订单管理 | POST `/admin/v1/orders/{order_no}/compensate` | 人工补发（failed/closed→paid/refunded） |
| 创新规则库 | GET/POST `/admin/v1/innovation/rules` | 搭配规则列表/创建 |
| 创新规则库 | PUT/DELETE `/admin/v1/innovation/rules/{id}` | 更新/删除规则 |
| 创新规则库 | GET `/admin/v1/innovation/recipes` | AI 创新菜列表（status 过滤） |
| 创新规则库 | POST `/admin/v1/innovation/recipes/{id}/inspect` | 创新菜巡检（只报告不升格） |
| 创新规则库 | POST `/admin/v1/innovation/recipes/{id}/remove` | 创新菜下架（→removed） |

## 12. Docker Compose 部署（容器栈）

文件：根目录 `docker-compose.yml`（db + api + web + redis）+ `backend/Dockerfile` + 根级 `Dockerfile.web`（单镜像 nginx 托管两套前端）+ `nginx/nginx.conf`。

```powershell
# 在项目根目录（d:\Code_Work\AI_Cook）执行：
powershell -ExecutionPolicy Bypass -File scripts\manage.ps1 -Action docker -DockerCmd build  # 构建双镜像
powershell -ExecutionPolicy Bypass -File scripts\manage.ps1 -Action docker -DockerCmd up     # 拉起并等待 /v1/healthz 就绪
docker compose exec api python -m app.seed                                                   # 首次启动：幂等种子（食材/菜谱/风控/管理员）
powershell -ExecutionPolicy Bypass -File scripts\manage.ps1 -Action smoke                    # 12 组冒烟断言
powershell -ExecutionPolicy Bypass -File scripts\manage.ps1 -Action docker -DockerCmd down   # 停止（保留 pgdata/uploads 卷）
```

- 访问：用户端 `http://localhost/`（web-stage1）、管理后台 `http://localhost/admin/`（admin-web，`admin/Admin@123456`）、API `http://localhost/v1/healthz`（同时发布 8000）。宿主机 80 被占用时以 `WEB_PORT=8080` 拉起，地址变为 `http://localhost:8080/`。
- 服务拓扑：nginx(80) 反代 `/v1` `/api` `/admin/v1` → api:8000；api 启动即 `alembic upgrade head`（失败即退出）后 uvicorn；db 为 `pgvector/pgvector:pg16`（自动建库 aicook，不发布宿主 5432 以避免与本机开发库冲突）；redis 预留（进程内缓存，不强依赖）。
- 配置注入：api 经 `env_file: backend/.env` 透传 LLM 配置，`environment` 覆盖 `DB_HOST=db`；`ADMIN_PASSWORD`/`ADMIN_JWT_SECRET` 生产部署必须更换强值。
- 镜像源：基础镜像走 `docker.m.daocloud.io` 加速前缀、pip 走阿里云镜像（当前网络直连 Docker Hub / PyPI 官方源不可用或极慢）；网络环境允许时删除前缀即可切回官方源。
- 管理后台子路径适配：容器构建时以 `npm run build-only -- --base=/admin/` 打包（`build` 脚本的 run-p 包装不透传附加参数），配套 `admin-web/src/router` 的 `createWebHistory(import.meta.env.BASE_URL)` 一行调整；dev 与根路径部署行为不变。
