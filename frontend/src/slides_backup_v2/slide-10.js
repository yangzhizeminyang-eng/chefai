window.slideDataMap.set(10, `
  <div class="w-[1440px] h-[810px] relative overflow-hidden slide-bg flex items-center justify-center">
    <div class="absolute inset-0" style="background-image: linear-gradient(#E6EDF5 1px, transparent 1px), linear-gradient(90deg,#E6EDF5 1px, transparent 1px); background-size: 48px 48px;"></div>
    <div class="absolute -top-40 -left-32 w-[520px] h-[520px] bg-orange-100 rounded-full blur-3xl opacity-60"></div>

    <div class="w-[1180px] bg-white rounded-3xl border border-slate-200 shadow-sm px-16 py-12 relative overflow-hidden">
      <div class="absolute left-0 top-0 w-full h-[8px] bg-orange-600"></div>
      <div class="absolute right-10 top-6 text-[150px] font-bold text-slate-50 font-mono leading-none select-none">02</div>

      <div class="relative">
        <div class="inline-flex items-center gap-2 bg-orange-50 border border-orange-200 text-orange-700 px-4 py-1.5 rounded-full text-[14px] font-medium mb-6">
          CHAPTER 02
        </div>
        <h1 class="text-[54px] font-bold text-slate-900 mb-4 tracking-tight">重点模块与精彩代码</h1>
        <p class="text-[20px] text-slate-500 mb-10 leading-relaxed">
          本部分回答「到底怎么做的」：三个核心模块的真实实现路径，其中包含完整的 LangGraph 图结构与子图拆解，以及两段最能体现设计取舍的代码。
        </p>

        <div class="grid grid-cols-4 gap-5">
          <div class="bg-slate-50 border border-slate-200 rounded-xl px-5 py-5">
            <p class="text-[30px] font-bold text-cyan-700 font-mono leading-none mb-2">5</p>
            <p class="text-[14px] text-slate-500 leading-relaxed">推荐子图节点数，全程不调用大模型</p>
          </div>
          <div class="bg-slate-50 border border-slate-200 rounded-xl px-5 py-5">
            <p class="text-[30px] font-bold text-orange-600 font-mono leading-none mb-2">22</p>
            <p class="text-[14px] text-slate-500 leading-relaxed">LangGraph 编排节点（主图 13 + 子图 9）</p>
          </div>
          <div class="bg-slate-50 border border-slate-200 rounded-xl px-5 py-5">
            <p class="text-[30px] font-bold text-indigo-600 font-mono leading-none mb-2">27</p>
            <p class="text-[14px] text-slate-500 leading-relaxed">风控规则条数，纯规则引擎零大模型调用</p>
          </div>
          <div class="bg-slate-50 border border-slate-200 rounded-xl px-5 py-5">
            <p class="text-[30px] font-bold text-emerald-600 font-mono leading-none mb-2">3</p>
            <p class="text-[14px] text-slate-500 leading-relaxed">终止出口：finalize / 安全响应 / 保守模式</p>
          </div>
        </div>
      </div>
    </div>
  </div>
`);
