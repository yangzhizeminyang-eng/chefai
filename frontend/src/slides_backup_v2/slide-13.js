window.slideDataMap.set(13, `
  <div class="w-[1440px] h-[810px] relative overflow-hidden slide-bg">
    <div class="absolute top-0 left-0 w-full h-[8px] bg-orange-600"></div>
    <div class="w-[1350px] h-[720px] mx-auto my-[45px] relative pt-4 flex flex-col">

      <div class="flex items-center gap-4 mb-5">
        <div class="w-[6px] h-10 bg-orange-600 rounded"></div>
        <div>
          <h2 class="text-[34px] font-bold text-slate-900 leading-tight">LangGraph 子图与关键路径</h2>
          <p class="text-[14px] text-slate-500 mt-0.5">推荐子图的并行分支 · 创新子图的单向状态机 · 三类边的语义与短路路径</p>
        </div>
      </div>

      <div class="flex gap-6 flex-1">
        <div class="w-[51%] bg-white border border-slate-200 rounded-xl p-5 shadow-sm flex flex-col">
          <div class="flex items-center justify-between mb-3">
            <h3 class="text-[18px] font-bold text-slate-800">推荐子图 · 5 节点并行结构</h3>
            <span class="text-[12px] px-3 py-1 bg-cyan-50 border border-cyan-200 text-cyan-800 rounded-full">子图 1 / 9 节点中的 5 个</span>
          </div>

          <div class="relative mx-auto" style="width:620px;height:200px;">
            <svg width="620" height="200" class="absolute left-0 top-0">
              <defs>
                <marker id="sg-ah" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6 z" fill="#64748B"/></marker>
              </defs>
              <path d="M124,99 L138,99" stroke="#64748B" stroke-width="1.6" fill="none" marker-end="url(#sg-ah)"/>
              <path d="M264,99 L278,99" stroke="#64748B" stroke-width="1.6" fill="none" marker-end="url(#sg-ah)"/>
              <path d="M404,99 L416,99" stroke="#64748B" stroke-width="1.6" fill="none"/>
              <path d="M416,43 L416,155" stroke="#64748B" stroke-width="1.6" fill="none"/>
              <path d="M416,43 L430,43" stroke="#64748B" stroke-width="1.6" fill="none" marker-end="url(#sg-ah)"/>
              <path d="M416,155 L430,155" stroke="#64748B" stroke-width="1.6" fill="none" marker-end="url(#sg-ah)"/>
              <path d="M562,43 L578,43" stroke="#64748B" stroke-width="1.6" fill="none"/>
              <path d="M562,155 L578,155" stroke="#64748B" stroke-width="1.6" fill="none"/>
              <path d="M578,43 L578,155" stroke="#64748B" stroke-width="1.6" fill="none"/>
            </svg>

            <div class="absolute rounded-lg border-2 border-cyan-300 bg-cyan-50 flex flex-col items-center justify-center" style="left:0px;top:70px;width:124px;height:58px;">
              <span class="text-[10px] font-mono text-cyan-700">assemble_context</span>
              <span class="text-[12px] text-slate-700 font-medium">上下文归一</span>
            </div>
            <div class="absolute rounded-lg border-2 border-sky-300 bg-sky-50 flex flex-col items-center justify-center" style="left:140px;top:70px;width:124px;height:58px;">
              <span class="text-[10px] font-mono text-sky-700">recipe_retrieve</span>
              <span class="text-[12px] text-slate-700 font-medium">三路混合召回</span>
            </div>
            <div class="absolute rounded-lg border-2 border-orange-300 bg-orange-50 flex flex-col items-center justify-center" style="left:280px;top:70px;width:124px;height:58px;">
              <span class="text-[10px] font-mono text-orange-700">hard_filter</span>
              <span class="text-[12px] text-slate-700 font-medium">布尔硬过滤</span>
            </div>
            <div class="absolute rounded-lg border-2 border-indigo-300 bg-indigo-50 flex flex-col items-center justify-center" style="left:432px;top:14px;width:130px;height:58px;">
              <span class="text-[10px] font-mono text-indigo-700">recipe_rank</span>
              <span class="text-[12px] text-slate-700 font-medium">7 因子加权排序</span>
            </div>
            <div class="absolute rounded-lg border-2 border-emerald-300 bg-emerald-50 flex flex-col items-center justify-center" style="left:432px;top:126px;width:130px;height:58px;">
              <span class="text-[10px] font-mono text-emerald-700">node_nutrition</span>
              <span class="text-[12px] text-slate-700 font-medium">营养估算</span>
            </div>

            <div class="absolute text-[12px] text-slate-400" style="left:334px;top:34px;">并行分支</div>
            <div class="absolute text-[12px] text-slate-400" style="left:436px;top:196px;">→ 汇合后返回主图 compose</div>
          </div>

          <div class="mt-3 space-y-2.5 flex-1">
            <div class="flex gap-3 bg-slate-50 rounded-lg px-4 py-2.5">
              <span class="w-1.5 rounded bg-orange-500 flex-shrink-0"></span>
              <p class="text-[13px] text-slate-600 leading-relaxed"><span class="font-semibold text-slate-800">为什么排序与营养并行：</span>两者互不依赖，串行会白白增加一次往返；并行后用户看到推荐结果的等待时间不受营养计算影响。</p>
            </div>
            <div class="flex gap-3 bg-slate-50 rounded-lg px-4 py-2.5">
              <span class="w-1.5 rounded bg-cyan-600 flex-shrink-0"></span>
              <p class="text-[13px] text-slate-600 leading-relaxed"><span class="font-semibold text-slate-800">为什么硬过滤夹在中间：</span>过滤放在召回之后、排序之前，既缩小了排序输入规模，也从调用关系上保证「只有通过过滤的候选才可能被打分」。</p>
            </div>
            <div class="flex gap-3 bg-amber-50 border border-amber-200 rounded-lg px-4 py-2.5">
              <span class="w-1.5 rounded bg-amber-500 flex-shrink-0"></span>
              <p class="text-[13px] text-amber-800 leading-relaxed"><span class="font-semibold">当前限制：</span>纯手选食材路径不携带文本，因此不触发向量召回，阶段一 RAG 实际只用到「覆盖率 + 文本」两路。该限制已登记为改进项，随语义嵌入模型升级一并解决。</p>
            </div>
          </div>
        </div>

        <div class="w-[49%] flex flex-col gap-4">
          <div class="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
            <h3 class="text-[18px] font-bold text-slate-800 mb-3">创新子图 · 单向状态流转</h3>
            <div class="flex items-center gap-1.5 mb-3 flex-wrap">
              <span class="px-3 py-1.5 bg-slate-100 border border-slate-300 text-slate-700 rounded-md text-[12px] font-mono">precheck</span>
              <span class="text-slate-400 text-[12px]">→</span>
              <span class="px-3 py-1.5 bg-slate-100 border border-slate-300 text-slate-700 rounded-md text-[12px] font-mono">generate</span>
              <span class="text-slate-400 text-[12px]">→</span>
              <span class="px-3 py-1.5 bg-cyan-50 border border-cyan-300 text-cyan-800 rounded-md text-[12px] font-mono">adopted</span>
              <span class="text-slate-400 text-[12px]">→</span>
              <span class="px-3 py-1.5 bg-emerald-50 border border-emerald-300 text-emerald-800 rounded-md text-[12px] font-mono">indexed</span>
              <span class="text-slate-400 text-[12px]">→</span>
              <span class="px-3 py-1.5 bg-rose-50 border border-rose-300 text-rose-700 rounded-md text-[12px] font-mono">removed</span>
            </div>
            <div class="space-y-2">
              <p class="text-[13px] text-slate-600 leading-relaxed">状态流转有硬校验表 <span class="font-mono text-slate-700">_VALID_TRANSITIONS</span>，例如只允许 <span class="font-mono text-[12px]">generated → adopted</span>，非法流转直接返回 422，避免出现「先入索引再补采纳」这类脏数据。</p>
              <p class="text-[13px] text-slate-600 leading-relaxed">预检阶段先过四类校验（高危、过敏原、特殊人群、禁忌），通过后才允许生成；生成长任务走异步任务接口，受理即返回 202，前端轮询进度。</p>
              <p class="text-[13px] text-slate-600 leading-relaxed">创新菜与公共知识库<span class="font-semibold text-slate-800">物理隔离</span>：写入用户私有向量分区，复用仅限本人，跨用户不可见。</p>
            </div>
          </div>

          <div class="bg-white border border-slate-200 rounded-xl p-5 shadow-sm flex-1">
            <h3 class="text-[18px] font-bold text-slate-800 mb-3">三类边的语义</h3>
            <div class="space-y-3">
              <div class="flex gap-3">
                <span class="w-[86px] flex-shrink-0 text-[13px] font-mono text-slate-500 pt-0.5">普通边</span>
                <p class="text-[13px] text-slate-600 leading-relaxed flex-1">按固定顺序推进，用于主链路上的确定性流转，例如召回 → 过滤 → 排序。</p>
              </div>
              <div class="flex gap-3">
                <span class="w-[86px] flex-shrink-0 text-[13px] font-mono text-red-600 pt-0.5">条件边</span>
                <p class="text-[13px] text-slate-600 leading-relaxed flex-1">风控命中即短路到安全响应节点，<span class="font-semibold text-slate-800">业务节点一个都不执行</span>；这是「一票否决」在图层面的实现方式。</p>
              </div>
              <div class="flex gap-3">
                <span class="w-[86px] flex-shrink-0 text-[13px] font-mono text-indigo-600 pt-0.5">并行分支</span>
                <p class="text-[13px] text-slate-600 leading-relaxed flex-1">排序与营养同时展开，各自完成后汇合；两者失败互不影响，营养失败不阻断推荐结果返回。</p>
              </div>
              <div class="bg-cyan-50 border border-cyan-200 rounded-lg px-4 py-3">
                <p class="text-[13px] text-cyan-800 leading-relaxed"><span class="font-semibold">复合意图处理：</span>当一句话同时包含推荐诉求与营养诉求时，路由到复合节点复用推荐子图，营养结果由并行分支直接覆盖，不需要额外再跑一遍。</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="mt-4 flex items-center justify-between text-[13px] text-slate-400">
        <span class="font-mono tracking-wider">AI 厨娘 · 智能烹饪助手 · 项目答辩</span>
        <span class="font-mono">13 / 24</span>
      </div>
    </div>
  </div>
`);
