window.slideDataMap.set(2, `
  <div class="w-[1440px] h-[810px] relative overflow-hidden slide-bg">
    <div class="absolute inset-0" style="background-image: linear-gradient(#E6EDF5 1px, transparent 1px), linear-gradient(90deg,#E6EDF5 1px, transparent 1px); background-size: 48px 48px;"></div>
    <div class="absolute top-0 left-0 w-full h-[10px] bg-cyan-700"></div>

    <div class="w-[1350px] h-[720px] mx-auto my-[45px] relative z-10 flex flex-col justify-center pt-6">
      <div class="flex items-end justify-between mb-9">
        <div>
          <h2 class="text-[46px] font-bold text-slate-900 mb-2">目录 <span class="text-[26px] font-normal text-slate-400 font-mono tracking-widest">CONTENTS</span></h2>
          <p class="text-[16px] text-slate-500">四个部分，回答三个问题：做了什么、怎么做的、学到了什么</p>
        </div>
        <div class="text-right">
          <p class="text-[13px] text-slate-400 font-mono">25 PAGES · 4 CHAPTERS</p>
          <p class="text-[13px] text-slate-400 font-mono">2026.10.14</p>
        </div>
      </div>

      <div class="space-y-4">
        <div class="flex items-center gap-7 bg-white border border-slate-200 border-l-[6px] border-l-cyan-700 rounded-xl px-8 py-5 shadow-sm">
          <span class="text-[40px] font-bold text-cyan-700 font-mono leading-none w-[70px]">01</span>
          <div class="flex-1">
            <h3 class="text-[24px] font-bold text-slate-800 mb-1">项目概述与技术架构</h3>
            <p class="text-[15px] text-slate-500">项目背景与产品定位 · 协作模式与交付物 · 交付成果核心指标 · 五层系统架构 · 技术栈选型 · 数据与语料资产</p>
          </div>
          <span class="text-[13px] text-cyan-700 bg-cyan-50 border border-cyan-200 rounded-full px-4 py-1.5 font-medium whitespace-nowrap">7 页</span>
        </div>

        <div class="flex items-center gap-7 bg-white border border-slate-200 border-l-[6px] border-l-orange-600 rounded-xl px-8 py-5 shadow-sm">
          <span class="text-[40px] font-bold text-orange-600 font-mono leading-none w-[70px]">02</span>
          <div class="flex-1">
            <h3 class="text-[24px] font-bold text-slate-800 mb-1">重点模块与精彩代码</h3>
            <p class="text-[15px] text-slate-500">智能菜谱推荐 · <span class="text-orange-600 font-semibold">LangGraph 主图拓扑</span> · 路由机制与两张子图 · 图结构运行期校验与自检发现 · 食品安全风控 · 其余核心能力速览 · 两段关键代码 · 真实界面演示</p>
          </div>
          <span class="text-[13px] text-orange-600 bg-orange-50 border border-orange-200 rounded-full px-4 py-1.5 font-medium whitespace-nowrap">10 页</span>
        </div>

        <div class="flex items-center gap-7 bg-white border border-slate-200 border-l-[6px] border-l-indigo-600 rounded-xl px-8 py-5 shadow-sm">
          <span class="text-[40px] font-bold text-indigo-600 font-mono leading-none w-[70px]">03</span>
          <div class="flex-1">
            <h3 class="text-[24px] font-bold text-slate-800 mb-1">问题与解决方案</h3>
            <p class="text-[15px] text-slate-500">六类问题 × 方案 × 验证结果总览 · 四个典型案例深剖（检索缺口 / 构建 OOM / 镜像加速失效 / 语音静默失效）</p>
          </div>
          <span class="text-[13px] text-indigo-600 bg-indigo-50 border border-indigo-200 rounded-full px-4 py-1.5 font-medium whitespace-nowrap">3 页</span>
        </div>

        <div class="flex items-center gap-7 bg-white border border-slate-200 border-l-[6px] border-l-emerald-600 rounded-xl px-8 py-5 shadow-sm">
          <span class="text-[40px] font-bold text-emerald-600 font-mono leading-none w-[70px]">04</span>
          <div class="flex-1">
            <h3 class="text-[24px] font-bold text-slate-800 mb-1">项目完成后的收获</h3>
            <p class="text-[15px] text-slate-500">技术深度 · 工程能力 · 产品思维 · 协作规范 · 风险意识 —— 从「能跑」到「敢上线」的五项成长</p>
          </div>
          <span class="text-[13px] text-emerald-600 bg-emerald-50 border border-emerald-200 rounded-full px-4 py-1.5 font-medium whitespace-nowrap">2 页</span>
        </div>
      </div>

      <div class="mt-8 flex items-center gap-8 text-[14px] text-slate-500 bg-white/80 border border-slate-200 rounded-xl px-8 py-4">
        <span class="font-medium text-slate-700">本次答辩重点：</span>
        <span class="flex items-center gap-2"><span class="w-2 h-2 rounded-full bg-cyan-700"></span>三大核心模块的实现路径</span>
        <span class="flex items-center gap-2"><span class="w-2 h-2 rounded-full bg-orange-600"></span>LangGraph 图结构与编排设计</span>
        <span class="flex items-center gap-2"><span class="w-2 h-2 rounded-full bg-indigo-600"></span>问题排查与工程取舍</span>
      </div>
    </div>
  </div>
`);
