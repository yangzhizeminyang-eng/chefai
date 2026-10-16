window.slideDataMap.set(17, `
  <div class="w-[1440px] h-[810px] relative overflow-hidden slide-bg">
    <div class="absolute top-0 left-0 w-full h-[8px] bg-cyan-700"></div>
    <div class="w-[1350px] h-[720px] mx-auto my-[45px] relative pt-4 flex flex-col">

      <div class="flex items-center gap-4 mb-5">
        <div class="w-[6px] h-[42px] bg-cyan-700 rounded"></div>
        <div>
          <h2 class="text-[36px] font-bold text-slate-900 leading-tight">精彩代码① 三路召回与布尔硬过滤</h2>
          <p class="text-[15px] text-slate-500 mt-1">过敏原硬过滤为什么必须是布尔运算，而不是「降权」—— 一段代码讲清设计取舍</p>
        </div>
      </div>

      <div class="flex gap-5 flex-1">
        <div class="w-[63%] bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden flex flex-col">
          <div class="bg-slate-50 border-b border-slate-200 px-5 py-2.5 flex items-center justify-between">
            <div class="flex items-center gap-2.5">
              <span class="w-2.5 h-2.5 rounded-full bg-rose-400"></span>
              <span class="w-2.5 h-2.5 rounded-full bg-amber-400"></span>
              <span class="w-2.5 h-2.5 rounded-full bg-emerald-400"></span>
              <span class="text-[13px] font-mono text-slate-600 ml-2">backend/app/graph/subgraphs/recommend.py</span>
            </div>
            <span class="text-[12px] font-mono text-slate-400">Python 3.11 ｜ 推荐子图</span>
          </div>

          <div class="p-4 font-mono text-[13px] leading-[1.8] text-slate-700 flex-1">
            <div class="flex">
              <div class="text-slate-300 pr-4 select-none text-right">
                <div>1</div><div>2</div><div>3</div><div>4</div><div>5</div><div>6</div><div>7</div><div>8</div><div>9</div><div>10</div><div>11</div>
              </div>
              <div class="flex-1">
                <div><span class="text-slate-400"># 1) 三路混合召回：覆盖率恒生效，文本需带 query，向量需 query_text 非空</span></div>
                <div><span class="text-sky-800">candidates</span> <span class="text-slate-500">=</span> <span class="text-indigo-700">coverage_recall</span><span class="text-slate-600">(ctx)</span> <span class="text-rose-600">|</span> <span class="text-indigo-700">text_recall</span><span class="text-slate-600">(ctx)</span></div>
                <div><span class="text-rose-600">if</span> <span class="text-sky-800">use_vector</span> <span class="text-rose-600">and</span> <span class="text-sky-800">query_text</span><span class="text-slate-600">:</span></div>
                <div>&nbsp;&nbsp;&nbsp;&nbsp;<span class="text-sky-800">candidates</span> <span class="text-rose-600">|=</span> <span class="text-indigo-700">vector_recall</span><span class="text-slate-600">(query_text, top_k=</span><span class="text-amber-700">20</span><span class="text-slate-600">)</span></div>
                <div>&nbsp;</div>
                <div><span class="text-slate-400"># 2) 四维布尔硬过滤：过敏原落到 SQL 布尔运算，绝不降权</span></div>
                <div><span class="text-sky-800">rows</span> <span class="text-slate-500">=</span> <span class="text-sky-800">session</span><span class="text-slate-600">.</span><span class="text-indigo-700">execute</span><span class="text-slate-600">(</span></div>
                <div>&nbsp;&nbsp;&nbsp;&nbsp;<span class="text-emerald-700">"WHERE NOT (allergen_codes &amp;&amp; %s::text[]) AND difficulty &lt;= %s"</span><span class="text-slate-600">,</span></div>
                <div>&nbsp;&nbsp;&nbsp;&nbsp;<span class="text-slate-600">(</span><span class="text-sky-800">user_allergens</span><span class="text-slate-600">,</span> <span class="text-sky-800">skill_level</span><span class="text-slate-600">))</span></div>
                <div>&nbsp;</div>
                <div><span class="text-slate-400"># 3) 排序输入只能来自 hard_filter 输出集 —— 结构上杜绝「打分后放回」</span></div>
              </div>
            </div>
          </div>

          <div class="bg-slate-50 border-t border-slate-200 px-5 py-2.5 flex items-center justify-between text-[12px] font-mono">
            <span class="text-rose-600">● 过敏原：布尔硬过滤，不降权</span>
            <span class="text-slate-500">dislike：降权 −0.5</span>
            <span class="text-emerald-600">✓ 12 条安全红线全绿</span>
          </div>
        </div>

        <div class="w-[37%] flex flex-col gap-4">
          <div class="bg-white border border-slate-200 border-l-4 border-l-rose-500 rounded-xl p-5 shadow-sm">
            <h3 class="text-[17px] font-bold text-slate-800 mb-2">为什么过敏原不能用「降权」</h3>
            <p class="text-[13px] text-slate-600 leading-relaxed">
              降权只是把分数调低，菜谱仍在候选集里 —— 一旦候选不足、或权重被远程调低，含过敏原的菜谱就可能重新浮上来。
              硬过滤则在数据层面直接剔除，<span class="font-semibold text-rose-600">不存在「浮上来」的路径</span>。
            </p>
          </div>

          <div class="bg-white border border-slate-200 border-l-4 border-l-cyan-700 rounded-xl p-5 shadow-sm">
            <h3 class="text-[17px] font-bold text-slate-800 mb-2">权重可远程热调</h3>
            <p class="text-[13px] text-slate-600 leading-relaxed">
              排序权重存放在远程配置中，运营侧可在不重新发版的前提下调整因子配比；但<span class="font-semibold">无论如何调整，都改不动过滤节点的布尔条件</span> —— 可调的是排序，不是安全。
            </p>
          </div>

          <div class="bg-white border border-slate-200 border-l-4 border-l-amber-500 rounded-xl p-5 shadow-sm flex-1">
            <h3 class="text-[17px] font-bold text-slate-800 mb-2">被过滤的菜谱可以「翻案」</h3>
            <p class="text-[13px] text-slate-600 leading-relaxed mb-2">
              过滤时逐项记录 <span class="font-mono text-[12px]">filtered_by</span> 计数，前端提供「显示被我过滤掉的菜」开关，用户可查看每道菜被过滤的具体原因。
            </p>
            <p class="text-[13px] text-slate-600 leading-relaxed">
              这个设计的价值在于：如果档案填错导致误过滤，用户能看见原因并及时修正，而不是面对一个「怎么推荐这么少」的黑盒。
            </p>
          </div>

          <div class="flex gap-2 flex-wrap">
            <span class="px-3.5 py-1.5 bg-cyan-50 border border-cyan-200 text-cyan-800 rounded-full text-[12px] font-mono">Python 3.11</span>
            <span class="px-3.5 py-1.5 bg-sky-50 border border-sky-200 text-sky-800 rounded-full text-[12px] font-mono">PostgreSQL 16</span>
            <span class="px-3.5 py-1.5 bg-indigo-50 border border-indigo-200 text-indigo-800 rounded-full text-[12px] font-mono">pgvector</span>
            <span class="px-3.5 py-1.5 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-full text-[12px] font-mono">SQL 布尔过滤</span>
          </div>
        </div>
      </div>

      <div class="mt-4 flex items-center justify-between text-[13px] text-slate-400">
        <span class="font-mono tracking-wider">AI 厨娘 · 智能烹饪助手 · 项目答辩</span>
        <span class="font-mono">17 / 25</span>
      </div>
    </div>
  </div>
`);
