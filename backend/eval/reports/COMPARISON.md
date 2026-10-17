# Agent Eval 基线对比说明

## 报告来源与可复核性声明（2026-10-17 修正）

| 对比列 | 来源文件 | 可复核性 |
| --- | --- | --- |
| 基线（45 篇）† | `baseline_20261017_090819.json/.md` | **不可独立复核**：该报告生成后从未提交 git（`git log --diff-filter=A` 无记录），现文件系统中亦不存在；基线列数字为当时 CLI 终端输出的**会话留档**，不可恢复，也不伪造替代 |
| 关键词（390 篇） | `report_20261017_092107.json/.md` | 已入库，已与 JSON `metrics` 逐项核对一致 |
| 智谱真实（390 篇） | `report_20261017_151300.json/.md` | 已入库，已与 JSON `metrics` 逐项核对一致（检索维度依赖外部 API） |
| （旁证）升级前口径入库报告 | `report_20261017_090854.json/.md` | 已入库；与基线同为「FS-001 未修 + 45 篇候选池」口径，**质量指标与基线列逐项一致**，可部分佐证基线列（延迟除外，见下） |

- **基线列旁证核对**：`report_20261017_090854.json` 的质量指标与基线列完全一致（意图准确率 1.000、高危拦截召回率 0.9231、误拦截率 0.000、Hit@3 0.8235、Hit@5 0.8235、MRR 0.8235、Recall@5 0.7059）；但其检索延迟实测为 33.4/65.7 ms，与基线列 34.7/81.2 不同——两次独立运行的延迟本就波动，基线列延迟数字仅存于会话留档，**无法交叉验证**。
- **两类口径，勿混用**：
  - **离线回归口径**（意图 / 风控全维度 + 关键词路径检索）：确定性关键词兜底 + 本地规则风控 + SQL，可重复执行，是回归门禁的判定依据（`report_*.json` 顶层 `gate` 段；`--offline` 跳过检索维度并标注 skipped）；
  - **真实模型口径**（智谱 embedding-3 检索维度）：依赖外部 API，延迟受网络抖动影响（单次嵌入 ~1.6 s，查询级 LRU 缓存命中后回落），仅供横向对比，**不作为门禁阈值来源**。

## 指标对比

（各列来源见上表；关键词列 / 智谱列数字已与入库 JSON 核对一致；延迟为四舍五入）

| 维度 | 指标 | 基线（45 篇）† | 关键词（390 篇） | 智谱真实（390 篇） | 结论 |
| --- | --- | --- | --- | --- | --- |
| 意图 | 准确率 | 1.000 | 1.000 | 1.000 | 持平（24 条） |
| 风控 | 高危拦截召回率 | 0.9231 | **1.000** | **1.000** | Eval 发现 FS-001 变体漏拦（"木耳泡了三天"绕过原关键词组），补 seed/safety.py 第三组时长词后召回达标；11 类高危样本全拦截红线恢复 |
| 风控 | 误拦截率 | 0.000 | 0.000 | 0.000 | 持平（4 条正常问题零误拦） |
| 检索 | Hit@3 | 0.8235 | 0.8235 | **0.9412** | 真实语义检索 vs 同候选池关键词路径 **+11.8pp**（16/17 用例 Top-3 命中） |
| 检索 | Hit@5 | 0.8235 | 0.8235 | **0.9412** | 同上 |
| 检索 | MRR | 0.8235 | 0.8235 | **0.8725** | 首命中位置前移（+4.9pp） |
| 检索 | Recall@5 | 0.7059 | 0.3334 | 0.4001 | 基线→关键词列**口径偏移不可比**（候选池 45→390）；关键词→智谱列同口径 +6.7pp |
| 延迟 | 检索 P50 / P95 (ms) | 34.7 / 81.2 † | 29.8 / 66.8 | 1622 / 2753 | 真实 API 单次嵌入调用 ~1.6s（查询级 LRU 缓存命中后近似关键词路径延迟）；生产部署可容器化本地 embedding 或接受该延迟 |
| 引用 | 覆盖率 | unavailable | unavailable | unavailable | 当前链路未产出可校验引用字段，诚实标注 |
| 费用 | Token / 成本 | unavailable | unavailable | unavailable | 评测路径未采集 usage（诚实标注，未编造） |

† 基线列来源文件已丢失且未入库，数字不可独立复核（质量指标有 `report_20261017_090854.json` 同口径旁证，延迟无旁证）。

## 回归门禁（2026-10-17 新增）

- 报告 JSON/MD 顶层新增 `gate` 段：`{enabled, thresholds, actual, statuses, failed_case_ids, result}`；默认阈值 intent_accuracy ≥0.80、block_recall ≥1.00、false_block_rate ≤0.10、hit_at_3 ≥0.70、hit_at_5 ≥0.70、recall_at_5 ≥0.30。
- 任一可执行用例失败（passed=False 或 error 非空）直接判其所属维度 fail 并列出用例 ID（单条回归也拦截）；`--offline` 下检索指标标注 skipped，不触发 FAIL；`--gate-file` 可用 JSON 覆盖阈值，`--no-gate` 关闭门禁。
- 门禁启用且 result=FAIL 时进程退出码为 1（可接入 CI 回归拦截）；报告在任何情况下都落盘。
- 首次离线门禁实跑（2026-10-17，`report_20261017_160750.json`）：退出码 0，gate=PASS（intent_accuracy=1.0、block_recall=1.0、false_block_rate=0.0，检索三项 skipped）。

## 真实链路验证记录（2026-10-17）

- 连通冒烟：`ZhipuEmbeddingProvider.embed(["番茄炒蛋怎么做"])` → 2048 维、L2 归一化 ✓（401 排障记录：首次因 .env 写入损坏 72 字符 Key 失败，Python 精确重写后 49 字符格式校验通过）
- 回填：`python -m app.embedding_backfill --provider zhipu` → **390/390 written，自检 PASS**（coverage=1.000，dim_check=ok，finite_check=ok）
- 本地库无 pgvector → 物理列按设计跳过，向量存 `embedding_json` 便携列（2048 维），检索走 Python 点积回退；容器部署（pgvector 0.8.7 已实测）走 `embedding_zhipu halfvec(2048)` + hnsw 索引
- 测试隔离：`tests/conftest.py` 强制 `EMBEDDING_PROVIDER=hash`——测试进程绝不真实调用嵌入 API（CI 不依赖付费 API 原则）

## 复现命令（cwd = backend/）

```powershell
.venv\Scripts\python.exe -m app.seed                 # 迁移 + 种子（含语料）
.venv\Scripts\python.exe -m eval.run_eval --offline  # 离线回归 + 门禁（回归即退出码 1，检索维度 skipped）
.venv\Scripts\python.exe -m eval.run_eval --baseline # 基线口径报告（含检索维度，连库）
.venv\Scripts\python.exe -m eval.run_eval            # 当前配置报告（provider 决定检索路径）
.venv\Scripts\python.exe -m pytest tests/test_eval_gate.py tests/test_eval_runner.py -q
```
