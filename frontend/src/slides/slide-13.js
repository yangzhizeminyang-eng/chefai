window.slideDataMap.set(13, `
  <div class="w-[1440px] h-[810px] relative overflow-hidden slide-bg">
    <div class="absolute top-0 left-0 w-full h-[8px] bg-orange-600"></div>
    <div class="w-[1350px] h-[720px] mx-auto my-[45px] relative pt-3 flex flex-col">

      <div class="flex items-center justify-between mb-3">
        <div class="flex items-center gap-4">
          <div class="w-[6px] h-10 bg-orange-600 rounded"></div>
          <div>
            <h2 class="text-[34px] font-bold text-slate-900 leading-tight">LangGraph 路由机制与两张子图</h2>
            <p class="text-[14px] text-slate-500 mt-0.5">3 个路由函数（确定性、零 LLM 参与）· INTENT_ROUTES 10 类意图 · 推荐子图 5 节点 / 创新子图 4 节点</p>
          </div>
        </div>
        <span class="px-3.5 py-1.5 bg-cyan-50 border border-cyan-200 text-cyan-800 rounded-full text-[12px] font-medium">三张 StateGraph 均裸编译 · 无 checkpointer / 无 interrupt</span>
      </div>

      <div class="flex gap-4 flex-1">
        <div class="w-[47%] flex flex-col gap-3">
          <div class="bg-white border border-slate-200 rounded-xl p-3.5 shadow-sm">
            <h3 class="text-[16px] font-bold text-slate-800 mb-2">三个路由函数 · 挂载点 / 白名单 / 判定</h3>
            <div class="space-y-1.5">
              <div class="bg-slate-50 rounded-lg px-3 py-1.5">
                <div class="flex items-center justify-between mb-0.5">
                  <span class="text-[11.5px] font-mono font-bold text-cyan-700">route_after_intake_guard</span>
                  <span class="text-[10.5px] text-slate-400">挂在 intake_guard</span>
                </div>
                <p class="text-[11px] text-slate-600 leading-snug">UNKNOWN→保守模式 ｜ hit→否决出口 ｜ 否则放行 supervisor</p>
              </div>
              <div class="bg-slate-50 rounded-lg px-3 py-1.5">
                <div class="flex items-center justify-between mb-0.5">
                  <span class="text-[11.5px] font-mono font-bold text-cyan-700">route_after_supervisor</span>
                  <span class="text-[10.5px] text-slate-400">挂在 supervisor</span>
                </div>
                <p class="text-[11px] text-slate-600 leading-snug">intent==__veto__→否决出口 ｜ 否则查 INTENT_ROUTES，未命中兜底 node_free_qa</p>
              </div>
              <div class="bg-slate-50 rounded-lg px-3 py-1.5">
                <div class="flex items-center justify-between mb-0.5">
                  <span class="text-[11.5px] font-mono font-bold text-cyan-700">route_after_output_guard</span>
                  <span class="text-[10.5px] text-slate-400">挂在 output_guard</span>
                </div>
                <p class="text-[11px] text-slate-600 leading-snug">UNKNOWN→保守模式 ｜ hit&amp;&amp;block→否决 ｜ hit&amp;&amp;!block→放行 finalize</p>
              </div>
            </div>
            <p class="text-[11px] text-slate-500 leading-snug mt-2 pt-2 border-t border-slate-100">
              <span class="font-semibold text-slate-700">关键设计点：</span>LLM 只输出意图标签，「意图 → 节点」映射由代码字典固定，模型无权决定调用哪个工具。
            </p>
          </div>

          <div class="bg-white border border-slate-200 rounded-xl p-3.5 shadow-sm flex-1 flex flex-col">
            <div class="flex items-center justify-between mb-2">
              <h3 class="text-[16px] font-bold text-slate-800">INTENT_ROUTES 全量映射</h3>
              <span class="text-[10.5px] text-slate-400 font-mono">10 类 · 无遗漏 / 无多余</span>
            </div>
            <div class="grid grid-cols-2 gap-x-3 gap-y-[5px] flex-1">
              <div class="flex items-center justify-between bg-slate-50 rounded px-2.5 py-1.5">
                <span class="text-[10.5px] font-mono text-slate-700">recommend_by_ingredients</span><span class="text-[10px] font-mono text-cyan-700">→ recommend</span>
              </div>
              <div class="flex items-center justify-between bg-slate-50 rounded px-2.5 py-1.5">
                <span class="text-[10.5px] font-mono text-slate-700">search_recipe</span><span class="text-[10px] font-mono text-cyan-700">→ recommend</span>
              </div>
              <div class="flex items-center justify-between bg-cyan-50 rounded px-2.5 py-1.5">
                <span class="text-[10.5px] font-mono text-cyan-800">composite_recommend_nutrition</span><span class="text-[10px] font-mono text-cyan-700">→ recommend</span>
              </div>
              <div class="flex items-center justify-between bg-slate-50 rounded px-2.5 py-1.5">
                <span class="text-[10.5px] font-mono text-slate-700">nutrition_query</span><span class="text-[10px] font-mono text-slate-600">→ nutrition_query</span>
              </div>
              <div class="flex items-center justify-between bg-slate-50 rounded px-2.5 py-1.5">
                <span class="text-[10.5px] font-mono text-slate-700">cooking_help</span><span class="text-[10px] font-mono text-slate-600">→ cooking_help</span>
              </div>
              <div class="flex items-center justify-between bg-slate-50 rounded px-2.5 py-1.5">
                <span class="text-[10.5px] font-mono text-slate-700">inventory_op</span><span class="text-[10px] font-mono text-slate-600">→ inventory_op</span>
              </div>
              <div class="flex items-center justify-between bg-slate-50 rounded px-2.5 py-1.5">
                <span class="text-[10.5px] font-mono text-slate-700">innovation</span><span class="text-[10px] font-mono text-cyan-700">→ innovation_entry</span>
              </div>
              <div class="flex items-center justify-between bg-slate-50 rounded px-2.5 py-1.5">
                <span class="text-[10.5px] font-mono text-slate-700">photo_recognize</span><span class="text-[10px] font-mono text-slate-600">→ node_free_qa</span>
              </div>
              <div class="flex items-center justify-between bg-slate-50 rounded px-2.5 py-1.5">
                <span class="text-[10.5px] font-mono text-slate-700">free_qa</span><span class="text-[10px] font-mono text-slate-600">→ node_free_qa</span>
              </div>
              <div class="flex items-center justify-between bg-slate-50 rounded px-2.5 py-1.5">
                <span class="text-[10.5px] font-mono text-slate-700">smalltalk_or_out_of_scope</span><span class="text-[10px] font-mono text-slate-600">→ node_free_qa</span>
              </div>
            </div>
            <div class="mt-2 bg-amber-50 border border-amber-200 rounded-lg px-3 py-1.5">
              <p class="text-[11px] text-amber-800 leading-snug">
                <span class="font-semibold">LLM 降级：</span>捕获 LLMError 或 JSON 解析失败 → <span class="font-mono text-[10.5px]">_keyword_fallback</span> 关键词兜底（覆盖复合意图与创新意图），trace span 标 <span class="font-mono text-[10.5px]">degraded</span>。
              </p>
            </div>
          </div>
        </div>

        <div class="w-[53%] flex flex-col gap-3">
          <div class="bg-white border border-slate-200 rounded-xl p-3.5 shadow-sm">
            <div class="flex items-center justify-between mb-2">
              <h3 class="text-[16px] font-bold text-slate-800">推荐子图 <span class="font-mono text-cyan-700 text-[14px]">subgraph_recommend</span></h3>
              <span class="text-[10.5px] px-2.5 py-1 bg-cyan-50 border border-cyan-200 text-cyan-800 rounded-full">5 节点 · 已注册进主图 · recursion_limit 40</span>
            </div>
            <div class="relative" style="width:700px;height:118px;">
              <svg width="700" height="118" class="absolute left-0 top-0">
                <defs><marker id="sg-a" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6 z" fill="#64748B"/></marker></defs>
                <path d="M58,50 L70,50" stroke="#64748B" stroke-width="1.5" fill="none" marker-end="url(#sg-a)"/>
                <path d="M184,50 L196,50" stroke="#64748B" stroke-width="1.5" fill="none" marker-end="url(#sg-a)"/>
                <path d="M310,50 L322,50" stroke="#64748B" stroke-width="1.5" fill="none" marker-end="url(#sg-a)"/>
                <path d="M428,50 L446,50" stroke="#64748B" stroke-width="1.5" fill="none"/>
                <path d="M446,24 L446,88" stroke="#64748B" stroke-width="1.5" fill="none"/>
                <path d="M446,24 L460,24" stroke="#64748B" stroke-width="1.5" fill="none" marker-end="url(#sg-a)"/>
                <path d="M446,88 L460,88" stroke="#64748B" stroke-width="1.5" fill="none" marker-end="url(#sg-a)"/>
                <path d="M572,24 L590,24" stroke="#64748B" stroke-width="1.5" fill="none"/>
                <path d="M572,88 L590,88" stroke="#64748B" stroke-width="1.5" fill="none"/>
                <path d="M590,24 L590,88" stroke="#64748B" stroke-width="1.5" fill="none"/>
                <path d="M590,50 L612,50" stroke="#64748B" stroke-width="1.5" fill="none" marker-end="url(#sg-a)"/>
              </svg>
              <div class="absolute rounded-md flex items-center justify-center" style="left:0px;top:36px;width:58px;height:28px;background:#1E293B;">
                <span class="text-white text-[9.5px] font-bold font-mono">__start__</span>
              </div>
              <div class="absolute rounded-md border-2 border-cyan-300 bg-cyan-50 flex flex-col items-center justify-center" style="left:72px;top:30px;width:112px;height:40px;">
                <span class="text-[9.5px] font-mono text-cyan-700 leading-none mb-1">assemble_context</span>
                <span class="text-[10px] text-slate-600 leading-none">食材名 / 别名 → ID</span>
              </div>
              <div class="absolute rounded-md border-2 border-sky-300 bg-sky-50 flex flex-col items-center justify-center" style="left:198px;top:30px;width:112px;height:40px;">
                <span class="text-[9.5px] font-mono text-sky-700 leading-none mb-1">recipe_retrieve</span>
                <span class="text-[10px] text-slate-600 leading-none">混合召回 ≤200</span>
              </div>
              <div class="absolute rounded-md border-2 border-orange-300 bg-orange-50 flex flex-col items-center justify-center" style="left:324px;top:30px;width:104px;height:40px;">
                <span class="text-[9.5px] font-mono text-orange-700 leading-none mb-1">hard_filter</span>
                <span class="text-[10px] text-slate-600 leading-none">布尔硬过滤 SQL</span>
              </div>
              <div class="absolute rounded-md border-2 border-indigo-300 bg-indigo-50 flex flex-col items-center justify-center" style="left:462px;top:6px;width:110px;height:36px;">
                <span class="text-[9.5px] font-mono text-indigo-700 leading-none mb-1">recipe_rank</span>
                <span class="text-[10px] text-slate-600 leading-none">7 因子 → Top 8</span>
              </div>
              <div class="absolute rounded-md border-2 border-emerald-300 bg-emerald-50 flex flex-col items-center justify-center" style="left:462px;top:70px;width:110px;height:36px;">
                <span class="text-[9.5px] font-mono text-emerald-700 leading-none mb-1">node_nutrition</span>
                <span class="text-[10px] text-slate-600 leading-none">前 3 道并行估算</span>
              </div>
              <div class="absolute rounded-md flex items-center justify-center border-2 border-slate-300 bg-white" style="left:614px;top:36px;width:60px;height:28px;">
                <span class="text-[9.5px] font-bold font-mono text-slate-600">__end__</span>
              </div>
              <div class="absolute text-[10px] text-slate-400" style="left:432px;top:52px;">并行</div>
            </div>
            <div class="grid grid-cols-2 gap-x-3 gap-y-1 mt-1">
              <p class="text-[11px] text-slate-600 leading-snug"><span class="font-semibold text-slate-700">并行语义：</span>hard_filter 同时 fan-out 两条边，二者在<b>同一 superstep</b> 内并行，都连 END，全部结束后才返回主图 compose。</p>
              <p class="text-[11px] text-slate-600 leading-snug"><span class="font-semibold text-slate-700">并行约束：</span>营养节点无法依赖排序输出，按过滤输出序取前 3 道估算（与最终 Top 重合度高）。</p>
              <p class="text-[11px] text-slate-600 leading-snug"><span class="font-semibold text-slate-700">召回双分支：</span>RETRIEVAL_VECTOR 开关默认 on → pgvector raw SQL / embedding_json 点积，兜底降级不抛错。</p>
              <p class="text-[11px] text-slate-600 leading-snug"><span class="font-semibold text-slate-700">反馈接线：</span>user_id 存在时加载 dislike 惩罚 −0.5 传入 weighted_rank；无 user_id 排序不变。</p>
            </div>
          </div>

          <div class="bg-white border border-slate-200 rounded-xl p-3.5 shadow-sm">
            <div class="flex items-center justify-between mb-2">
              <h3 class="text-[16px] font-bold text-slate-800">创新子图 <span class="font-mono text-orange-600 text-[14px]">innovation</span></h3>
              <span class="text-[10.5px] px-2.5 py-1 bg-orange-50 border border-orange-200 text-orange-700 rounded-full">4 节点 · 纯线性 · 未注册进主图</span>
            </div>
            <div class="relative" style="width:700px;height:76px;">
              <svg width="700" height="76" class="absolute left-0 top-0">
                <defs><marker id="ig-a" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6 z" fill="#64748B"/></marker></defs>
                <path d="M58,38 L70,38" stroke="#64748B" stroke-width="1.5" fill="none" marker-end="url(#ig-a)"/>
                <path d="M208,38 L220,38" stroke="#64748B" stroke-width="1.5" fill="none" marker-end="url(#ig-a)"/>
                <path d="M372,38 L384,38" stroke="#64748B" stroke-width="1.5" fill="none" marker-end="url(#ig-a)"/>
                <path d="M532,38 L544,38" stroke="#64748B" stroke-width="1.5" fill="none" marker-end="url(#ig-a)"/>
              </svg>
              <div class="absolute rounded-md flex items-center justify-center" style="left:0px;top:24px;width:58px;height:28px;background:#1E293B;">
                <span class="text-white text-[9.5px] font-bold font-mono">__start__</span>
              </div>
              <div class="absolute rounded-md border-2 border-red-300 bg-red-50 flex flex-col items-center justify-center" style="left:72px;top:20px;width:136px;height:36px;">
                <span class="text-[9.5px] font-mono text-red-700 leading-none mb-1">innovation_precheck</span>
                <span class="text-[10px] text-red-600 leading-none">🔴 安全前置红线</span>
              </div>
              <div class="absolute rounded-md border border-slate-300 bg-white flex flex-col items-center justify-center" style="left:222px;top:20px;width:150px;height:36px;">
                <span class="text-[9.5px] font-mono text-slate-700 leading-none mb-1">innovation_property_match</span>
                <span class="text-[10px] text-slate-500 leading-none">食材五属性查表</span>
              </div>
              <div class="absolute rounded-md border-2 border-red-300 bg-red-50 flex flex-col items-center justify-center" style="left:386px;top:20px;width:146px;height:36px;">
                <span class="text-[9.5px] font-mono text-red-700 leading-none mb-1">innovation_pairing_check</span>
                <span class="text-[10px] text-red-600 leading-none">🔴 搭配结论必须查表</span>
              </div>
              <div class="absolute rounded-md border border-slate-300 bg-white flex flex-col items-center justify-center" style="left:544px;top:20px;width:136px;height:36px;">
                <span class="text-[9.5px] font-mono text-slate-700 leading-none mb-1">innovation_generate</span>
                <span class="text-[10px] text-slate-500 leading-none">受约束生成 + 落库</span>
              </div>
            </div>
            <div class="space-y-0.5 mt-0.5">
              <p class="text-[11px] text-slate-600 leading-snug"><span class="font-semibold text-slate-700">非 LangGraph 子图：</span>它不是主图的子图节点，而是被命令式调用 —— entry 节点 → run_innovation_precheck() + run_innovation_generate() → invoke 子图；同一组函数也被 API 层直接调用，共 <b>3 个调用入口</b>。</p>
              <p class="text-[11px] text-slate-600 leading-snug"><span class="font-semibold text-slate-700">precheck 红线：</span>食材逐个过风控扫描（避免安全食材拼接误伤组合规则）→ 过敏原交集非空直接拒绝 → 特殊人群 + 高危食材拒绝 → taboo 命中拒绝；<b>UNKNOWN / 查表异常一律保守拦截（宁拦不放）</b>。</p>
              <p class="text-[11px] text-slate-600 leading-snug"><span class="font-semibold text-slate-700">generation 约束：</span>用量 100% 量化（禁「适量 / 少许」）、步骤含时长字段 → 违例重试一次 → 再违例降级本地模板；LLM 硬超时 80.0s；blocked=True 后三个下游节点直接返回 status="skipped"。</p>
            </div>
          </div>

          <div class="bg-slate-900 rounded-xl p-3.5 shadow-sm flex-1">
            <h3 class="text-[15px] font-bold text-white mb-1.5">父子图状态隔离（关键工程约束 · 源码明确记载「已实测踩坑」）</h3>
            <div class="flex gap-2 mb-1.5">
              <span class="px-2.5 py-1 bg-white/10 border border-white/15 rounded-md text-[10.5px] font-mono text-slate-200">主图 CookingState.trace</span>
              <span class="px-2.5 py-1 bg-white/10 border border-white/15 rounded-md text-[10.5px] font-mono text-slate-200">推荐子图 RecommendSubgraphState.sub_trace</span>
              <span class="px-2.5 py-1 bg-white/10 border border-white/15 rounded-md text-[10.5px] font-mono text-slate-200">创新子图 InnovationState.sub_trace</span>
            </div>
            <p class="text-[11px] text-slate-300 leading-snug">
              <b>原因：</b>若子图复用同名 trace 通道，子图会把继承自主图的 span 原样写回，再经主图 <span class="font-mono text-[10.5px]">operator.add</span> 累加 → trace 重复。
              <b class="text-emerald-400">运行期验证：</b>一次正常推荐落库 11 行 trace，无重复 span，隔离机制生效。
            </p>
          </div>
        </div>
      </div>

      <div class="mt-2.5 flex items-center justify-between text-[12px] text-slate-400">
        <span class="font-mono tracking-wider">AI 厨娘 · 智能烹饪助手 · 项目答辩</span>
        <span class="font-mono">13 / 25</span>
      </div>
    </div>
  </div>
`);
