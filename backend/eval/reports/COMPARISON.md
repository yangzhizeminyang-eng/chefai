# Agent Eval 基线对比说明

- 基线报告：`baseline_20261017_090819.json/.md`（升级前口径，HowToCook 语料未导入，候选池 45 篇）
- 升级后报告：`report_20261017_092107.json/.md`（FS-001 规则补丁后，语料已导入，候选池 390 篇，关键词路径）
- **真实模型报告**：`report_20261017_151300.json/.md`（智谱 embedding-3 2048 维真实 API，同 390 篇候选池）
- 三次报告意图/风控维度均为确定性口径（LLM 关键词兜底 + 本地规则风控），可重复运行；真实模型报告的检索维度依赖外部 API（网络抖动会使延迟指标波动）。

## 指标对比

| 维度 | 指标 | 基线（45 篇） | 关键词（390 篇） | 智谱真实（390 篇） | 结论 |
| --- | --- | --- | --- | --- | --- |
| 意图 | 准确率 | 1.000 | 1.000 | 1.000 | 持平（24 条） |
| 风控 | 高危拦截召回率 | 0.9231 | **1.000** | **1.000** | Eval 发现 FS-001 变体漏拦（"木耳泡了三天"绕过原关键词组），补 seed/safety.py 第三组时长词后召回达标；11 类高危样本全拦截红线恢复 |
| 风控 | 误拦截率 | 0.000 | 0.000 | 0.000 | 持平（4 条正常问题零误拦） |
| 检索 | Hit@3 | 0.8235 | 0.8235 | **0.9412** | 真实语义检索 vs 同候选池关键词路径 **+11.8pp**（16/17 用例 Top-3 命中） |
| 检索 | Hit@5 | 0.8235 | 0.8235 | **0.9412** | 同上 |
| 检索 | MRR | 0.8235 | 0.8235 | **0.8725** | 首命中位置前移（+4.9pp） |
| 检索 | Recall@5 | 0.7059 | 0.3334 | 0.4001 | 基线→关键词列**口径偏移不可比**（候选池 45→390）；关键词→智谱列同口径 +6.7pp |
| 延迟 | 检索 P50 / P95 (ms) | 34.7 / 81.2 | 29.8 / 66.8 | 1622 / 2753 | 真实 API 单次嵌入调用 ~1.6s（查询级 LRU 缓存命中后近似关键词路径延迟）；生产部署可容器化本地 embedding 或接受该延迟 |
| 引用 | 覆盖率 | unavailable | unavailable | unavailable | 当前链路未产出可校验引用字段，诚实标注 |
| 费用 | Token / 成本 | unavailable | unavailable | unavailable | 评测路径未采集 usage（诚实标注，未编造） |

## 真实链路验证记录（2026-10-17）

- 连通冒烟：`ZhipuEmbeddingProvider.embed(["番茄炒蛋怎么做"])` → 2048 维、L2 归一化 ✓（401 排障记录：首次因 .env 写入损坏 72 字符 Key 失败，Python 精确重写后 49 字符格式校验通过）
- 回填：`python -m app.embedding_backfill --provider zhipu` → **390/390 written，自检 PASS**（coverage=1.000，dim_check=ok，finite_check=ok）
- 本地库无 pgvector → 物理列按设计跳过，向量存 `embedding_json` 便携列（2048 维），检索走 Python 点积回退；容器部署（pgvector 0.8.7 已实测）走 `embedding_zhipu halfvec(2048)` + hnsw 索引
- 测试隔离：`tests/conftest.py` 强制 `EMBEDDING_PROVIDER=hash`——测试进程绝不真实调用嵌入 API（CI 不依赖付费 API 原则）

## 复现命令（cwd = backend/）

```powershell
.venv\Scripts\python.exe -m app.seed                 # 迁移 + 种子（含语料）
.venv\Scripts\python.exe -m eval.run_eval --baseline # 基线口径报告
.venv\Scripts\python.exe -m eval.run_eval            # 当前配置报告（provider 决定检索路径）
.venv\Scripts\python.exe -m pytest tests/test_eval_runner.py -q
```
