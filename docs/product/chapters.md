# AI 厨娘·智能烹饪助手 —— 项目答辩 PPT 章节规划（V2 · 浅色版）

- **PPT 类型**：Report/Summary（汇报型，结论先行）
- **目标读者**：答辩评审老师 / 项目验收方
- **答辩人**：肖裔雄
- **总页数**：24 页
- **主题色**：**浅色为主**（底 `#F3F6FA`），主色 深青 `#0E7490`，强调 暖橙 `#EA580C`，辅色 靛蓝 `#4F46E5`；不再以黑色为主
- **必备章节**（用户指定）：重点模块与精彩代码｜问题及解决方案｜项目完成后的收获
- **本版新增**：LangGraph 图结构展示（第 12、13 页）；全篇文字内容加厚

---

## 页面总览

| # | 页面 | 类型 | 参考模板 |
| --- | --- | --- | --- |
| 1 | 封面 · AI 厨娘·智能烹饪助手 | Cover | cover/business/059 |
| 2 | 目录 CONTENTS（四章 + 页数标签） | TOC | toc/business/3546 |
| 3 | 过渡 01 · 项目概述与技术架构 | Transition | transition/business/536 |
| 4 | 项目背景与产品定位（四痛点 / 定位 / 技术主张） | Content | content/tech/1675 |
| 5 | 协作模式与交付物（四约定 / B-D1~D8 / 交付节奏） | Content | content/business/1532 |
| 6 | 交付成果核心指标（4 KPI + 三端明细 + 质量） | Content | content/business/1534 |
| 7 | 系统架构总览（五层 + 六条硬约束） | Content | content/business/1536 |
| 8 | 技术栈选型（四类 + 部署方式） | Content | content/tech/1679 |
| 9 | 数据与语料资产（语料 / 27 条规则 / 合规待办） | Content | content/business/1538 |
| 10 | 过渡 02 · 重点模块与精彩代码 | Transition | transition/business/536 |
| 11 | 重点模块① 智能菜谱推荐（5 节点链 + 召回/过滤/排序三卡） | Content | content/tech/1673 |
| 12 | **LangGraph 编排图结构 · 主图**（22 节点全拓扑） | Content | 自绘 SVG 拓扑 |
| 13 | **LangGraph 子图与关键路径**（推荐子图并行 + 创新状态机 + 边语义） | Content | 自绘 SVG + 卡片 |
| 14 | 其余核心能力速览（F/G/H/J/C/语音 六卡） | Content | content/business/1537 |
| 15 | 重点模块② 食品安全与过敏原风控（四铁律 + 架构位置 + 实测证据） | Content | content/tech/1682 |
| 16 | 精彩代码① 三路召回与布尔硬过滤 | Content | content/tech/1587（浅色化改造） |
| 17 | 精彩代码② 风控短路与节点动态装配 | Content | content/tech/1587（浅色化改造） |
| 18 | 功能演示 · 真实界面（2×2 真实截图） | Content | content/tech/1675 |
| 19 | 过渡 03 · 问题与解决方案 | Transition | transition/business/536 |
| 20 | 问题与解决方案总览（六类 × 问题/方案/结果） | Content | content/business/1531 |
| 21 | 关键问题深剖（四案例四段式） | Content | content/tech/1680 |
| 22 | 过渡 04 · 项目完成后的收获 | Transition | transition/business/536 |
| 23 | 项目完成后的收获（五项成长 + 总结 + 下一步） | Content | content/tech/1690 |
| 24 | 结束页 · 谢谢 | Ending | ending/business/1052 |

> 说明：第 12、13 页的 LangGraph 拓扑图为本项目自绘 SVG（模板库无对应图形），其余内容页均以浅色模板的版式语言为基准重写。

---

## 关键页面内容要点

### Page 12 ｜ LangGraph 编排图结构 · 主图（★ 本轮新增重点）
- **节点规模**：22 个（主图 13 + 子图 9），全图**仅 1 个 LLM 节点**（supervisor，仅做意图识别）
- **主链路**：START → `intake_guard`（输入风控）→ `supervisor` → 6 个业务分支 → `compose` → `output_guard`（输出风控）→ `finalize` → END
- **6 个业务分支**：`subgraph_recommend` / `node_free_qa` / `node_inventory_op` / `node_nutrition_query` / `node_cooking_help` / `node_innovation_entry`
- **三类条件边**：① 输入风控否决 → 短路；② supervisor 否决 → 短路；③ output_guard 否决 → 短路；异常/超时 → `safe_mode_handler`
- **3 个终止出口**：`finalize`（正常）｜`emit_safety_response`（安全短路）｜`safe_mode_handler`（保守模式）
- **配色约定**：风控节点橙色、supervisor 深青实心、业务节点白底青边、短路路径红色虚线、降级路径琥珀虚线、通过路径绿色

### Page 13 ｜ LangGraph 子图与关键路径（★ 本轮新增重点）
- **推荐子图**：`assemble_context` → `recipe_retrieve` → `hard_filter` →（`recipe_rank` ∥ `node_nutrition`）并行汇合
- **创新子图**：单向状态机 `precheck → generate → adopted → indexed → removed`，由 `_VALID_TRANSITIONS` 硬校验，非法流转 422
- **三类边的语义**：普通边（顺序推进）/ 条件边（短路到安全响应）/ 并行分支（同时展开、失败互不影响）
- **复合意图**：同时含推荐与营养诉求 → 路由到复合节点复用推荐子图，营养由并行分支覆盖

### 其余页面
内容与前版保持一致的口径与数据来源，仅做两处调整：① 文字加厚（每页 100–200 字正文、2–3 句解释）；② 全篇改为浅色配色。
