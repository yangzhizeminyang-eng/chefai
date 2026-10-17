# Agent Eval 基线对比说明

- 基线报告：`baseline_20261017_090819.json/.md`（升级前口径，HowToCook 语料未导入，候选池 45 篇）
- 升级后报告：`report_20261017_092107.json/.md`（FS-001 规则补丁后，语料已导入，候选池 390 篇）
- 两次报告均为确定性 Stub 口径（LLM 关键词兜底 + 本地规则风控 + SQL 文本检索），不依赖付费 API，可重复运行。

## 指标对比

| 维度 | 指标 | 基线 | 升级后 | 结论 |
| --- | --- | --- | --- | --- |
| 意图 | 准确率 | 1.000 | 1.000 | 持平（24 条） |
| 风控 | 高危拦截召回率 | 0.9231 | **1.000** | Eval 发现 FS-001 变体漏拦（"木耳泡了三天"绕过原关键词组），补 seed/safety.py 第三组时长词后召回达标；11 类高危样本全拦截红线恢复 |
| 风控 | 误拦截率 | 0.000 | 0.000 | 持平（4 条正常问题零误拦） |
| 检索 | Hit@3 / Hit@5 | 0.8235 | 0.8235 | 持平（17 条） |
| 检索 | MRR | 0.8235 | 0.8235 | 持平 |
| 检索 | Recall@5 | 0.7059 | 0.3334 | **口径偏移，不可直接比较**：基线候选池 45 篇（语料未导入），升级后 390 篇；Recall@5 要求 Top-5 覆盖全部期望命中，候选池扩大 8.7 倍后分母语义变化 |
| 延迟 | 检索 P50 / P95 (ms) | 34.7 / 81.2 | 29.8 / 66.8 | 候选池扩大下持平略优（embedding_json Python 点积回退路径） |
| 引用 | 覆盖率 | unavailable | unavailable | 当前链路未产出可校验引用字段，诚实标注 |
| 费用 | Token / 成本 | unavailable | unavailable | Stub 链路无模型调用与计费数据，诚实标注 |

## 升级项与 Eval 的关系

- **智谱 embedding-3（2048 维）**：`EMBEDDING_PROVIDER=zhipu` + 真实 Key 配置后重跑 `python -m eval.run_eval` 即可对比语义检索 vs 关键词路径；本机无 pgvector 扩展时向量检索自动降级 `embedding_json` 点积路径（2048 维向量可正常存储与计算），容器部署（pgvector ≥0.7）走 `embedding_zhipu halfvec(2048)` 列 + hnsw 索引。真实模型链路的检索质量对比属「待用户配置 Key 后验证」项，未在本报告中编造数字。
- **工具调用 / MCP**：本轮 Eval 数据集覆盖意图与风控维度；工具选择维度的样例接口已预留（`run_eval.py` 指标函数可扩展），随 tool_loop 接入主链路后补充用例。

## 复现命令（cwd = backend/）

```powershell
.venv\Scripts\python.exe -m app.seed                 # 迁移 + 种子（含语料）
.venv\Scripts\python.exe -m eval.run_eval --baseline # 基线口径报告
.venv\Scripts\python.exe -m eval.run_eval            # 升级后报告
.venv\Scripts\python.exe -m pytest tests/test_eval_runner.py -q
```
