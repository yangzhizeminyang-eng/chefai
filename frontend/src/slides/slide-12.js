window.slideDataMap.set(12, `
  <div class="w-[1440px] h-[810px] relative overflow-hidden slide-bg">
    <div class="absolute top-0 left-0 w-full h-[8px] bg-orange-600"></div>
    <div class="w-[1350px] h-[720px] mx-auto my-[45px] relative pt-3 flex flex-col">

      <div class="flex items-center justify-between mb-3">
        <div class="flex items-center gap-4">
          <div class="w-[6px] h-10 bg-orange-600 rounded"></div>
          <div>
            <h2 class="text-[34px] font-bold text-slate-900 leading-tight">LangGraph 主图拓扑（运行期导出）</h2>
            <p class="text-[14px] text-slate-500 mt-0.5">13 个节点 · 24 条边（含 13 条条件边）· 双侧闸门 + 中枢路由 + 汇聚 + 3 个出口</p>
          </div>
        </div>
        <div class="flex gap-2">
          <span class="px-3 py-1.5 bg-slate-50 border border-slate-200 text-slate-600 rounded-full text-[12px] font-medium">实线＝普通边</span>
          <span class="px-3 py-1.5 bg-slate-50 border border-slate-200 text-slate-600 rounded-full text-[12px] font-medium">虚线＝条件边</span>
          <span class="px-3 py-1.5 bg-red-50 border border-red-200 text-red-700 rounded-full text-[12px] font-medium">红＝否决短路</span>
          <span class="px-3 py-1.5 bg-amber-50 border border-amber-200 text-amber-700 rounded-full text-[12px] font-medium">琥珀＝保守模式</span>
        </div>
      </div>

      <div class="bg-white border border-slate-200 rounded-xl shadow-sm px-3 py-2 flex-1 relative overflow-hidden">
        <div class="relative" style="width:1330px;height:452px;">

          <svg width="1330" height="452" class="absolute left-0 top-0" style="pointer-events:none;">
            <defs>
              <marker id="m-s" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6 z" fill="#64748B"/></marker>
              <marker id="m-c" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6 z" fill="#94A3B8"/></marker>
              <marker id="m-r" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6 z" fill="#DC2626"/></marker>
              <marker id="m-a" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6 z" fill="#D97706"/></marker>
              <marker id="m-g" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6 z" fill="#059669"/></marker>
            </defs>

            <path d="M84,250 L98,250" stroke="#64748B" stroke-width="1.6" fill="none" marker-end="url(#m-s)"/>
            <path d="M252,250 L268,250" stroke="#94A3B8" stroke-width="1.6" fill="none" stroke-dasharray="6,4" marker-end="url(#m-c)"/>

            <path d="M185,222 L185,18 L698,18" stroke="#DC2626" stroke-width="1.6" fill="none" stroke-dasharray="6,4" marker-end="url(#m-r)"/>
            <path d="M185,278 L185,440 L1028,440 L1028,396 L1058,396" stroke="#D97706" stroke-width="1.6" fill="none" stroke-dasharray="6,4" marker-end="url(#m-a)"/>

            <path d="M442,250 L460,250" stroke="#94A3B8" stroke-width="1.6" fill="none"/>
            <path d="M460,70 L460,360" stroke="#94A3B8" stroke-width="1.6" fill="none"/>
            <path d="M460,70 L478,70" stroke="#94A3B8" stroke-width="1.6" fill="none" stroke-dasharray="6,4" marker-end="url(#m-c)"/>
            <path d="M460,128 L478,128" stroke="#94A3B8" stroke-width="1.6" fill="none" stroke-dasharray="6,4" marker-end="url(#m-c)"/>
            <path d="M460,186 L478,186" stroke="#94A3B8" stroke-width="1.6" fill="none" stroke-dasharray="6,4" marker-end="url(#m-c)"/>
            <path d="M460,244 L478,244" stroke="#94A3B8" stroke-width="1.6" fill="none" stroke-dasharray="6,4" marker-end="url(#m-c)"/>
            <path d="M460,302 L478,302" stroke="#94A3B8" stroke-width="1.6" fill="none" stroke-dasharray="6,4" marker-end="url(#m-c)"/>
            <path d="M460,360 L478,360" stroke="#94A3B8" stroke-width="1.6" fill="none" stroke-dasharray="6,4" marker-end="url(#m-c)"/>

            <path d="M365,216 L365,42 L698,42" stroke="#DC2626" stroke-width="1.6" fill="none" stroke-dasharray="6,4" marker-end="url(#m-r)"/>

            <path d="M688,70 L708,70" stroke="#64748B" stroke-width="1.6" fill="none"/>
            <path d="M688,128 L708,128" stroke="#64748B" stroke-width="1.6" fill="none"/>
            <path d="M688,186 L708,186" stroke="#64748B" stroke-width="1.6" fill="none"/>
            <path d="M688,244 L708,244" stroke="#64748B" stroke-width="1.6" fill="none"/>
            <path d="M688,302 L708,302" stroke="#64748B" stroke-width="1.6" fill="none"/>
            <path d="M688,360 L708,360" stroke="#64748B" stroke-width="1.6" fill="none"/>
            <path d="M708,70 L708,360" stroke="#64748B" stroke-width="1.6" fill="none"/>
            <path d="M708,250 L724,250" stroke="#64748B" stroke-width="1.6" fill="none" marker-end="url(#m-s)"/>

            <path d="M856,250 L884,250" stroke="#64748B" stroke-width="1.6" fill="none" marker-end="url(#m-s)"/>
            <path d="M1046,250 L1078,250" stroke="#059669" stroke-width="1.8" fill="none" stroke-dasharray="6,4" marker-end="url(#m-g)"/>

            <path d="M966,222 L966,64 L820,64 L820,56" stroke="#DC2626" stroke-width="1.6" fill="none" stroke-dasharray="6,4" marker-end="url(#m-r)"/>
            <path d="M966,278 L966,384 L1058,384" stroke="#D97706" stroke-width="1.6" fill="none" stroke-dasharray="6,4" marker-end="url(#m-a)"/>

            <path d="M1232,250 L1254,250" stroke="#64748B" stroke-width="1.6" fill="none" marker-end="url(#m-s)"/>
            <path d="M940,30 L956,30" stroke="#64748B" stroke-width="1.6" fill="none" marker-end="url(#m-s)"/>
            <path d="M1260,396 L1274,396" stroke="#64748B" stroke-width="1.6" fill="none" marker-end="url(#m-s)"/>
          </svg>

          <div class="absolute text-[12px] text-red-600 font-medium" style="left:188px;top:96px;">hit（含伪科学澄清）</div>
          <div class="absolute text-[12px] text-amber-600 font-medium" style="left:188px;top:340px;">status=UNKNOWN</div>
          <div class="absolute text-[12px] text-slate-500 font-medium" style="left:262px;top:226px;">pass</div>
          <div class="absolute text-[12px] text-red-600 font-medium" style="left:372px;top:22px;">intent=__veto__（双保险）</div>
          <div class="absolute text-[12px] text-slate-400" style="left:462px;top:372px;">← 按 INTENT_ROUTES 字典路由（7 条条件边）</div>
          <div class="absolute text-[12px] text-red-600 font-medium" style="left:866px;top:68px;">hit &amp; block</div>
          <div class="absolute text-[12px] text-emerald-600 font-medium" style="left:1048px;top:228px;">pass</div>
          <div class="absolute text-[12px] text-amber-600 font-medium" style="left:972px;top:328px;">status=UNKNOWN</div>

          <div class="absolute rounded-lg flex items-center justify-center" style="left:6px;top:226px;width:78px;height:48px;background:#1E293B;">
            <span class="text-white text-[11px] font-bold font-mono">__start__</span>
          </div>

          <div class="absolute rounded-lg border-2 border-orange-400 bg-orange-50 flex flex-col items-center justify-center" style="left:100px;top:222px;width:152px;height:56px;">
            <span class="text-[12px] font-mono font-bold text-orange-700">intake_guard</span>
            <span class="text-[11px] text-orange-600">入口闸门 · rule · 500ms</span>
          </div>

          <div class="absolute rounded-lg flex flex-col items-center justify-center" style="left:270px;top:216px;width:172px;height:68px;background:#0E7490;">
            <span class="text-[15px] font-bold text-white font-mono">supervisor</span>
            <span class="text-[11px] text-cyan-100 mt-0.5">意图识别 · llm · 3000ms</span>
            <span class="text-[10px] text-cyan-200 mt-0.5 px-2 py-0.5 rounded-full" style="background:rgba(255,255,255,0.18)">只输出意图标签 · 不选工具</span>
          </div>

          <div class="absolute rounded-lg border border-slate-300 border-l-4 border-l-cyan-700 bg-white flex flex-col items-center justify-center" style="left:480px;top:51px;width:208px;height:38px;">
            <span class="text-[10.5px] font-mono text-slate-700 leading-none mb-1">subgraph_recommend</span><span class="text-[10px] text-slate-500 leading-none">推荐子图 · subgraph · 5000ms</span>
          </div>
          <div class="absolute rounded-lg border border-slate-300 border-l-4 border-l-sky-600 bg-white flex flex-col items-center justify-center" style="left:480px;top:109px;width:208px;height:38px;">
            <span class="text-[10.5px] font-mono text-slate-700 leading-none mb-1">node_free_qa</span><span class="text-[10px] text-slate-500 leading-none">受限问答 · llm · 5000ms</span>
          </div>
          <div class="absolute rounded-lg border border-slate-300 border-l-4 border-l-slate-500 bg-white flex flex-col items-center justify-center" style="left:480px;top:167px;width:208px;height:38px;">
            <span class="text-[10.5px] font-mono text-slate-700 leading-none mb-1">node_inventory_op</span><span class="text-[10px] text-slate-500 leading-none">库存操作 · rule · 1000ms</span>
          </div>
          <div class="absolute rounded-lg border border-slate-300 border-l-4 border-l-slate-500 bg-white flex flex-col items-center justify-center" style="left:480px;top:225px;width:208px;height:38px;">
            <span class="text-[10.5px] font-mono text-slate-700 leading-none mb-1">node_nutrition_query</span><span class="text-[10px] text-slate-500 leading-none">营养查询 · rule · 1000ms</span>
          </div>
          <div class="absolute rounded-lg border border-slate-300 border-l-4 border-l-slate-500 bg-white flex flex-col items-center justify-center" style="left:480px;top:283px;width:208px;height:38px;">
            <span class="text-[10.5px] font-mono text-slate-700 leading-none mb-1">node_cooking_help</span><span class="text-[10px] text-slate-500 leading-none">烹饪求助 · rule · 1000ms</span>
          </div>
          <div class="absolute rounded-lg border border-slate-300 border-l-4 border-l-cyan-700 bg-white flex flex-col items-center justify-center" style="left:480px;top:341px;width:208px;height:38px;">
            <span class="text-[10.5px] font-mono text-slate-700 leading-none mb-1">node_innovation_entry</span><span class="text-[10px] text-slate-500 leading-none">创新入口 · subgraph · 8000ms</span>
          </div>

          <div class="absolute rounded-lg border-2 border-indigo-300 bg-indigo-50 flex flex-col items-center justify-center" style="left:726px;top:226px;width:130px;height:48px;">
            <span class="text-[12px] font-mono font-bold text-indigo-700">compose</span>
            <span class="text-[10px] text-indigo-600">汇总组装 · 1000ms</span>
          </div>

          <div class="absolute rounded-lg border-2 border-orange-400 bg-orange-50 flex flex-col items-center justify-center" style="left:886px;top:222px;width:160px;height:56px;">
            <span class="text-[12px] font-mono font-bold text-orange-700">output_guard</span>
            <span class="text-[11px] text-orange-600">出口闸门 · rule · 500ms</span>
          </div>

          <div class="absolute rounded-lg flex flex-col items-center justify-center" style="left:700px;top:6px;width:240px;height:48px;background:#DC2626;">
            <span class="text-[12px] font-mono font-bold text-white">emit_safety_response</span>
            <span class="text-[10px] text-red-100">一票否决 / 澄清出口 · 仅 6 个安全字段</span>
          </div>
          <div class="absolute rounded-full flex items-center justify-center border-2 border-slate-400 bg-white" style="left:958px;top:14px;width:62px;height:32px;">
            <span class="text-[11px] font-bold font-mono text-slate-600">__end__</span>
          </div>

          <div class="absolute rounded-lg border-2 border-emerald-400 bg-emerald-50 flex flex-col items-center justify-center" style="left:1080px;top:222px;width:152px;height:56px;">
            <span class="text-[12px] font-mono font-bold text-emerald-700">finalize</span>
            <span class="text-[10px] text-emerald-600">trace 落库 + 终响应</span>
          </div>
          <div class="absolute rounded-full flex items-center justify-center border-2 border-slate-400 bg-white" style="left:1256px;top:234px;width:66px;height:32px;">
            <span class="text-[11px] font-bold font-mono text-slate-600">__end__</span>
          </div>

          <div class="absolute rounded-lg border-2 border-amber-400 bg-amber-50 flex flex-col items-center justify-center" style="left:1060px;top:372px;width:200px;height:48px;">
            <span class="text-[12px] font-mono font-bold text-amber-700">safe_mode_handler</span>
            <span class="text-[10px] text-amber-600">保守模式出口 · TXT-G06 固定话术</span>
          </div>
          <div class="absolute rounded-full flex items-center justify-center border-2 border-slate-400 bg-white" style="left:1276px;top:380px;width:50px;height:32px;">
            <span class="text-[10px] font-bold font-mono text-slate-600">__end__</span>
          </div>
        </div>
      </div>

      <div class="mt-3 grid grid-cols-5 gap-2.5">
        <div class="bg-white border border-slate-200 border-t-2 border-t-orange-500 rounded-lg px-3 py-2 shadow-sm">
          <p class="text-[12px] font-bold text-slate-800 mb-0.5">END 入边仅 3 条</p>
          <p class="text-[11px] text-slate-500 leading-snug">全部来自三个出口，无绕过闸门直达 END 的路径</p>
        </div>
        <div class="bg-white border border-slate-200 border-t-2 border-t-orange-500 rounded-lg px-3 py-2 shadow-sm">
          <p class="text-[12px] font-bold text-slate-800 mb-0.5">闸门与 END 无直连</p>
          <p class="text-[11px] text-slate-500 leading-snug">intake_guard 与 END 无直边，否决必经短路出口</p>
        </div>
        <div class="bg-white border border-slate-200 border-t-2 border-t-orange-500 rounded-lg px-3 py-2 shadow-sm">
          <p class="text-[12px] font-bold text-slate-800 mb-0.5">条件边白名单闭合</p>
          <p class="text-[11px] text-slate-500 leading-snug">13 条条件边均显式声明目标白名单，越界编译期报错</p>
        </div>
        <div class="bg-white border border-slate-200 border-t-2 border-t-orange-500 rounded-lg px-3 py-2 shadow-sm">
          <p class="text-[12px] font-bold text-slate-800 mb-0.5">全节点可达无死点</p>
          <p class="text-[11px] text-slate-500 leading-snug">13 个节点从 START 全部可达，无出度为 0 的死节点</p>
        </div>
        <div class="bg-white border border-slate-200 border-t-2 border-t-orange-500 rounded-lg px-3 py-2 shadow-sm">
          <p class="text-[12px] font-bold text-slate-800 mb-0.5">出口闸门不可绕过</p>
          <p class="text-[11px] text-slate-500 leading-snug">output_guard 位于 compose 之后、三出口之前</p>
        </div>
      </div>

      <div class="mt-2.5 flex items-center justify-between text-[12px] text-slate-400">
        <span class="font-mono tracking-wider">AI 厨娘 · 智能烹饪助手 · 项目答辩</span>
        <span class="font-mono">12 / 25</span>
      </div>
    </div>
  </div>
`);
