# AI 厨娘后端 · 从 0 到 1 演示链（demo-walkthrough）

本文档提供一条**全程可复制**的演示链：先以纯本地确定性 Stub 链路完整演示（不需要任何付费 API Key），再给出接入智谱 embedding-3 真实模型的切流步骤。接口契约以 `http://127.0.0.1:8000/docs`（OpenAPI）为准。

约定：

- 操作系统口径为 **Windows PowerShell**；每个代码块首行以注释标注 `cwd`（当前目录），执行前请先切换。
- 项目根目录 = `d:\ChefAI\ai_cook`；后端目录 = `d:\ChefAI\ai_cook\backend`。
- 响应示例仅展示关键字段示意，完整字段结构以 OpenAPI 为准。

---

## 1. 环境准备

### 1.1 Python 虚拟环境（cwd = 项目根目录）

```powershell
Set-Location d:\ChefAI\ai_cook\backend
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
```

### 1.2 环境配置（cwd = backend）

复制 `.env.example` 为 `.env`，填写本机 PostgreSQL 连接信息（本地开发库缺省 `localhost:5432`、用户 `postgres`、库 `aicook`，按实际修改 `DB_PASSWORD`）：

```powershell
Copy-Item .env.example .env
notepad .env    # 至少确认 DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME
```

> 本节为 Stub 演示，**无需配置任何模型 Key**（`LLM_API_KEY` / `ZHIPU_API_KEY` 留空即可，链路自动走确定性降级路径）。

### 1.3 迁移 + 种子（cwd = backend，一条命令）

```powershell
.venv\Scripts\python.exe -m app.seed
```

`app.seed` 内部先做 Alembic 分支决策（幂等，可重复执行），再依次填充食材 / 菜谱 / HowToCook 语料 / 风控规则 / 远程开关等种子数据；语料导入完成后共 390 篇 published 菜谱。HowToCook 语料缓存于 `backend\data\HowToCook`，下载失败时会跳过语料导入（影响见 §4.3）。

### 1.4 启动后端（cwd = backend）

```powershell
.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

另开一个终端验证健康检查：

```powershell
# cwd 任意
Invoke-RestMethod http://127.0.0.1:8000/v1/healthz
# 预期：status=ok, database=up, version=1.0.0
```

---

## 2. Stub 链路演示（无真实密钥，全程确定性）

### 2.1 创建匿名会话

```powershell
# cwd 任意
$anon = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/v1/auth/anonymous `
  -ContentType "application/json" -Body '{"client_type":"web_demo"}'
$anon.anonymous_id
# 预期：返回 user_id 与 anon_ 前缀的 anonymous_id（重复调用复用同一 ID）
```

### 2.2 输入风控：一票否决拦截（G-01）

用 FS-001「木耳/银耳久泡」高危样本（规则第三组时长词已覆盖「三天」变体）：

```powershell
# cwd 任意
$blocked = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/v1/ask `
  -ContentType "application/json" -Body '{"text":"木耳泡了三天还能吃吗"}'
$blocked.blocked; $blocked.risk.rule_code
# 预期：blocked=True，命中一票否决（G-01），risk.rule_code=FS-001（木耳/银耳久泡），
# 响应体为纯阻断结构（不承载任何业务内容）
```

> 一票否决短路纯净性红线：阻断响应结构上不含 `results` / `candidates` / `nutrition` 等业务字段；`risk` 详情为 W-05 三块卡片数据源，完整结构以 OpenAPI 为准。

### 2.3 `/v1/ask` 意图识别（关键词兜底）

LLM 不可用时意图路由走 supervisor 关键词兜底（确定性，可离线复现）：

```powershell
# cwd 任意
$ask = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/v1/ask `
  -ContentType "application/json" -Body '{"text":"家里有番茄和鸡蛋做点什么菜"}'
$ask
# 预期：recommend 意图只回 trace_id（前端再调 /v1/recommend）；free_qa 意图返回受限问答内容。
# 完整响应结构以 OpenAPI 为准。
```

### 2.4 `/v1/recommend` 有来源推荐

```powershell
# cwd 任意
$rec = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/v1/recommend `
  -ContentType "application/json" `
  -Body '{"ingredients":[{"name":"番茄"},{"name":"鸡蛋"}]}'
$rec.results | Select-Object title, match_level, source, rank_reasons
# 预期：三档结果（can_cook_now / missing_1_2 / need_more）+ rank_reasons + filtered_by；
# 每条带 source 来源标注（手写菜谱或 "HowToCook / 公开家常菜语料"）。
```

### 2.5 `/v1/trace/{request_id}` 调度面板

用上一步任一响应中的 `request_id`（或 `trace_id`）查询 Agent 调度 trace（W-06 面板数据源）：

```powershell
# cwd 任意；$rid 换成上一步实际拿到的 ID
$rid = "<上一步的 request_id>"
Invoke-RestMethod "http://127.0.0.1:8000/v1/trace/$rid"
# 预期：返回该请求的 Agent 调度 trace 详情（意图/闸门/节点耗时等 span 记录）
```

### 2.6 MCP 本地 Server 工具调用演示（stub 模式）

`AICOOK_MCP_STUB=1` 时 MCP Server 零依赖（不导入 app 模块、不连 DB），直接以 stdio JSON-RPC 2.0 交互。向子进程 stdin 写入三行请求（initialize 握手 → tools/list → tools/call），stdout 逐行返回响应：

```powershell
# cwd = backend
$env:AICOOK_MCP_STUB = "1"
@'
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"demo-cli","version":"0.0.0"}}}
{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"recipe_search","arguments":{"query":"番茄炒蛋"}}}
'@ | .venv\Scripts\python.exe -m mcp_server
# 预期（三行响应）：
# id=1 → protocolVersion="2024-11-05" + serverInfo(aicook-readonly-mcp)
# id=2 → 白名单两个只读工具 recipe_search / recipe_detail 的 inputSchema
# id=3 → content 为 text 的工具结果（isError=false，stub 固定演示数据）
Remove-Item Env:AICOOK_MCP_STUB
```

> 白名单外工具名（如 `tools/call` 传 `"name":"write_file"`）返回结果级错误 `isError=true` + "permission denied"；协议级错误码 -32700/-32601/-32602/-32603。

**服务端挂载（可选进阶）**：在 `backend/.env` 配置 `MCP_ENABLED=on` 与 `MCP_SERVER_COMMAND=["python", "-m", "mcp_server"]` 并重启后端，`/v1/ask` 的 free_qa 等三意图经 tool_loop 节点时会经 MCPClient 挂载 MCP 只读工具。注意：工具选择由 LLM 决策，**无 LLM Key 时 tool_loop 视为 done 正常收敛**（行为等同无该节点，不报错）；挂载效果建议配合真实 LLM Key 观察 `/v1/trace` 中的 span。缺省 `MCP_ENABLED=off` 完全不走 MCP 路径。

### 2.7 Agent Eval 评测报告

```powershell
# cwd = backend（需已完成 §1.3 seed）
.venv\Scripts\python.exe -m eval.run_eval
# 预期：输出 eval/reports/report_YYYYmmdd_HHMMSS.json + 同名 .md 摘要表；
# intent 24 条 / retrieval 17 条 / safety 17 条，全程确定性 Stub，无 Key 可跑。
# 需要「升级前」基线口径时加 --baseline（生成 baseline_ 前缀报告）；
# 不连库的纯离线模式加 --offline（retrieval 指标标注 unavailable）。
```

基线与升级后对比结论（风控召回 0.9231→1.000 修复闭环、Recall@5 口径偏移说明）见 `backend/eval/reports/COMPARISON.md`。

---

## 3. 真实模型链路（需用户自配 Key，另行标注）

> 本节需要你自己的智谱 API Key。下文一律以 `<你的智谱 API Key>` 占位，**请勿把真实 Key 提交进仓库**。

### 3.1 配置智谱 Embedding（cwd = backend，编辑 backend/.env）

```ini
EMBEDDING_PROVIDER=zhipu
ZHIPU_BASE_URL=https://open.bigmodel.cn/api/paas/v4/
ZHIPU_API_KEY=<你的智谱 API Key>
ZHIPU_MODEL=embedding-3
EMBEDDING_DIMENSIONS=2048
```

语义：智谱空间标识为 `embedding-3-2048`（`{ZHIPU_MODEL}-{EMBEDDING_DIMENSIONS}`），写入 `recipe_embedding.embedding_model` 列；检索/回填按该空间过滤，与旧 1024 维 hash/bailian 空间物理隔离、绝不混算余弦。**`ZHIPU_API_KEY` 留空时工厂降级 hash**（space_name 仍为 `hash-v1`，绝不冒充智谱空间）。

### 3.2 迁移（cwd = backend）

```powershell
.venv\Scripts\python.exe -m app.seed     # 或 .venv\Scripts\python.exe -m alembic upgrade head
```

迁移 revision `d8f2b7c91e43` 按库内 pgvector 扩展版本分支：扩展缺失（本地常见）→ 跳过建列不失败；≥0.7.0 → `embedding_zhipu` halfvec(2048) + hnsw 索引；<0.7.0 → vector(2048) 顺序扫描。**该迁移幂等、可 downgrade，且不删除旧 1024 维列与索引。**

### 3.3 回填向量（cwd = backend）

```powershell
# 先小样预演 5 条（打印 Provider/space_name/维度/目标列，绝不打印 Key）
.venv\Scripts\python.exe -m app.embedding_backfill --provider zhipu --limit 5
# 确认无误后全量回填（幂等：已存在目标空间 verified 行的菜谱自动跳过）
.venv\Scripts\python.exe -m app.embedding_backfill --provider zhipu
# 预期：回填 + 自检（行数对比 / 抽样维度与数值有限性校验）；自检失败退出码非 0。
```

### 3.4 检索对比与回退

```powershell
# cwd = backend：重启后端使新配置生效，然后重复 §2.3/§2.4 的 ask/recommend 请求
.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
# 可再跑一次评测留档（当前为确定性口径，语义检索对比属配置 Key 后验证项）：
.venv\Scripts\python.exe -m eval.run_eval
```

- 回退：把 `.env` 中 `EMBEDDING_PROVIDER` 改回 `hash`（或 `bailian`）并重启后端即可回到旧空间——**验证期绝不删除旧空间向量行与索引**。
- 本地无 pgvector 扩展时：向量检索自动降级 `embedding_json` 便携列 Python 点积回退路径，功能完整可演示；正式部署口径为容器镜像 `pgvector/pgvector:pg16`。

---

## 4. 排障速查

| 现象 | 排查与处理 |
| --- | --- |
| 启动报端口占用 | `netstat -ano \| findstr :8000` 查占用 PID，`taskkill /PID <pid> /F` 释放；或改 `.env` 的 `APP_PORT` 后重启 |
| healthz 503 `database=down` | 检查 PostgreSQL 是否运行、`.env` 的 `DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME` 是否正确（本地常见为密码不符）；修好后重跑 `python -m app.seed` |
| seed 提示语料下载失败 / 候选池不足 | 下载失败时 seed 自动跳过语料导入（仅手写 45 篇，test_performance 2 项因需 ≥300 候选会 error）；语料缓存目录 `backend\data\HowToCook`，网络恢复后重跑 `python -m app.seed` 按存在性补导即可 |
| 本地库无 pgvector 扩展 | 预期行为（非故障）：迁移跳过建 `embedding_zhipu` 列，向量检索走 `embedding_json` Python 点积回退；需要近似索引时改用容器镜像 `pgvector/pgvector:pg16` |
| 配了 `EMBEDDING_PROVIDER=zhipu` 但 Key 缺失/无效 | 工厂降级 hash（日志有提示，space_name 仍 `hash-v1`），不会用假向量冒充智谱空间；回填命令自检失败以非 0 退出码结束 |
| MCP Server 无响应 | stub 演示模式需先 `$env:AICOOK_MCP_STUB = "1"`；真实模式需 `MCP_ENABLED=on` 且 `MCP_SERVER_COMMAND` 已配置（空串视为未配置，完全不走 MCP 路径）；进程在 stdin EOF 时正常退出 |
| eval 报数据集损坏 | `eval/datasets/*.jsonl` 有最小行数校验（intent 20 / retrieval 15 / safety 15），文件缺失或行数不足时报错；请勿手工删改数据集行 |

---

## 5. 相关文档

- 后端总览与环境/部署：`backend/README.md`（§13 Agent 工具与 MCP / §14 Agent Eval / §15 智谱 Embedding / §16 创新任务持久化）
- Eval 基线对比：`backend/eval/reports/COMPARISON.md`
- 接口契约：`http://127.0.0.1:8000/docs`（OpenAPI）
