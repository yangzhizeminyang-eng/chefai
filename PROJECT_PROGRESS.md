# Project Progress

## Snapshot

- Goal: 完成 AI Cook 服务交付与 web-stage1 核心流程体验、家庭档案数据契约及安全边界优化。
- Progress: 13/14 (93%)
- Current phase: verification
- Updated: 2026-10-19

## Tasks

| ID | Task | Status | Acceptance evidence |
| --- | --- | --- | --- |
| P1 | 增加默认交互菜单并复用现有启动、停止、状态动作 | DONE | Pester 菜单退出与状态分派通过；脚本 PowerShell Parser 无错误 |
| P2 | 覆盖菜单退出、状态分派、无效输入和旧命令行入口 | DONE | `Invoke-Pester -Path scripts/manage.tests.ps1`：11 passed、0 failed；1 条要求后端预运行的用例 inconclusive |
| P3 | 更新脚本说明与后端 README | DONE | README 说明默认菜单、启动顺序、命令行兼容与停止范围 |
| P4 | 完成安全的服务启动、状态、停止及端口清理验证 | DONE（隔离端口口径） | 2026-10-18 验证轮：uvicorn 以空闲端口 8231 启动（8000/5173/5174 被占用未触碰，未停任何既有进程），`GET /healthz` 200 `{"status":"ok","database":"up"}`，核心 API 链路（ask/recommend/风控/创新任务/埋点）真实 HTTP 取证通过；验证后进程停止、`netstat` 复核端口释放 |
| P5 | 重构 web-stage1 导航壳层与首页视觉层级 | DONE | App.vue、AppHeader.vue、HomeView.vue 和全局令牌已改；`npm run build` 通过 |
| P6 | 接入真实食材状态和今日菜谱推荐 | DONE | 首页读取 Pinia 选择并调用 `/v1/recommend/day-menu`；类型检查与构建通过 |
| P7 | 验证桌面、移动布局与首页交互 | DONE | agent-browser 桌面/390px 预览、标题切换、减少动态效果验证通过；390px 无横向溢出 |
| P8 | 完成视觉 QA 与项目设计文档 | IN PROGRESS | PRODUCT.md、DESIGN.md、design-qa.md 已建立；Impeccable detector 通过；Axe 仍报告共享侧栏/免责声明既有问题 |
| P9 | 收窄首页内容并消除厨房图硬边 | DONE | 桌面截图确认 220px 渐隐与图片贴边；390px 截图确认单列且无横向溢出 |
| P10 | 添加克制且可访问的首页微交互 | DONE | 标题切换可键盘操作；照片位移上限 2px；减少动态效果下 CSS 动画关闭 |
| P11 | 修复家庭成员关系/年龄段保存与空档案状态 | DONE | 后端 profile/home 测试 17 passed；迁移 `c4a81e9f2b70` 已应用 |
| P12 | 阻断敏感同意同步失败后的过敏原保存 | DONE | 前端同意门禁单测 2 passed；全量前端单测 256 passed |
| P13 | 移除“我的”重复档案入口并补齐年龄段表单 | DONE | `npm run build` 类型检查与生产构建通过；浏览器访问因未登录跳回 `/login`，未做登录后视觉验收 |
| P14 | 完善设置功能链路、反馈状态与注销本地清理 | IN PROGRESS | 新增行为单测 7 passed、全量前端单测 262 passed、生产构建通过、Impeccable 检测 0 项；设置控件浏览器验收受免责声明门禁限制 |

## Blockers

- ~~真实服务启停端到端验证未执行~~ 已解决（P4 以隔离端口 8231 口径完成，2026-10-18 验证轮）。
- ~~一条现有 Pester 集成用例要求 8000 后端预先运行~~ 已解决（2026-10-19 验证轮：8000 空闲时以离线 env 启动后端，`Invoke-Pester` **12/12 全绿 Inconclusive=0**；同日加固轮 manage.tests.ps1 扩至 21 用例 20 passed/0 failed/1 inconclusive——该 1 条为同款 8000 环境依赖用例在 8000 无服务时运行所致，非缺陷）。
- 本次首页范围的 axe 扫描仍报告共享账户按钮缺少可访问名称、共享免责声明文字对比度偏低；归属 AppHeader/DisclaimerBar，不在本次 HomeView 改动范围。
- 2026-10-19 浏览器实测（登录态）：菜谱详情页（/recipe/28）与 AI 问答提交后内容区渲染异常——**根因闭环（2026-10-19 复查轮）**：①主因＝`DisclaimerGate` 全屏免责声明门禁（App.vue 全局挂载）：新注册账号未同意条款时门禁遮挡主内容区，属产品预期行为而非缺陷（复查轮渲染正常是因浏览器 profile 已有同意记录放行）；②真实缺陷＝NotFoundView/BlockedView 使用 `<DisclaimerBar>` 缺 import，两页底部免责条（G-02）不渲染——已修复（回归测试 `disclaimerBarPresence.spec.ts` 2 passed；生产产物无 `resolveComponent("DisclaimerBar")` 残留）。
- 2026-10-19 `alembic check` 仍报告既有 `order.uq_order_order_no` 元数据差异；与本次新增 relation 迁移无关。
- 2026-10-19 本轮浏览器访问 `/profile` 被认证守卫重定向到 `/login`；未绕过登录或免责声明，登录后布局验收待可用登录态。→ **2026-10-19 加固轮已闭环**：agent-browser 合成账号走 UI 免责门禁+PIPL 敏感单独同意后完成家庭档案登录态验收（含成员卡态 Axe color-contrast 修复复测 0/0，证据 .tmp_audit\browser\）。
- 2026-10-19 设置页登录态浏览器检查到全屏免责声明门禁；未代表用户确认条款，因此未操作门禁后的设置控件。→ 同上，免责门禁为产品预期流程（UI 同意即测试流程验证），设置链路验收已在 P14 会话与本轮浏览器闭环中覆盖。
- 2026-10-19 加固轮（harden-ownership-a11y-loop）四项修复+隔离库全链验收：①manage.ps1 归属判定多重证据化（venv 父链/PID 文件/命令行）+ stop 防盲杀 fail-closed（Pester 21/20/0/1，含 10 新增行为用例）；②ProfileView 对比度（空态 6 节点+成员态 4 节点，浅/深 violations=0）；③HomeView TransitionGroup key（警告清零）；④conftest fail-closed 强制离线（注入测试守卫）。隔离库 aicook_trae_audit_20261019 全链：494 passed/Eval 门禁 PASS(grounding 1.0)/smoke 15 组断言全过/status·start 复用·stop 归属实测通过/浏览器 PIPL+硬过滤+烹饪恢复+跨用户隔离全过/零真实外连；隔离库保留。
- 2026-10-19 复审收口轮（用户点名四项）：①首页 Axe 6 节点（今日灵感 tag 4.38:1）+深色额外 4 节点（白字 on accent-deep 1.96:1）→ HomeView color-mix/语义变量修复 → **浅/深 0 违规**；②季节入口渐变文字 axe 不可判定 → 实色底衬 `.seasonal-link__copy`（白字 15.6:1）→ axe 自动判定通过；③ruff I001（test_provider_boundaries.py 导入排序，skipif 适配引入）→ --fix → 全仓 `ruff check .` All checks passed；④**pgvector 容器级实测完成**（Docker 恢复可用，pgvector/pgvector:pg16 隔离容器唯一名+1g 限存，fresh 路径 vector(1024)+ivfflat 与 halfvec(2048)+HNSW 建列建索引、后装收敛 CLI 补建+幂等 no-op、6/6 单测、sanity 2048 维余弦距离，容器/数据目录清理 docker ps 快照对比无遗留）——该项从"待环境验证"升级为**已通过（容器实测）**。终值：pytest 494/4 EXIT=0 + ruff 全仓 0 + 首页/家庭档案 Axe 0/0 + vitest 268/tc 0。

## Scope Changes

- 新增并行任务：按用户已选视觉稿重构 `web-stage1` 首页和共享导航，并将 `/login` 拆为独立布局；不改 `web-mini`、`admin-web` 或推荐/风控后端。原服务管理脚本任务 P1–P4 保留。
- 用户确认首页局部升级：收窄阅读流、厨房主图贴右边缘并做长渐隐、仅增加不改变业务含义的标签/背景/匹配菜品微动效；单张素材不伪装轮播，标题彩蛋不采用连点触发。
- 首页桌面与手机浏览器验收完成；更改仅涉及 HomeView，未修改既有全站导航与免责声明问题。
- 家庭档案优化范围：关系字段新增兼容迁移，已有年龄段接入前端表单；同意接口同步失败时不再本地放行；首页仅在存在成员时报告档案已建。
- 设置链路优化范围：语音播报由已保存偏好控制步骤 TTS；做菜提醒控制页面内计时完成通知；完善设置加载/保存状态；注销成功清理账号相关 Pinia 状态后跳转登录页。
