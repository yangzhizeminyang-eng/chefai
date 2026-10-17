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
│   ├── graph/                 # LangGraph 编排（supervisor / guards / qa / tool_loop / compose / finalize）
│   └── schemas/               # Pydantic v2 请求/响应模型
├── mcp_server/                # 本地 stdio MCP Server（JSON-RPC 2.0 只读工具；AICOOK_MCP_STUB=1 进入零依赖 stub 模式）
├── eval/                      # Agent Eval 评测框架（datasets 人工合成数据集 / reports 报告 / run_eval CLI）
└── tests/                     # pytest（369+ 条：风控 / 硬过滤 / 排序 / 营养 / API 集成 / eval / 工具与 MCP / 创新恢复 / 质量补强）
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
# 全量测试（369+ 条，连真实本地库 aicook，需先完成 seed；
# test_performance 2 项在 HowToCook 语料未导入时 error——其需 ≥300 篇候选池）
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

1. **bge-m3 本地向量检索未引入**：保留 `EMBEDDING_MODE` 配置语义与适配器接口（`recipe_embedding` 预留表已建）；数百篇语料规模下「关键词 + 别名 + 覆盖率」混合召回满足阶段一演示，引入 2GB+ 权重与 torch 依赖收益不匹配（05-V1.1 §12.2 将其定义为可切换项）。阶段二升级已新增**智谱 embedding-3 远程语义嵌入路径**（见 §15，`EMBEDDING_PROVIDER='zhipu'` 启用）；`hash` 仍为缺省兜底提供方，未配置 Key 时行为与阶段一完全一致。
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

## 13. Agent 工具调用与 MCP（阶段二升级）

> 演示链全程可复制命令见 `docs/demo-walkthrough.md`。接口契约以 `http://127.0.0.1:8000/docs`（OpenAPI）为准。

### 13.1 工具层（app/ability/tools.py）

`AgentTool` 抽象基类 + 4 个**只读**内置工具（只复用既有业务函数，不重写业务逻辑；检索走 `use_vector=False`，不触发嵌入惰性回填写库）：

| 工具名 | 能力 | 只读 |
| --- | --- | --- |
| `recipe_search` | 按自然语言查询文本检索已发布菜谱候选（`query` 必填 / `top_k` 1~20 缺省 5） | 是 |
| `recipe_detail` | 按菜谱 ID 查详情 | 是 |
| `nutrition_estimate` | 菜谱营养估算 | 是 |
| `inventory_query` | 库存查询 | 是 |

`execute_tool` 统一执行入口：pydantic 参数校验（失败返回 `invalid_params`，不向编排层抛异常）→ 只读工具 LRU 幂等缓存（容量 128）→ 线程池超时控制 → tenacity 重试（仅 `unavailable`/`timeout`，最多 2 次重试共 3 次尝试）→ 结构化错误码（`invalid_params`/`timeout`/`permission_denied`/`unavailable`/`internal`）→ 审计友好的 `ToolResult`（`params_summary` 截断 200 字符并掩码 `api_key`/`password`/`token`/`secret` 等敏感字段）。

### 13.2 工具循环节点（app/graph/nodes/tool_loop.py）

- **硬限制**：`MAX_TOOL_ROUNDS=3`（轮数上限）、`TOOL_LOOP_BUDGET_SECONDS=25.0`（总耗时预算）、单次工具执行超时按剩余预算收紧（上限 10s、保底 0.5s）；触限置 `state.tool_loop_limit_hit=True` 并立即返回（state 新增 `tool_results` / `tool_loop_limit_hit`）。
- **决策方式**：LLM 按工具清单输出严格 JSON——选 `{tool, params}` 或 `{done: true}`；每轮经 `make_span` 记录 trace。
- **降级红线**：LLM 失败 / 输出解析失败 / 选择未知工具 → 视为 `done` 正常收敛（不触限、不抛异常）；最终回答仍由 `node_free_qa` 生成并经 compose → output_guard **出口闸门**（工具结果只作回答素材，不绕过风控）。
- **主图接入**：main_graph 中 `photo_recognize` / `free_qa` / `smalltalk_or_out_of_scope` 三意图路由 `tool_loop → node_free_qa`（无条件边）；`MCP_ENABLED='off'`（缺省）时仅挂内置 4 工具。

### 13.3 本地 MCP Server / Client

- `backend/mcp_server/`：stdio **JSON-RPC 2.0**（`protocolVersion="2024-11-05"`）最小实现，支持 `initialize` / `notifications/initialized` / `tools/list` / `tools/call` / `ping`；协议级错误码 -32700/-32601/-32602/-32603。工具白名单 `recipe_search` / `recipe_detail`，白名单外工具名返回结果级错误（`isError=true` + "permission denied"）；DB 不可用时转结构化错误消息，进程不崩溃。
- **stub 模式**：环境变量 `AICOOK_MCP_STUB=1` 时不导入 app 模块、不连 DB，返回固定演示数据（测试与前端联调用）。
- `app/ability/mcp_client.py`：子进程拉起 + initialize 握手 + `list_tools`/`call_tool`/`close`；客户端不做重试，不可用时由 tool_loop 节点降级（连接失败 → 构建期静默剔除 MCP 工具；执行返回 `unavailable`/`timeout`/`permission_denied` → 该工具本轮起剔除，均不阻断主链路）。

本地运行（cwd = backend，PowerShell）：

```powershell
$env:AICOOK_MCP_STUB = "1"                    # stub 演示模式（零 DB 依赖）；删除该变量则为真实模式
.venv\Scripts\python.exe -m mcp_server        # 阻塞运行，stdin EOF（Ctrl+C / 关闭管道）正常退出
```

### 13.4 配置项（backend/.env）

| 变量 | 取值 | 说明 |
| --- | --- | --- |
| `MCP_ENABLED` | `off`（缺省）/ `on` | `on` 时 tool_loop 节点经 MCPClient 挂载 MCP 只读工具 |
| `MCP_SERVER_COMMAND` | 空串（缺省）/ 命令串 | stdio MCP Server 启动命令（JSON 数组字符串或空格分隔，如 `["python", "-m", "mcp_server"]`） |

测试覆盖：`tests/test_agent_tools.py`（工具框架）、`tests/test_tool_node.py`（工具循环）、`tests/test_mcp_client.py`（stub server 覆盖 8 路径）。

## 14. Agent Eval（可重复评测）

离线评测框架（`backend/eval/`），对三条核心链路做可重复的确定性评测。

### 14.1 运行命令（cwd = backend，需先 `python -m app.seed` 完成迁移与种子）

```powershell
.venv\Scripts\python.exe -m eval.run_eval --baseline   # 生成 baseline_ 前缀基线报告
.venv\Scripts\python.exe -m eval.run_eval              # 常规报告（report_ 前缀）
.venv\Scripts\python.exe -m eval.run_eval --offline    # --offline 模式不连库（retrieval 指标标注 unavailable）
```

报告输出至 `eval/reports/`（`report_YYYYmmdd_HHMMSS.json` + 同名 `.md` 摘要表）；基线对比记录见 `eval/reports/COMPARISON.md`。

### 14.2 数据集（eval/datasets/*.jsonl，人工合成、不含真实用户隐私）

| 数据集 | 条数 | 评测对象 |
| --- | --- | --- |
| `intent_cases.jsonl` | 24 | supervisor 关键词兜底意图分类（确定性路径） |
| `retrieval_cases.jsonl` | 17 | 检索候选命中（空食材 + 文本查询） |
| `safety_cases.jsonl` | 17 | 风控规则引擎高危拦截 / 正常问题误拦 |

### 14.3 指标口径

| 维度 | 指标 | 说明 |
| --- | --- | --- |
| 意图 | 准确率、延迟 P50/P95 | 关键词兜底路径（离线可测） |
| 风控 | 高危拦截召回率、误拦截率 | 引擎异常内部消化为 UNKNOWN=不拦截，按 D9 语义如实统计 |
| 检索 | Hit@3 / Hit@5 / Recall@5 / MRR、延迟 P50/P95 | `--offline` 时整组标注 unavailable |
| 引用 | 覆盖率 | **恒为 unavailable**：当前回答链路未产出可校验的引用来源字段 |
| 费用 | Token / 成本 | **恒为 unavailable**：评测路径为确定性兜底（关键词/规则/SQL），无模型调用与计费数据 |

诚实性约定：无可靠来源的指标一律输出 `unavailable` 并注明原因，绝不编造数字；单条用例失败记 `error` 不中断整体评测。

### 14.4 基线与对比结论（详见 eval/reports/COMPARISON.md）

| 指标 | 基线（语料未导入，候选池 45 篇） | 升级后（FS-001 补丁 + 候选池 390 篇） | 结论 |
| --- | --- | --- | --- |
| 意图准确率 | 1.000 | 1.000 | 持平（24 条） |
| 风控高危拦截召回率 | 0.9231 | **1.000** | Eval 发现 FS-001「木耳久泡」规则变体漏拦（"木耳泡了三天" 绕过原关键词组），补 `app/seed/safety.py` 第三组时长词后达标，11 类高危样本全拦截红线恢复 |
| 风控误拦截率 | 0.000 | 0.000 | 持平 |
| Hit@3 / Hit@5 / MRR | 0.8235 | 0.8235 | 持平（17 条） |
| Recall@5 | 0.7059 | 0.3334 | **口径偏移，不可直接比较**：基线候选池 45 篇 vs 升级后 390 篇（HowToCook 语料导入后分母语义变化） |

### 14.5 CI 原则

评测全程确定性 Stub（关键词兜底 + 本地规则风控 + SQL 检索），**不依赖任何付费 API**，可在 CI 无密钥环境重复运行；配套测试 `tests/test_eval_runner.py`。

## 15. 智谱 Embedding 与向量空间切换

新增智谱 `embedding-3` 远程语义嵌入提供方（OpenAI 兼容协议），与既有 `hash`（确定性哈希兜底）/ `bailian`（百炼）并存。

### 15.1 配置项（backend/.env）

| 变量 | 缺省值 | 说明 |
| --- | --- | --- |
| `EMBEDDING_PROVIDER` | `hash` | 改为 `zhipu` 启用智谱嵌入 |
| `ZHIPU_BASE_URL` | `https://open.bigmodel.cn/api/paas/v4/` | 智谱 OpenAI 兼容端点 |
| `ZHIPU_API_KEY` | 空串 | **空串时工厂降级 hash**，绝不以 hash 向量冒充智谱空间 |
| `ZHIPU_MODEL` | `embedding-3` | 智谱嵌入模型名 |
| `EMBEDDING_DIMENSIONS` | `2048` | 智谱空间向量维度，与 `embedding_zhipu halfvec(2048)` 列对齐 |

### 15.2 空间隔离机制

- 智谱空间标识 `space_name = f"{ZHIPU_MODEL}-{EMBEDDING_DIMENSIONS}"`（即 `embedding-3-2048`），写入 `recipe_embedding.embedding_model` 列；**检索与回填均按当前 provider.space_name 过滤**——不同空间的向量绝不混算余弦相似度（维度/语义均不可比）。
- 远程响应三重校验：返回条数、向量维度、数值有限性（`math.isfinite`），任一不满足即报错，不落脏数据。
- 旧 1024 维 `embedding` vector(1024) 列与 ivfflat 索引**原样保留**，新旧空间靠 `embedding_model` 列过滤隔离。

### 15.3 迁移与回滚（revision `d8f2b7c91e43`）

按 `pg_extension.extversion` 分支（幂等 DDL，全部 `IF [NOT] EXISTS`，可 downgrade）：

| 库内 pgvector 状态 | 动作 |
| --- | --- |
| 扩展不存在 | 记 WARNING 跳过建列与索引，**迁移不失败**（embedding_json 便携列不受影响） |
| extversion ≥ 0.7.0 | `embedding_zhipu` **halfvec(2048)** 列 + hnsw `halfvec_cosine_ops` 索引 `idx_emb_zhipu`（近似检索） |
| extversion < 0.7.0 | `embedding_zhipu` vector(2048) 列，无近似索引（顺序扫描） |

### 15.4 回填与切流（cwd = backend）

```powershell
.venv\Scripts\python.exe -m app.embedding_backfill --provider zhipu          # 全量回填（幂等，已存在目标空间 verified 行的菜谱自动跳过）
.venv\Scripts\python.exe -m app.embedding_backfill --provider zhipu --limit 5 # 小样预演
.venv\Scripts\python.exe -m app.embedding_backfill --provider zhipu --force   # 忽略既有行强制重算
```

- 回填含自检（目标空间 verified 行数 vs published 菜谱数、抽样校验维度与有限值），失败以非 0 退出码结束（供切流流水线判定）。
- **回退路径**：把 `EMBEDDING_PROVIDER` 改回旧提供方（`hash` / `bailian`）并重启即可回到旧空间——验证期**绝不删除旧空间向量行与索引**。
- 检索分流：`app/ability/retrieval.py` 的 `_vector_search_pgvector` 按向量维度分流列（1024 维 → 旧 `embedding` 列；非 1024 维 → `embedding_zhipu` 列，halfvec/vector 类型经 `probe_zhipu_column` 实测）。

### 15.5 本地无 pgvector 时的行为

本地开发库（PostgreSQL 16 未装 pgvector 扩展）下：迁移跳过建列，向量检索自动降级 **`embedding_json` 便携列 Python 点积**回退路径（≤800 行规模、无 numpy），2048 维向量可正常存储与计算；容器部署镜像 `pgvector/pgvector:pg16` 为正式口径（扩展 ≥0.7 走 halfvec + hnsw 索引）。

## 16. 创新异步任务持久化与重启恢复

AI 创新生成任务（`POST /v1/innovation/generate` 异步链路）原为纯内存 job store，进程重启后轮询方将 404。本轮升级（改进方案 M-01 最小落地）补齐持久化：

- **写穿（write-through）**：`app/models/innovation.py` 的 `InnovationJob` 表（迁移 `9c3e1f7a52b8` 新建 `innovation_job` 表，`status` CHECK 五态 `pending/running/succeeded/failed/blocked` 与内存状态机一致，索引 `idx_innovation_job_user` 支撑按用户查询与恢复扫描）在**提交 / running / 终态**三个时机写穿内存 store。
- **启动恢复**：`app/main.py` startup 调用 `recover_stale_innovation_jobs()`，把遗留 `pending/running` 任务置为 `failed`（错误文案「服务已重启，任务被中断，请重新提交」），轮询方拿到明确终态而非永久 pending。
- **DB fallback**：`get_innovation_job` 内存 miss 时回读 DB（**同用户**可取回终态副本；他人任务仍 404，跨用户隔离口径不变）。
- 测试覆盖：`tests/test_innovation_job_recovery.py`、`tests/test_innovation_jobs.py`。
