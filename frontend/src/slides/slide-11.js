window.slideDataMap.set(11, `
  <div class="w-[1440px] h-[810px] relative overflow-hidden slide-bg">
    <div class="absolute top-0 left-0 w-full h-[8px] bg-cyan-700"></div>
    <div class="w-[1350px] h-[720px] mx-auto my-[45px] relative pt-4 flex flex-col">

      <div class="flex items-center justify-between mb-4">
        <div class="flex items-center gap-4">
          <div class="w-[6px] h-[42px] bg-cyan-700 rounded"></div>
          <div>
            <h2 class="text-[36px] font-bold text-slate-900 leading-tight">重点模块① 智能菜谱推荐</h2>
            <p class="text-[15px] text-slate-500 mt-1">第一主路径 · 推荐子图 5 节点 · <span class="text-cyan-700 font-semibold">全程不调用大模型</span>，确定性、可解释、可审计</p>
          </div>
        </div>
        <div class="flex gap-3">
          <span class="px-4 py-2 bg-cyan-50 border border-cyan-200 text-cyan-800 rounded-full text-[13px] font-medium">模块完成度 98%</span>
          <span class="px-4 py-2 bg-slate-50 border border-slate-200 text-slate-600 rounded-full text-[13px] font-medium">0 次 LLM 调用</span>
        </div>
      </div>

      <div class="bg-white border border-slate-200 rounded-xl px-5 py-4 shadow-sm mb-4">
        <div class="flex items-center gap-2.5">
          <div class="flex-1 bg-cyan-50 border-2 border-cyan-200 rounded-lg px-3 py-2.5 text-center">
            <p class="text-[11px] font-mono text-cyan-700 mb-0.5">assemble_context</p>
            <p class="text-[14px] font-bold text-slate-800 mb-0.5">① 上下文归一</p>
            <p class="text-[11px] text-slate-500">食材名 / 别名 → ingredient_id</p>
          </div>
          <span class="text-slate-300 text-[18px] flex-shrink-0">➜</span>
          <div class="flex-1 bg-sky-50 border-2 border-sky-200 rounded-lg px-3 py-2.5 text-center">
            <p class="text-[11px] font-mono text-sky-700 mb-0.5">recipe_retrieve</p>
            <p class="text-[14px] font-bold text-slate-800 mb-0.5">② 三路混合召回</p>
            <p class="text-[11px] text-slate-500">覆盖率 / 文本 / 向量 · ≤200</p>
          </div>
          <span class="text-slate-300 text-[18px] flex-shrink-0">➜</span>
          <div class="flex-1 bg-orange-50 border-2 border-orange-200 rounded-lg px-3 py-2.5 text-center">
            <p class="text-[11px] font-mono text-orange-700 mb-0.5">hard_filter</p>
            <p class="text-[14px] font-bold text-slate-800 mb-0.5">③ 布尔硬过滤</p>
            <p class="text-[11px] text-slate-500">SQL WHERE 四维布尔运算</p>
          </div>
          <span class="text-slate-300 text-[18px] flex-shrink-0">➜</span>
          <div class="flex-1 bg-indigo-50 border-2 border-indigo-200 rounded-lg px-3 py-2.5 text-center relative">
            <span class="absolute -top-2.5 right-2 text-[10px] px-2 py-0.5 bg-indigo-600 text-white rounded-full">与⑤并行</span>
            <p class="text-[11px] font-mono text-indigo-700 mb-0.5">recipe_rank</p>
            <p class="text-[14px] font-bold text-slate-800 mb-0.5">④ 7 因子加权</p>
            <p class="text-[11px] text-slate-500">输出 rank_reasons → Top 8</p>
          </div>
          <span class="text-slate-300 text-[18px] flex-shrink-0">⇉</span>
          <div class="flex-1 bg-emerald-50 border-2 border-emerald-200 rounded-lg px-3 py-2.5 text-center">
            <p class="text-[11px] font-mono text-emerald-700 mb-0.5">node_nutrition</p>
            <p class="text-[14px] font-bold text-slate-800 mb-0.5">⑤ 营养估算</p>
            <p class="text-[11px] text-slate-500">按过滤输出序取前 3 道</p>
          </div>
        </div>
        <p class="text-[11.5px] text-slate-500 leading-snug mt-3 pt-2.5 border-t border-slate-100">
          <span class="font-semibold text-slate-700">并行语义：</span>④ 与 ⑤ 由 <span class="font-mono text-[11px] text-orange-600">hard_filter</span> 同时 fan-out，在<b>同一 superstep</b> 内并行执行，两条分支都连 END，<b>全部结束后</b>才返回主图进入 compose —— 因此 ⑤ 无法依赖 ④ 的输出，取的是过滤后的前 3 道。
        </p>
      </div>

      <div class="grid grid-cols-3 gap-4 flex-1">
        <div class="bg-white border border-slate-200 rounded-xl p-5 shadow-sm flex flex-col">
          <h3 class="text-[18px] font-bold text-slate-800 mb-3">召回：三路混合与生效条件</h3>
          <div class="space-y-2.5 flex-1">
            <div class="bg-slate-50 rounded-lg px-3.5 py-2.5">
              <div class="flex items-center justify-between mb-1">
                <span class="text-[14px] font-semibold text-slate-800">① 覆盖率召回</span>
                <span class="text-[11px] text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-full px-2.5 py-0.5">恒生效</span>
              </div>
              <p class="text-[12px] text-slate-500 leading-relaxed">按命中食材数量降序排列，是「有什么做什么」这一主场景的基线能力。</p>
            </div>
            <div class="bg-slate-50 rounded-lg px-3.5 py-2.5">
              <div class="flex items-center justify-between mb-1">
                <span class="text-[14px] font-semibold text-slate-800">② 文本召回</span>
                <span class="text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded-full px-2.5 py-0.5">需携带文本</span>
              </div>
              <p class="text-[12px] text-slate-500 leading-relaxed">菜名模糊匹配，并从菜谱正文中解析食材提及，补足「按名字找菜」的场景。</p>
            </div>
            <div class="bg-slate-50 rounded-lg px-3.5 py-2.5">
              <div class="flex items-center justify-between mb-1">
                <span class="text-[14px] font-semibold text-slate-800">③ 向量召回</span>
                <span class="text-[11px] text-rose-700 bg-rose-50 border border-rose-200 rounded-full px-2.5 py-0.5">需 query_text</span>
              </div>
              <p class="text-[12px] text-slate-500 leading-relaxed">用 pgvector 计算相似度取 Top-20，捕捉字面不同但语义相近的菜谱。</p>
            </div>
          </div>
          <p class="text-[12px] text-slate-500 leading-relaxed mt-3 pt-3 border-t border-slate-100">
            三路结果取并集去重，再按固定优先级融合。<span class="font-semibold text-slate-700">诚实说明：</span>纯手选路径不携带文本，因此不触发向量召回，阶段一实际只用到两路。
          </p>
        </div>

        <div class="bg-white border border-slate-200 rounded-xl p-5 shadow-sm flex flex-col">
          <h3 class="text-[18px] font-bold text-slate-800 mb-3">过滤：四个维度命中即剔除</h3>
          <div class="grid grid-cols-2 gap-2.5">
            <div class="bg-red-50 border border-red-200 rounded-lg px-3.5 py-3">
              <p class="text-[14px] font-semibold text-red-700 mb-1">过敏原</p>
              <p class="text-[12px] text-red-600 leading-relaxed">落到数据库布尔运算，绝不降权</p>
            </div>
            <div class="bg-orange-50 border border-orange-200 rounded-lg px-3.5 py-3">
              <p class="text-[14px] font-semibold text-orange-700 mb-1">忌口</p>
              <p class="text-[12px] text-orange-600 leading-relaxed">素食、清真、不吃辣等直接排除</p>
            </div>
            <div class="bg-sky-50 border border-sky-200 rounded-lg px-3.5 py-3">
              <p class="text-[14px] font-semibold text-sky-700 mb-1">难度</p>
              <p class="text-[12px] text-sky-600 leading-relaxed">不高于用户自评的厨艺能力上限</p>
            </div>
            <div class="bg-teal-50 border border-teal-200 rounded-lg px-3.5 py-3">
              <p class="text-[14px] font-semibold text-teal-700 mb-1">设备</p>
              <p class="text-[12px] text-teal-600 leading-relaxed">按家庭厨具做差集，基础工具豁免</p>
            </div>
          </div>
          <div class="space-y-2 mt-3 flex-1">
            <p class="text-[12px] text-slate-500 leading-relaxed">四个维度各自记录 <span class="font-mono text-[11px]">filtered_by</span> 命中计数，前端可逐条重放「这道菜为什么被过滤」。</p>
            <p class="text-[12px] text-slate-500 leading-relaxed">口味上的「不喜欢」走的是降权（−0.5）而不是过滤 —— 不喜欢不等于不能吃，两套语义刻意区分。</p>
            <div class="bg-slate-900 rounded-lg px-3.5 py-3">
              <p class="text-[12px] text-slate-300 leading-relaxed">排序函数的输入集只能是过滤节点的输出集 —— <span class="text-white font-semibold">代码结构本身杜绝「打分后放回」</span>。</p>
            </div>
          </div>
        </div>

        <div class="bg-white border border-slate-200 rounded-xl p-5 shadow-sm flex flex-col">
          <h3 class="text-[18px] font-bold text-slate-800 mb-1">排序：7 因子与结果契约</h3>
          <p class="text-[12px] text-slate-400 font-mono mb-3">权重存于远程配置，可热调而不发版</p>
          <div class="grid grid-cols-4 gap-1.5 mb-3">
            <div class="bg-cyan-50 border border-cyan-200 rounded-md px-1.5 py-1.5 text-center">
              <p class="text-[10px] text-cyan-800">coverage</p><p class="text-[14px] font-bold font-mono text-cyan-700">.30</p><p class="text-[10px] text-emerald-600">生效</p>
            </div>
            <div class="bg-slate-50 border border-slate-200 rounded-md px-1.5 py-1.5 text-center">
              <p class="text-[10px] text-slate-500">expiring</p><p class="text-[14px] font-bold font-mono text-slate-400">.15</p><p class="text-[10px] text-slate-400">未启用</p>
            </div>
            <div class="bg-slate-50 border border-slate-200 rounded-md px-1.5 py-1.5 text-center">
              <p class="text-[10px] text-slate-500">taste</p><p class="text-[14px] font-bold font-mono text-slate-400">.15</p><p class="text-[10px] text-slate-400">未启用</p>
            </div>
            <div class="bg-slate-50 border border-slate-200 rounded-md px-1.5 py-1.5 text-center">
              <p class="text-[10px] text-slate-500">goal</p><p class="text-[14px] font-bold font-mono text-slate-400">.15</p><p class="text-[10px] text-slate-400">未启用</p>
            </div>
            <div class="bg-sky-50 border border-sky-200 rounded-md px-1.5 py-1.5 text-center">
              <p class="text-[10px] text-sky-800">difficulty</p><p class="text-[14px] font-bold font-mono text-sky-700">.10</p><p class="text-[10px] text-emerald-600">生效</p>
            </div>
            <div class="bg-slate-50 border border-slate-200 rounded-md px-1.5 py-1.5 text-center">
              <p class="text-[10px] text-slate-500">history</p><p class="text-[14px] font-bold font-mono text-slate-400">.10</p><p class="text-[10px] text-slate-400">未启用</p>
            </div>
            <div class="bg-slate-50 border border-slate-200 rounded-md px-1.5 py-1.5 text-center">
              <p class="text-[10px] text-slate-500">popularity</p><p class="text-[14px] font-bold font-mono text-slate-400">.05</p><p class="text-[10px] text-slate-400">未启用</p>
            </div>
            <div class="bg-white border border-dashed border-slate-300 rounded-md px-1.5 py-1.5 flex items-center justify-center">
              <p class="text-[10px] text-slate-400 leading-tight text-center">无效权重<br/>摊给 coverage</p>
            </div>
          </div>
          <div class="space-y-1.5 flex-1">
            <p class="text-[12px] text-slate-500 leading-relaxed"><span class="font-semibold text-slate-700">结果分档：</span>按缺失食材数分为「全齐 / 缺 1-2 道 / 缺 3 道以上」三档，缺失过多整条跳过。</p>
            <p class="text-[12px] text-slate-500 leading-relaxed"><span class="font-semibold text-slate-700">只取前 8 条：</span>不足时如实提示「现有食材组合有限，宁缺毋滥」，不填充低分菜谱。</p>
            <p class="text-[12px] text-slate-500 leading-relaxed"><span class="font-semibold text-slate-700">可解释：</span>卡片提供「为什么推荐给你」入口，展开即为 <span class="font-mono text-[11px]">rank_reasons</span>。</p>
          </div>
          <div class="mt-3 bg-amber-50 border border-amber-200 rounded-lg px-3.5 py-2.5">
            <p class="text-[12px] text-amber-800 leading-relaxed">
              <span class="font-semibold">阶段一真实排序口径：</span>实际仅 coverage 与 difficulty 生效，其余因子接口已就位但权重为 0，随阶段二行为数据积累逐项启用。
            </p>
          </div>
        </div>
      </div>

      <div class="mt-3 flex items-center justify-between text-[13px] text-slate-400">
        <span class="font-mono tracking-wider">AI 厨娘 · 智能烹饪助手 · 项目答辩</span>
        <span class="font-mono">11 / 25</span>
      </div>
    </div>
  </div>
`);
