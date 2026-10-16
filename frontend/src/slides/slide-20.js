window.slideDataMap.set(20, `
  <div class="w-[1440px] h-[810px] relative overflow-hidden slide-bg flex items-center justify-center">
    <div class="absolute inset-0" style="background-image: linear-gradient(#E6EDF5 1px, transparent 1px), linear-gradient(90deg,#E6EDF5 1px, transparent 1px); background-size: 48px 48px;"></div>
    <div class="absolute -bottom-40 -right-32 w-[520px] h-[520px] bg-indigo-100 rounded-full blur-3xl opacity-60"></div>

    <div class="w-[1180px] bg-white rounded-3xl border border-slate-200 shadow-sm px-16 py-12 relative overflow-hidden">
      <div class="absolute left-0 top-0 w-full h-[8px] bg-indigo-600"></div>
      <div class="absolute right-10 top-6 text-[150px] font-bold text-slate-50 font-mono leading-none select-none">03</div>

      <div class="relative">
        <div class="inline-flex items-center gap-2 bg-indigo-50 border border-indigo-200 text-indigo-700 px-4 py-1.5 rounded-full text-[14px] font-medium mb-6">
          CHAPTER 03
        </div>
        <h1 class="text-[54px] font-bold text-slate-900 mb-4 tracking-tight">问题与解决方案</h1>
        <p class="text-[20px] text-slate-500 mb-10 leading-relaxed">
          这一部分不复述成绩，只讲踩过的坑：六类问题的「问题 → 方案 → 验证结果」，以及四个从现象追到根因的典型案例。
        </p>

        <div class="grid grid-cols-3 gap-5">
          <div class="bg-slate-50 border border-slate-200 rounded-xl px-6 py-5">
            <p class="text-[30px] font-bold text-indigo-600 font-mono leading-none mb-2">6</p>
            <p class="text-[14px] text-slate-500 leading-relaxed">问题类别，覆盖算法、资源、基础设施与浏览器安全模型</p>
          </div>
          <div class="bg-slate-50 border border-slate-200 rounded-xl px-6 py-5">
            <p class="text-[30px] font-bold text-emerald-600 font-mono leading-none mb-2">3<span class="text-[18px]">/4</span></p>
            <p class="text-[14px] text-slate-500 leading-relaxed">典型案例已闭环，剩余一项已登记为风险并给出触发条件</p>
          </div>
          <div class="bg-slate-50 border border-slate-200 rounded-xl px-6 py-5">
            <p class="text-[30px] font-bold text-cyan-700 font-mono leading-none mb-2">11</p>
            <p class="text-[14px] text-slate-500 leading-relaxed">风险登记册条目（R-23 ~ R-33），未闭环项主动披露</p>
          </div>
        </div>
      </div>
    </div>
  </div>
`);
