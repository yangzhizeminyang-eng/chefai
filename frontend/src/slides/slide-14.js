window.slideDataMap.set(14, `
  <div class="w-[1440px] h-[810px] relative overflow-hidden slide-bg">
    <div class="absolute top-0 left-0 w-full h-[8px] bg-orange-600"></div>
    <div class="w-[1350px] h-[720px] mx-auto my-[45px] relative pt-3 flex flex-col">

      <div class="flex items-center justify-between mb-3">
        <div class="flex items-center gap-4">
          <div class="w-[6px] h-10 bg-orange-600 rounded"></div>
          <div>
            <h2 class="text-[34px] font-bold text-slate-900 leading-tight">图结构运行期校验与自检发现</h2>
            <p class="text-[14px] text-slate-500 mt-0.5">编译并导出拓扑 + 真实调用链路埋点验证 · 图结构单测 18 passed · 同步产出 9 项结构性发现</p>
          </div>
        </div>
        <div class="flex gap-2">
          <span class="px-3.5 py-1.5 bg-emerald-50 border border-emerald-200 text-emerald-700 rounded-full text-[12px] font-medium">拓扑红线全部成立</span>
          <span class="px-3.5 py-1.5 bg-emerald-50 border border-emerald-200 text-emerald-700 rounded-full text-[12px] font-medium">18 passed</span>
          <span class="px-3.5 py-1.5 bg-amber-50 border border-amber-200 text-amber-700 rounded-full text-[12px] font-medium">9 项发现已登记</span>
        </div>
      </div>

      <div class="grid grid-cols-3 gap-3.5 mb-3">
        <div class="bg-white border border-slate-200 border-t-4 border-t-emerald-500 rounded-xl p-3.5 shadow-sm">
          <div class="flex items-center justify-between mb-1.5">
            <span class="text-[12.5px] font-mono font-bold text-emerald-700">finalize</span>
            <span class="text-[10.5px] px-2 py-0.5 bg-emerald-50 border border-emerald-200 text-emerald-700 rounded-full">正常路径出口</span>
          </div>
          <p class="text-[11px] text-slate-500 mb-1">触发：正常通过双侧闸门</p>
          <p class="text-[11px] text-slate-600 leading-snug mb-1"><span class="font-semibold text-slate-700">响应：</span>request_id / results / filtered_by / qa_answer / notice / partial_failures / disclaimer_id / trace_id</p>
          <p class="text-[11px] text-slate-600 leading-snug"><span class="font-semibold text-slate-700">取证：</span>全量 span + 自身 span</p>
        </div>

        <div class="bg-white border border-slate-200 border-t-4 border-t-red-500 rounded-xl p-3.5 shadow-sm">
          <div class="flex items-center justify-between mb-1.5">
            <span class="text-[12.5px] font-mono font-bold text-red-700">emit_safety_response</span>
            <span class="text-[10.5px] px-2 py-0.5 bg-red-50 border border-red-200 text-red-700 rounded-full">否决 / 澄清出口</span>
          </div>
          <p class="text-[11px] text-slate-500 mb-1">触发：入口 hit（含伪科学 block=false 的澄清）或出口 hit &amp;&amp; block</p>
          <p class="text-[11px] text-slate-600 leading-snug mb-1"><span class="font-semibold text-slate-700">响应：</span><b>仅 6 个安全字段</b>，绝不含 results / candidates / nutrition</p>
          <p class="text-[11px] text-slate-600 leading-snug"><span class="font-semibold text-slate-700">取证：</span>为缺失业务节点补 not_executed，output_guard 与 finalize 补 skipped_by_veto，并写 risk_log</p>
        </div>

        <div class="bg-white border border-slate-200 border-t-4 border-t-amber-500 rounded-xl p-3.5 shadow-sm">
          <div class="flex items-center justify-between mb-1.5">
            <span class="text-[12.5px] font-mono font-bold text-amber-700">safe_mode_handler</span>
            <span class="text-[10.5px] px-2 py-0.5 bg-amber-50 border border-amber-200 text-amber-700 rounded-full">保守模式出口</span>
          </div>
          <p class="text-[11px] text-slate-500 mb-1">触发：任一闸门 status=UNKNOWN</p>
          <p class="text-[11px] text-slate-600 leading-snug mb-1"><span class="font-semibold text-slate-700">响应：</span>safe_mode=true + TXT-G06 固定话术</p>
          <p class="text-[11px] text-slate-600 leading-snug"><span class="font-semibold text-slate-700">取证：</span>业务节点与 output_guard 补 not_executed，并写 risk_log(action="safe_mode")</p>
        </div>
      </div>

      <div class="flex gap-3.5 flex-1">
        <div class="w-[56%] bg-white border border-slate-200 rounded-xl p-3.5 shadow-sm flex flex-col">
          <div class="flex items-center justify-between mb-2">
            <h3 class="text-[16px] font-bold text-slate-800">结构健康度小结</h3>
            <span class="text-[10.5px] text-slate-400 font-mono">✅ 成立 ／ ⚠️ 部分 ／ ❌ 未落地</span>
          </div>
          <div class="space-y-[5px] flex-1">
            <div class="flex items-start gap-2 bg-slate-50 rounded-lg px-3 py-[7px]">
              <span class="text-[11.5px] leading-snug">✅</span><span class="text-[11.5px] font-semibold text-slate-700 w-[96px] flex-shrink-0">拓扑红线</span>
              <span class="text-[11.5px] text-slate-600 leading-snug">全部成立：无绕闸路径、无直连 END、全节点可达、白名单闭合</span>
            </div>
            <div class="flex items-start gap-2 bg-slate-50 rounded-lg px-3 py-[7px]">
              <span class="text-[11.5px] leading-snug">✅</span><span class="text-[11.5px] font-semibold text-slate-700 w-[96px] flex-shrink-0">可测试性</span>
              <span class="text-[11.5px] text-slate-600 leading-snug">图结构断言已落单测（关键节点 / END 入边 / 否决体纯净），18 passed</span>
            </div>
            <div class="flex items-start gap-2 bg-slate-50 rounded-lg px-3 py-[7px]">
              <span class="text-[11.5px] leading-snug">✅</span><span class="text-[11.5px] font-semibold text-slate-700 w-[96px] flex-shrink-0">状态隔离</span>
              <span class="text-[11.5px] text-slate-600 leading-snug">子图 sub_trace 隔离有效，一次推荐落库 11 行 trace 无重复</span>
            </div>
            <div class="flex items-start gap-2 bg-slate-50 rounded-lg px-3 py-[7px]">
              <span class="text-[11.5px] leading-snug">⚠️</span><span class="text-[11.5px] font-semibold text-slate-700 w-[96px] flex-shrink-0">可插拔 NFR-4.1</span>
              <span class="text-[11.5px] text-slate-600 leading-snug">仅节点实现可插拔，新增节点仍需手改 main_graph.py 的边与白名单</span>
            </div>
            <div class="flex items-start gap-2 bg-rose-50 border border-rose-100 rounded-lg px-3 py-[7px]">
              <span class="text-[11.5px] leading-snug">❌</span><span class="text-[11.5px] font-semibold text-rose-700 w-[96px] flex-shrink-0">超时治理</span>
              <span class="text-[11.5px] text-rose-700/90 leading-snug">注册表 timeout_ms 未接入执行，超时与降级矩阵未落地</span>
            </div>
            <div class="flex items-start gap-2 bg-slate-50 rounded-lg px-3 py-[7px]">
              <span class="text-[11.5px] leading-snug">⚠️</span><span class="text-[11.5px] font-semibold text-slate-700 w-[96px] flex-shrink-0">取证完整性</span>
              <span class="text-[11.5px] text-slate-600 leading-snug">node_innovation_entry 缺 not_executed 补标，否决 trace 取证有缺口</span>
            </div>
            <div class="flex items-start gap-2 bg-slate-50 rounded-lg px-3 py-[7px]">
              <span class="text-[11.5px] leading-snug">⚠️</span><span class="text-[11.5px] font-semibold text-slate-700 w-[96px] flex-shrink-0">trace 一致性</span>
              <span class="text-[11.5px] text-slate-600 leading-snug">创新链路自生成 trace_id，同一请求被拆成两个 thread_id</span>
            </div>
            <div class="flex items-start gap-2 bg-slate-50 rounded-lg px-3 py-[7px]">
              <span class="text-[11.5px] leading-snug">⚠️</span><span class="text-[11.5px] font-semibold text-slate-700 w-[96px] flex-shrink-0">冗余执行</span>
              <span class="text-[11.5px] text-slate-600 leading-snug">创新主图路径上 precheck 被重复执行 3 轮</span>
            </div>
            <div class="flex items-start gap-2 bg-slate-50 rounded-lg px-3 py-[7px]">
              <span class="text-[11.5px] leading-snug">⚠️</span><span class="text-[11.5px] font-semibold text-slate-700 w-[96px] flex-shrink-0">文档一致性</span>
              <span class="text-[11.5px] text-slate-600 leading-snug">设计文档与实现存在多处漂移（子图清单 / checkpointer / 意图类数）</span>
            </div>
          </div>
        </div>

        <div class="w-[44%] flex flex-col gap-3">
          <div class="bg-white border border-slate-200 rounded-xl p-3.5 shadow-sm flex-1">
            <div class="flex items-center justify-between mb-2">
              <h3 class="text-[16px] font-bold text-slate-800">9 项自检发现 · 按修复优先级</h3>
              <span class="text-[10.5px] text-slate-400 font-mono">均为运行期实测确认</span>
            </div>
            <div class="space-y-[6px]">
              <div class="bg-red-50 border-l-4 border-l-red-500 rounded-lg px-3 py-1.5">
                <p class="text-[12px] font-bold text-red-700 mb-0.5">P0 · BUSINESS_NODE_NAMES 追加未生效</p>
                <p class="text-[11px] text-red-700/90 leading-snug">对模块自身命名空间重绑定（import 是值拷贝），common 与 guards 的清单都不受影响 → 否决 trace 漏补该节点；改动量极小但直接影响取证链完整性</p>
              </div>
              <div class="bg-amber-50 border-l-4 border-l-amber-500 rounded-lg px-3 py-1.5">
                <p class="text-[12px] font-bold text-amber-700 mb-0.5">P1 · 创新路径 precheck 重复执行 3 次</p>
                <p class="text-[11px] text-amber-700/90 leading-snug">主图节点 → generate 内部 → 子图节点各跑一遍，纯浪费 DB 往返与规则匹配（功能无错，延迟与负载被放大）</p>
              </div>
              <div class="bg-amber-50 border-l-4 border-l-amber-500 rounded-lg px-3 py-1.5">
                <p class="text-[12px] font-bold text-amber-700 mb-0.5">P1 · 创新子图 trace_id 断裂</p>
                <p class="text-[11px] text-amber-700/90 leading-snug">子图自生成 trace_id 与主图不同 → 按 thread_id 做会话级回放会断裂（按 request_id 查询仍可命中）</p>
              </div>
              <div class="bg-sky-50 border-l-4 border-l-sky-500 rounded-lg px-3 py-1.5">
                <p class="text-[12px] font-bold text-sky-700 mb-0.5">P2 · 注册表 timeout_ms / forms 从未被消费</p>
                <p class="text-[11px] text-sky-700/90 leading-snug">全仓库零读取点 → 超时矩阵未强制执行，声明与实际约束能力不一致，易被误读为已实现</p>
              </div>
              <div class="bg-slate-50 border-l-4 border-l-slate-400 rounded-lg px-3 py-1.5">
                <p class="text-[12px] font-bold text-slate-700 mb-0.5">P3 · 5 项文档与实现漂移</p>
                <p class="text-[11px] text-slate-600 leading-snug">state.safe_mode 只写不读 · 三图均无 checkpointer / interrupt · 设计文档描述的子图大部分不存在 · 若干 docstring 与实现不一致 · 否决 trace 中包装节点未补标</p>
              </div>
            </div>
          </div>

          <div class="bg-slate-900 rounded-xl p-3.5 shadow-sm">
            <h3 class="text-[14px] font-bold text-white mb-1.5">两个运行期取证案例</h3>
            <p class="text-[11px] text-slate-300 leading-snug mb-1">
              <span class="font-mono text-red-300">一票否决</span>　「木耳泡一晚上明天炒行吗」→ 落库 <b class="text-white">15 行</b> trace：业务节点全为 not_executed，响应键恰为 6 个安全字段，无业务字段泄漏。
            </p>
            <p class="text-[11px] text-slate-300 leading-snug">
              <span class="font-mono text-amber-300">伪科学澄清</span>　「豆腐和菠菜一起吃会相克吗」→ 走同一出口但 blocked=false、risk=PS-001 → 返回<b class="text-white">科普澄清</b>而非拦截。
            </p>
          </div>
        </div>
      </div>

      <div class="mt-2.5 flex items-center justify-between text-[12px] text-slate-400">
        <span class="font-mono tracking-wider">AI 厨娘 · 智能烹饪助手 · 项目答辩</span>
        <span class="font-mono">14 / 25</span>
      </div>
    </div>
  </div>
`);
