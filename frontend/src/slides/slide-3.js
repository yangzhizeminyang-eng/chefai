window.slideDataMap.set(3, `
  <div class="w-[1440px] h-[810px] relative overflow-hidden slide-bg flex items-center justify-center">
    <div class="absolute inset-0" style="background-image: linear-gradient(#E6EDF5 1px, transparent 1px), linear-gradient(90deg,#E6EDF5 1px, transparent 1px); background-size: 48px 48px;"></div>
    <div class="absolute -top-40 -right-32 w-[520px] h-[520px] bg-cyan-100 rounded-full blur-3xl opacity-60"></div>

    <div class="w-[1180px] bg-white rounded-3xl border border-slate-200 shadow-sm px-16 py-12 relative overflow-hidden">
      <div class="absolute left-0 top-0 w-full h-[8px] bg-cyan-700"></div>
      <div class="absolute right-10 top-6 text-[150px] font-bold text-slate-50 font-mono leading-none select-none">01</div>

      <div class="relative">
        <div class="inline-flex items-center gap-2 bg-cyan-50 border border-cyan-200 text-cyan-800 px-4 py-1.5 rounded-full text-[14px] font-medium mb-6">
          CHAPTER 01
        </div>
        <h1 class="text-[54px] font-bold text-slate-900 mb-4 tracking-tight">项目概述与技术架构</h1>
        <p class="text-[20px] text-slate-500 mb-10 leading-relaxed">
          先回答「这是什么项目、交付了多少、它长什么样」—— 从产品定位与协作模式，到五层系统架构与技术栈选型，建立全局坐标。
        </p>

        <div class="grid grid-cols-3 gap-6">
          <div class="bg-slate-50 border border-slate-200 rounded-xl px-6 py-5">
            <p class="text-[34px] font-bold text-cyan-700 font-mono leading-none mb-2">74<span class="text-[18px] ml-1">页</span></p>
            <p class="text-[14px] text-slate-500">三端页面总数（Web 16 / 小程序 42 / 后台 16）</p>
          </div>
          <div class="bg-slate-50 border border-slate-200 rounded-xl px-6 py-5">
            <p class="text-[34px] font-bold text-orange-600 font-mono leading-none mb-2">47,736<span class="text-[18px] ml-1">行</span></p>
            <p class="text-[14px] text-slate-500">前端代码量（三端合计）</p>
          </div>
          <div class="bg-slate-50 border border-slate-200 rounded-xl px-6 py-5">
            <p class="text-[34px] font-bold text-indigo-600 font-mono leading-none mb-2">121<span class="text-[18px] ml-1">个</span></p>
            <p class="text-[14px] text-slate-500">后端接口端点（118 个 py 模块）</p>
          </div>
        </div>
      </div>
    </div>
  </div>
`);
