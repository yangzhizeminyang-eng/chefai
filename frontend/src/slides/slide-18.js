window.slideDataMap.set(18, `
  <div class="w-[1440px] h-[810px] relative overflow-hidden slide-bg">
    <div class="absolute top-0 left-0 w-full h-[8px] bg-cyan-700"></div>
    <div class="w-[1350px] h-[720px] mx-auto my-[45px] relative pt-1 flex flex-col">

      <div class="flex items-center gap-4 mb-5">
        <div class="w-[6px] h-[42px] bg-cyan-700 rounded"></div>
        <div>
          <h2 class="text-[36px] font-bold text-slate-900 leading-tight">精彩代码② 风控短路与节点动态装配</h2>
          <p class="text-[15px] text-slate-500 mt-1">一票否决 = 控制流短路，不是「标记后丢弃」—— 三行代码守住整条安全底线</p>
        </div>
      </div>

      <div class="flex gap-5 flex-1">
        <div class="w-[37%] flex flex-col gap-4">
          <div class="bg-white border border-slate-200 border-l-4 border-l-rose-500 rounded-xl p-5 shadow-sm">
            <h3 class="text-[17px] font-bold text-slate-800 mb-2">「短路」和「丢弃」的区别</h3>
            <p class="text-[13px] text-slate-600 leading-relaxed">
              标记后丢弃意味着业务节点仍然执行了一遍，只是最后不返回结果 —— 中间可能已经调用了模型、写入了数据。
              短路则是条件边直接越过全部业务节点，<span class="font-semibold text-rose-600">连执行机会都不给</span>。
            </p>
          </div>

          <div class="bg-white border border-slate-200 border-l-4 border-l-cyan-700 rounded-xl p-5 shadow-sm">
            <h3 class="text-[17px] font-bold text-slate-800 mb-2">为什么风控不交给大模型</h3>
            <p class="text-[13px] text-slate-600 leading-relaxed">
              安全判定需要的是<span class="font-semibold">确定性</span>：同一句话今天判拦截、明天也必须拦截。
              规则引擎毫秒级返回、零 token 成本、可逐条审计，而且用户输入无法通过提示词绕过它 —— 因为它根本不读提示词。
            </p>
          </div>

          <div class="bg-white border border-slate-200 border-l-4 border-l-indigo-600 rounded-xl p-5 shadow-sm">
            <h3 class="text-[17px] font-bold text-slate-800 mb-2">动态装配带来的扩展性</h3>
            <p class="text-[13px] text-slate-600 leading-relaxed">
              节点按注册表装配，新增一个 Agent 只需注册一项，不需要改动图的构建逻辑。
              这让「22 个节点」不是一次性写死的结构，而是可持续生长的骨架。
            </p>
          </div>

          <div class="bg-slate-50 border border-slate-200 rounded-xl p-5 flex-1">
            <h3 class="text-[17px] font-bold text-slate-800 mb-2">双保险：两层拦截</h3>
            <p class="text-[13px] text-slate-600 leading-relaxed mb-2">
              第一层在图入口拦截用户输入；第二层在处理完成后拦截输出。
              即便某个节点被绕过，各节点入口还会再次检查否决标记，命中即以 <span class="font-mono text-[12px]">skipped_by_veto</span> 返回。
            </p>
            <p class="text-[13px] text-slate-600 leading-relaxed">
              规则、节点、出口三层防护叠加，才让「12 条安全红线全绿」这个结论站得住。
            </p>
          </div>
        </div>

        <div class="w-[63%] bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden flex flex-col">
          <div class="bg-slate-50 border-b border-slate-200 px-5 py-2.5 flex items-center justify-between">
            <div class="flex items-center gap-2.5">
              <span class="w-2.5 h-2.5 rounded-full bg-rose-400"></span>
              <span class="w-2.5 h-2.5 rounded-full bg-amber-400"></span>
              <span class="w-2.5 h-2.5 rounded-full bg-emerald-400"></span>
              <span class="text-[13px] font-mono text-slate-600 ml-2">backend/app/graph/nodes/guards.py ｜ main_graph.py</span>
            </div>
            <span class="text-[12px] font-mono text-slate-400">纯规则 · 零 LLM</span>
          </div>

          <div class="p-4 font-mono text-[13px] leading-[1.6] text-slate-700 flex-1">
            <div class="flex">
              <div class="text-slate-300 pr-4 select-none text-right">
                <div>1</div><div>2</div><div>3</div><div>4</div><div>5</div><div>6</div><div>7</div><div>8</div><div>9</div><div>10</div><div>11</div><div>12</div>
              </div>
              <div class="flex-1">
                <div><span class="text-slate-400"># ① 风控节点：纯规则引擎，不调用大模型</span></div>
                <div><span class="text-sky-800">verdict</span> <span class="text-slate-500">=</span> <span class="text-sky-800">safety_engine</span><span class="text-slate-600">.</span><span class="text-indigo-700">check</span><span class="text-slate-600">(text, stage=</span><span class="text-emerald-700">"intake"</span><span class="text-slate-600">)</span></div>
                <div><span class="text-rose-600">if</span> <span class="text-sky-800">verdict</span><span class="text-slate-600">.overrides_all:</span> <span class="text-slate-400"># 一票否决</span></div>
                <div>&nbsp;&nbsp;&nbsp;&nbsp;<span class="text-rose-600">return</span> <span class="text-slate-600">{</span><span class="text-emerald-700">"route"</span><span class="text-slate-600">:</span> <span class="text-emerald-700">"emit_safety_response"</span><span class="text-slate-600">}</span> <span class="text-slate-400"># 条件边 → 短路</span></div>
                <div>&nbsp;</div>
                <div><span class="text-slate-400"># ② 图装配：节点按注册表动态加入，新增 Agent 不必改装配逻辑</span></div>
                <div><span class="text-rose-600">for</span> <span class="text-sky-800">name</span><span class="text-slate-600">,</span> <span class="text-sky-800">builder</span> <span class="text-rose-600">in</span> <span class="text-sky-800">AGENT_REGISTRY</span><span class="text-slate-600">.</span><span class="text-indigo-700">items</span><span class="text-slate-600">():</span></div>
                <div>&nbsp;&nbsp;&nbsp;&nbsp;<span class="text-sky-800">graph</span><span class="text-slate-600">.</span><span class="text-indigo-700">add_node</span><span class="text-slate-600">(name,</span> <span class="text-indigo-700">builder</span><span class="text-slate-600">())</span></div>
                <div>&nbsp;</div>
                <div><span class="text-slate-400"># ③ 各节点入口统一检查否决标记，命中即跳过业务逻辑</span></div>
                <div><span class="text-rose-600">if</span> <span class="text-sky-800">state</span><span class="text-slate-600">[</span><span class="text-emerald-700">"input_verdict"</span><span class="text-slate-600">].overrides_all:</span></div>
                <div>&nbsp;&nbsp;&nbsp;&nbsp;<span class="text-rose-600">return</span> <span class="text-slate-600">{</span><span class="text-emerald-700">"skipped_by_veto"</span><span class="text-slate-600">:</span> <span class="text-amber-700">True</span><span class="text-slate-600">}</span> <span class="text-slate-400"># 不执行任何业务逻辑</span></div>
              </div>
            </div>
          </div>

          <div class="bg-slate-50 border-t border-slate-200 px-5 py-2.5 flex items-center justify-between text-[12px] font-mono">
            <span class="text-rose-600">● 一票否决：控制流短路</span>
            <span class="text-indigo-600">AGENT_REGISTRY：动态装配</span>
            <span class="text-slate-500">trace：FS-003@rules-v1.0 可回放</span>
          </div>
        </div>
      </div>

      <div class="mt-4 flex items-center justify-between text-[13px] text-slate-400">
        <span class="font-mono tracking-wider">AI 厨娘 · 智能烹饪助手 · 项目答辩</span>
        <span class="font-mono">18 / 25</span>
      </div>
    </div>
  </div>
`);
