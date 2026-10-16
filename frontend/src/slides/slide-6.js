window.slideDataMap.set(6, `
  <div class="w-[1440px] h-[810px] relative overflow-hidden slide-bg">
    <div class="absolute top-0 left-0 w-full h-[8px] bg-cyan-700"></div>
    <div class="w-[1350px] h-[720px] mx-auto my-[45px] relative pt-4 flex flex-col">

      <div class="flex items-center justify-between mb-7">
        <div class="flex items-center gap-4">
          <div class="w-[6px] h-11 bg-cyan-700 rounded"></div>
          <div>
            <h2 class="text-[38px] font-bold text-slate-900 leading-tight">交付成果核心指标</h2>
            <p class="text-[15px] text-slate-500 mt-1">全部数据来自本地实测与线上实探，可用附录命令独立复现</p>
          </div>
        </div>
        <div class="bg-white border border-slate-200 rounded-xl px-6 py-3 text-right shadow-sm">
          <p class="text-[12px] text-slate-400 font-mono mb-1">WEIGHTED COMPLETION</p>
          <p class="text-[32px] font-bold text-cyan-700 font-mono leading-none">≈ 88<span class="text-[18px]">%</span></p>
        </div>
      </div>

      <div class="grid grid-cols-4 gap-5 mb-6">
        <div class="bg-white border border-slate-200 border-t-[5px] border-t-cyan-700 rounded-xl px-5 py-5 shadow-sm">
          <p class="text-[38px] font-bold text-cyan-700 font-mono leading-none mb-2">74</p>
          <p class="text-[16px] font-semibold text-slate-800 mb-1">交付页面（三端）</p>
          <p class="text-[13px] text-slate-500 leading-relaxed">Web 16 + 微信小程序 42 + 管理后台 16，全部完成注册与路由配置</p>
        </div>
        <div class="bg-white border border-slate-200 border-t-[5px] border-t-orange-600 rounded-xl px-5 py-5 shadow-sm">
          <p class="text-[38px] font-bold text-orange-600 font-mono leading-none mb-2">47,736</p>
          <p class="text-[16px] font-semibold text-slate-800 mb-1">前端代码行数</p>
          <p class="text-[13px] text-slate-500 leading-relaxed">Web 18,486 + 后台 3,375 + 小程序 25,875，逻辑层通过共享包复用</p>
        </div>
        <div class="bg-white border border-slate-200 border-t-[5px] border-t-indigo-600 rounded-xl px-5 py-5 shadow-sm">
          <p class="text-[38px] font-bold text-indigo-600 font-mono leading-none mb-2">121</p>
          <p class="text-[16px] font-semibold text-slate-800 mb-1">后端接口端点</p>
          <p class="text-[13px] text-slate-500 leading-relaxed">118 个 py 模块、3 个数据库迁移、46 个测试文件，覆盖推荐与风控全链路</p>
        </div>
        <div class="bg-white border border-slate-200 border-t-[5px] border-t-emerald-600 rounded-xl px-5 py-5 shadow-sm">
          <p class="text-[38px] font-bold text-emerald-600 font-mono leading-none mb-2">319</p>
          <p class="text-[16px] font-semibold text-slate-800 mb-1">后端单测通过</p>
          <p class="text-[13px] text-slate-500 leading-relaxed">319 passed / 1 skipped；前端另有 236 + 45 条用例，43 条 E2E 全闭环</p>
        </div>
      </div>

      <div class="flex gap-5 flex-1">
        <div class="w-[62%] bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
          <h3 class="text-[19px] font-bold text-slate-800 mb-4">三端实现明细</h3>
          <div class="space-y-4">
            <div>
              <div class="flex items-center justify-between mb-1.5">
                <span class="text-[15px] font-semibold text-slate-700">Web 演示端 <span class="font-mono text-slate-400 text-[13px]">web-stage1</span></span>
                <span class="text-[14px] font-mono text-slate-500">16 页 · 18,486 行</span>
              </div>
              <div class="h-2.5 bg-slate-100 rounded-full overflow-hidden"><div class="h-full bg-cyan-700 rounded-full" style="width:100%"></div></div>
              <p class="text-[13px] text-slate-500 mt-1.5">Vue 3 + Vite + TS + Pinia + Element Plus；含 W-06 Agent 调度可视化面板等专属交付页</p>
            </div>
            <div>
              <div class="flex items-center justify-between mb-1.5">
                <span class="text-[15px] font-semibold text-slate-700">微信小程序 <span class="font-mono text-slate-400 text-[13px]">web-mini</span></span>
                <span class="text-[14px] font-mono text-slate-500">42 页 · 25,875 行</span>
              </div>
              <div class="h-2.5 bg-slate-100 rounded-full overflow-hidden"><div class="h-full bg-orange-600 rounded-full" style="width:100%"></div></div>
              <p class="text-[13px] text-slate-500 mt-1.5">uni-app + Vue 3 + Pinia，六个分包：主包 / recommend / cooking / nutrition / member / innovation</p>
            </div>
            <div>
              <div class="flex items-center justify-between mb-1.5">
                <span class="text-[15px] font-semibold text-slate-700">管理后台 <span class="font-mono text-slate-400 text-[13px]">admin-web</span></span>
                <span class="text-[14px] font-mono text-slate-500">16 页 · 3,375 行</span>
              </div>
              <div class="h-2.5 bg-slate-100 rounded-full overflow-hidden"><div class="h-full bg-indigo-600 rounded-full" style="width:100%"></div></div>
              <p class="text-[13px] text-slate-500 mt-1.5">风控规则、违禁词、创新巡检、开关管理（远程配置）、操作日志、调度日志等运营侧能力</p>
            </div>
          </div>
        </div>

        <div class="w-[38%] bg-white border border-slate-200 rounded-xl p-6 shadow-sm flex flex-col">
          <h3 class="text-[19px] font-bold text-slate-800 mb-4">质量与上线</h3>
          <div class="space-y-3 flex-1">
            <div class="flex items-center justify-between bg-slate-50 rounded-lg px-4 py-3">
              <span class="text-[14px] text-slate-600">页面实测可达</span>
              <span class="text-[15px] font-bold text-emerald-600 font-mono">16 / 16</span>
            </div>
            <div class="flex items-center justify-between bg-slate-50 rounded-lg px-4 py-3">
              <span class="text-[14px] text-slate-600">控制台 Error</span>
              <span class="text-[15px] font-bold text-emerald-600 font-mono">0</span>
            </div>
            <div class="flex items-center justify-between bg-slate-50 rounded-lg px-4 py-3">
              <span class="text-[14px] text-slate-600">安全红线</span>
              <span class="text-[15px] font-bold text-emerald-600 font-mono">12 条全绿</span>
            </div>
            <div class="flex items-center justify-between bg-slate-50 rounded-lg px-4 py-3">
              <span class="text-[14px] text-slate-600">E2E 用例</span>
              <span class="text-[15px] font-bold text-slate-700 font-mono">43 条 · 缺陷全闭环</span>
            </div>
            <div class="bg-cyan-50 border border-cyan-200 rounded-lg px-4 py-3">
              <p class="text-[13px] text-cyan-800 mb-1 font-semibold">生产环境实探</p>
              <p class="text-[13px] text-cyan-700 font-mono leading-relaxed">YOUR_SERVER_IP:8005<br/>用户端 / 后台 / healthz 全部 200，DB up</p>
            </div>
          </div>
        </div>
      </div>

      <div class="mt-4 flex items-center justify-between text-[13px] text-slate-400">
        <span class="font-mono tracking-wider">AI 厨娘 · 智能烹饪助手 · 项目答辩</span>
        <span class="font-mono">06 / 25</span>
      </div>
    </div>
  </div>
`);
