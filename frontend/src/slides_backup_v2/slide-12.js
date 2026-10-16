window.slideDataMap.set(12, `
  <div class="w-[1440px] h-[810px] relative overflow-hidden slide-bg">
    <div class="absolute top-0 left-0 w-full h-[8px] bg-orange-600"></div>
    <div class="w-[1350px] h-[720px] mx-auto my-[45px] relative pt-3 flex flex-col">

      <div class="flex items-center justify-between mb-3">
        <div class="flex items-center gap-4">
          <div class="w-[6px] h-10 bg-orange-600 rounded"></div>
          <div>
            <h2 class="text-[34px] font-bold text-slate-900 leading-tight">LangGraph 编排图结构 · 主图</h2>
            <p class="text-[14px] text-slate-500 mt-0.5">22 个节点（主图 13 + 子图 9）· 全图仅 1 个 LLM 节点 · 输入输出双闸门 · 3 个终止出口</p>
          </div>
        </div>
        <div class="flex gap-2.5">
          <span class="px-3 py-1.5 bg-red-50 border border-red-200 text-red-700 rounded-full text-[12px] font-medium">一票否决 = 控制流短路</span>
          <span class="px-3 py-1.5 bg-cyan-50 border border-cyan-200 text-cyan-800 rounded-full text-[12px] font-medium">风控不调大模型</span>
        </div>
      </div>

      <div class="bg-white border border-slate-200 rounded-xl shadow-sm px-3 py-2 flex-1 relative overflow-hidden">
        <div class="relative" style="width:1330px;height:452px;">

          <svg width="1330" height="452" class="absolute left-0 top-0" style="pointer-events:none;">
            <defs>
              <marker id="ah" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6 z" fill="#94A3B8"/></marker>
              <marker id="ahr" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6 z" fill="#DC2626"/></marker>
              <marker id="aha" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6 z" fill="#D97706"/></marker>
              <marker id="ahg" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6 z" fill="#059669"/></marker>
            </defs>

            <path d="M92,270 L107,270" stroke="#94A3B8" stroke-width="1.6" fill="none" marker-end="url(#ah)"/>
            <path d="M260,270 L276,270" stroke="#94A3B8" stroke-width="1.6" fill="none" marker-end="url(#ah)"/>

            <path d="M185,242 L185,36 L691,36" stroke="#DC2626" stroke-width="1.6" fill="none" stroke-dasharray="6,4" marker-end="url(#ahr)"/>
            <path d="M365,236 L365,80 L820,80 L820,62" stroke="#DC2626" stroke-width="1.6" fill="none" stroke-dasharray="6,4" marker-end="url(#ahr)"/>

            <path d="M450,270 L470,270" stroke="#94A3B8" stroke-width="1.6" fill="none"/>
            <path d="M470,120 L470,420" stroke="#94A3B8" stroke-width="1.6" fill="none"/>
            <path d="M470,120 L488,120" stroke="#94A3B8" stroke-width="1.6" fill="none" marker-end="url(#ah)"/>
            <path d="M470,180 L488,180" stroke="#94A3B8" stroke-width="1.6" fill="none" marker-end="url(#ah)"/>
            <path d="M470,240 L488,240" stroke="#94A3B8" stroke-width="1.6" fill="none" marker-end="url(#ah)"/>
            <path d="M470,300 L488,300" stroke="#94A3B8" stroke-width="1.6" fill="none" marker-end="url(#ah)"/>
            <path d="M470,360 L488,360" stroke="#94A3B8" stroke-width="1.6" fill="none" marker-end="url(#ah)"/>
            <path d="M470,420 L488,420" stroke="#94A3B8" stroke-width="1.6" fill="none" marker-end="url(#ah)"/>

            <path d="M690,120 L710,120" stroke="#94A3B8" stroke-width="1.6" fill="none"/>
            <path d="M690,180 L710,180" stroke="#94A3B8" stroke-width="1.6" fill="none"/>
            <path d="M690,240 L710,240" stroke="#94A3B8" stroke-width="1.6" fill="none"/>
            <path d="M690,300 L710,300" stroke="#94A3B8" stroke-width="1.6" fill="none"/>
            <path d="M690,360 L710,360" stroke="#94A3B8" stroke-width="1.6" fill="none"/>
            <path d="M690,420 L710,420" stroke="#94A3B8" stroke-width="1.6" fill="none"/>
            <path d="M710,120 L710,420" stroke="#94A3B8" stroke-width="1.6" fill="none"/>
            <path d="M710,270 L728,270" stroke="#94A3B8" stroke-width="1.6" fill="none" marker-end="url(#ah)"/>

            <path d="M860,270 L888,270" stroke="#94A3B8" stroke-width="1.6" fill="none" marker-end="url(#ah)"/>
            <path d="M1050,270 L1083,270" stroke="#059669" stroke-width="1.8" fill="none" marker-end="url(#ahg)"/>
            <path d="M1235,270 L1248,270" stroke="#94A3B8" stroke-width="1.6" fill="none" marker-end="url(#ah)"/>

            <path d="M970,242 L970,36 L944,36" stroke="#DC2626" stroke-width="1.6" fill="none" stroke-dasharray="6,4" marker-end="url(#ahr)"/>
            <path d="M970,298 L970,424 L1058,424" stroke="#D97706" stroke-width="1.6" fill="none" stroke-dasharray="6,4" marker-end="url(#aha)"/>

            <path d="M940,36 L953,36" stroke="#94A3B8" stroke-width="1.6" fill="none" marker-end="url(#ah)"/>
            <path d="M1260,424 L1273,424" stroke="#94A3B8" stroke-width="1.6" fill="none" marker-end="url(#ah)"/>
          </svg>

          <div class="absolute text-[12px] text-red-600 font-medium" style="left:196px;top:108px;">否决 · 短路</div>
          <div class="absolute text-[12px] text-red-600 font-medium" style="left:376px;top:142px;">否决 · 短路</div>
          <div class="absolute text-[12px] text-red-600 font-medium" style="left:982px;top:150px;">否决 · 短路</div>
          <div class="absolute text-[12px] text-amber-600 font-medium" style="left:982px;top:346px;">异常 / 超时</div>
          <div class="absolute text-[12px] text-emerald-600 font-medium" style="left:1052px;top:222px;">通过</div>
          <div class="absolute text-[12px] text-slate-400 font-medium" style="left:474px;top:292px;">按意图路由 →</div>

          <div class="absolute rounded-lg flex items-center justify-center" style="left:8px;top:246px;width:84px;height:48px;background:#1E293B;">
            <span class="text-white text-[14px] font-bold font-mono">START</span>
          </div>

          <div class="absolute rounded-lg border-2 border-orange-400 bg-orange-50 flex flex-col items-center justify-center" style="left:110px;top:242px;width:150px;height:56px;">
            <span class="text-[12px] font-mono font-bold text-orange-700">intake_guard</span>
            <span class="text-[12px] text-orange-600">输入风控闸门</span>
          </div>

          <div class="absolute rounded-lg flex flex-col items-center justify-center" style="left:280px;top:236px;width:170px;height:68px;background:#0E7490;">
            <span class="text-[15px] font-bold text-white font-mono">supervisor</span>
            <span class="text-[11px] text-cyan-100 mt-0.5">意图识别 · 唯一 LLM 节点</span>
            <span class="text-[10px] text-cyan-200 mt-0.5 px-2 py-0.5 rounded-full" style="background:rgba(255,255,255,0.18)">不做回答 · 不选工具</span>
          </div>

          <div class="absolute rounded-lg border border-slate-300 border-l-4 border-l-cyan-700 bg-white flex items-center justify-between px-3" style="left:490px;top:101px;width:200px;height:38px;">
            <span class="text-[11px] font-mono text-slate-700">subgraph_recommend</span><span class="text-[12px] text-slate-500">推荐子图</span>
          </div>
          <div class="absolute rounded-lg border border-slate-300 border-l-4 border-l-cyan-700 bg-white flex items-center justify-between px-3" style="left:490px;top:161px;width:200px;height:38px;">
            <span class="text-[11px] font-mono text-slate-700">node_free_qa</span><span class="text-[12px] text-slate-500">自由问答</span>
          </div>
          <div class="absolute rounded-lg border border-slate-300 border-l-4 border-l-cyan-700 bg-white flex items-center justify-between px-3" style="left:490px;top:221px;width:200px;height:38px;">
            <span class="text-[11px] font-mono text-slate-700">node_inventory_op</span><span class="text-[12px] text-slate-500">库存操作</span>
          </div>
          <div class="absolute rounded-lg border border-slate-300 border-l-4 border-l-cyan-700 bg-white flex items-center justify-between px-3" style="left:490px;top:281px;width:200px;height:38px;">
            <span class="text-[11px] font-mono text-slate-700">node_nutrition_query</span><span class="text-[12px] text-slate-500">营养查询</span>
          </div>
          <div class="absolute rounded-lg border border-slate-300 border-l-4 border-l-cyan-700 bg-white flex items-center justify-between px-3" style="left:490px;top:341px;width:200px;height:38px;">
            <span class="text-[11px] font-mono text-slate-700">node_cooking_help</span><span class="text-[12px] text-slate-500">烹饪求助</span>
          </div>
          <div class="absolute rounded-lg border border-slate-300 border-l-4 border-l-cyan-700 bg-white flex items-center justify-between px-3" style="left:490px;top:401px;width:200px;height:38px;">
            <span class="text-[11px] font-mono text-slate-700">node_innovation_entry</span><span class="text-[12px] text-slate-500">创新菜</span>
          </div>

          <div class="absolute rounded-lg border-2 border-indigo-300 bg-indigo-50 flex flex-col items-center justify-center" style="left:730px;top:246px;width:130px;height:48px;">
            <span class="text-[12px] font-mono font-bold text-indigo-700">compose</span>
            <span class="text-[11px] text-indigo-600">结果合成</span>
          </div>

          <div class="absolute rounded-lg border-2 border-orange-400 bg-orange-50 flex flex-col items-center justify-center" style="left:890px;top:242px;width:160px;height:56px;">
            <span class="text-[12px] font-mono font-bold text-orange-700">output_guard</span>
            <span class="text-[12px] text-orange-600">输出风控闸门</span>
          </div>

          <div class="absolute rounded-lg flex flex-col items-center justify-center" style="left:700px;top:12px;width:240px;height:48px;background:#DC2626;">
            <span class="text-[12px] font-mono font-bold text-white">emit_safety_response</span>
            <span class="text-[11px] text-red-100">安全响应 · 短路出口</span>
          </div>
          <div class="absolute rounded-full flex items-center justify-center border-2 border-slate-400 bg-white" style="left:955px;top:20px;width:62px;height:32px;">
            <span class="text-[12px] font-bold font-mono text-slate-600">END</span>
          </div>

          <div class="absolute rounded-lg border-2 border-emerald-400 bg-emerald-50 flex flex-col items-center justify-center" style="left:1085px;top:242px;width:150px;height:56px;">
            <span class="text-[12px] font-mono font-bold text-emerald-700">finalize</span>
            <span class="text-[12px] text-emerald-600">结果定稿</span>
          </div>
          <div class="absolute rounded-full flex items-center justify-center border-2 border-slate-400 bg-white" style="left:1250px;top:254px;width:66px;height:32px;">
            <span class="text-[12px] font-bold font-mono text-slate-600">END</span>
          </div>

          <div class="absolute rounded-lg border-2 border-amber-400 bg-amber-50 flex flex-col items-center justify-center" style="left:1060px;top:400px;width:200px;height:48px;">
            <span class="text-[12px] font-mono font-bold text-amber-700">safe_mode_handler</span>
            <span class="text-[11px] text-amber-600">保守模式 · 绝不直连模型</span>
          </div>
          <div class="absolute rounded-full flex items-center justify-center border-2 border-slate-400 bg-white" style="left:1275px;top:408px;width:50px;height:32px;">
            <span class="text-[11px] font-bold font-mono text-slate-600">END</span>
          </div>
        </div>
      </div>

      <div class="mt-3 grid grid-cols-3 gap-4">
        <div class="bg-white border border-slate-200 rounded-lg px-4 py-3 shadow-sm">
          <p class="text-[14px] font-bold text-slate-800 mb-1">唯一 LLM 节点的边界</p>
          <p class="text-[13px] text-slate-600 leading-relaxed">全图只有 supervisor 调用大模型，且只负责意图识别；具体走哪个分支由 <span class="font-mono text-cyan-700">INTENT_ROUTES</span> 字典决定，从结构上消除「幻觉选工具」。</p>
        </div>
        <div class="bg-white border border-slate-200 rounded-lg px-4 py-3 shadow-sm">
          <p class="text-[14px] font-bold text-slate-800 mb-1">双闸门与三级兜底</p>
          <p class="text-[13px] text-slate-600 leading-relaxed">输入侧 intake_guard 与输出侧 output_guard 都不可省；LLM 解析失败走关键词兜底分类并标记 degraded，风控异常进保守模式。</p>
        </div>
        <div class="bg-white border border-slate-200 rounded-lg px-4 py-3 shadow-sm">
          <p class="text-[14px] font-bold text-slate-800 mb-1">动态装配与可观测</p>
          <p class="text-[13px] text-slate-600 leading-relaxed">节点按 <span class="font-mono text-cyan-700">AGENT_REGISTRY</span> 注册装配，新增 Agent 不改装配逻辑；trace 记录节点、耗时、命中规则 ID 与未执行节点。</p>
        </div>
      </div>

      <div class="mt-3 flex items-center justify-between text-[13px] text-slate-400">
        <span class="font-mono tracking-wider">AI 厨娘 · 智能烹饪助手 · 项目答辩</span>
        <span class="font-mono">12 / 24</span>
      </div>
    </div>
  </div>
`);
