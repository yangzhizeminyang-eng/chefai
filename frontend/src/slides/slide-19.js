window.slideDataMap.set(19, `
  <div class="w-[1440px] h-[810px] relative overflow-hidden slide-bg">
    <div class="absolute top-0 left-0 w-full h-[8px] bg-cyan-700"></div>
    <div class="w-[1350px] h-[720px] mx-auto my-[45px] relative pt-4 flex flex-col">

      <div class="flex items-end justify-between mb-4">
        <div class="flex items-center gap-4">
          <div class="w-[6px] h-[42px] bg-cyan-700 rounded"></div>
          <div>
            <h2 class="text-[36px] font-bold text-slate-900 leading-tight">功能演示 · 真实界面</h2>
            <p class="text-[15px] text-slate-500 mt-1">浏览器自动化实测 · 真实导航 + 交互操作 + 截图取证</p>
          </div>
        </div>
        <div class="flex gap-7">
          <div class="text-center">
            <p class="text-[26px] font-bold text-cyan-700 font-mono leading-none mb-1">16/16</p>
            <p class="text-[13px] text-slate-500">页面可达</p>
          </div>
          <div class="text-center">
            <p class="text-[26px] font-bold text-emerald-600 font-mono leading-none mb-1">0</p>
            <p class="text-[13px] text-slate-500">控制台 Error</p>
          </div>
          <div class="text-center">
            <p class="text-[26px] font-bold text-orange-600 font-mono leading-none mb-1">19</p>
            <p class="text-[13px] text-slate-500">截图存证</p>
          </div>
        </div>
      </div>

      <div class="grid grid-cols-2 gap-4 flex-1">
        <div class="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm flex flex-col">
          <img src="/assets/images/03-recommend.png" class="w-full h-[198px] object-cover object-top"/>
          <div class="px-4 py-2.5 border-t border-slate-200 flex-1">
            <p class="text-[16px] font-bold text-slate-800 mb-1">推荐结果页 · 可解释的推荐</p>
            <p class="text-[13px] text-slate-500 leading-relaxed">按匹配程度分三档分组，卡片展示耗时、难度、热量、覆盖率与缺失食材；提供「为什么推荐给你」入口与被过滤明细重放开关；匹配不足时如实说明并提示「宁缺毋滥」。</p>
          </div>
        </div>

        <div class="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm flex flex-col">
          <img src="/assets/images/06-recipe-detail.png" class="w-full h-[198px] object-cover object-top"/>
          <div class="px-4 py-2.5 border-t border-slate-200 flex-1">
            <p class="text-[16px] font-bold text-slate-800 mb-1">菜谱详情页 · 安全信息前置</p>
            <p class="text-[13px] text-slate-500 leading-relaxed">顶部常驻致敏原警示条（实测检出大豆）；主料、辅料、调味料三表用量量化并逐行标注致敏原；支持份数缩放重算；页面底部给出营养估算入口与设备要求。</p>
          </div>
        </div>

        <div class="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm flex flex-col">
          <img src="/assets/images/07-cook-guide.png" class="w-full h-[198px] object-cover object-top"/>
          <div class="px-4 py-2.5 border-t border-slate-200 flex-1">
            <p class="text-[16px] font-bold text-slate-800 mb-1">分步烹饪引导 · 厨房场景优先</p>
            <p class="text-[13px] text-slate-500 leading-relaxed">大字单步显示，进度条标注「第 N 步 / 共 M 步」；上一步下一步本地即时切换无需网络；并行计时器提供 5 个预设计时与自定义；退出需二次确认，支持断点续做。</p>
          </div>
        </div>

        <div class="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm flex flex-col">
          <img src="/assets/images/08-blocked.png" class="w-full h-[198px] object-cover object-top"/>
          <div class="px-4 py-2.5 border-t border-slate-200 flex-1">
            <p class="text-[16px] font-bold text-slate-800 mb-1">风控拦截页 · 真实触发</p>
            <p class="text-[13px] text-slate-500 leading-relaxed">实测输入「发芽土豆能吃吗」命中 FS-003，页面三段式呈现风险说明、正确做法与就医引导，并明确标注「本次请求未生成任何内容」，同时提供「我认为这是误判」的上报入口。</p>
          </div>
        </div>
      </div>

      <div class="mt-3 bg-white border border-slate-200 rounded-lg px-5 py-2.5 flex items-center gap-8 text-[13px] text-slate-600 shadow-sm">
        <span class="font-medium text-slate-700">核心链路验证：</span>
        <span class="flex items-center gap-2"><span class="w-2 h-2 rounded-full bg-cyan-700"></span>选食材 → 推荐 → 详情 → 烹饪 全链路跑通</span>
        <span class="flex items-center gap-2"><span class="w-2 h-2 rounded-full bg-rose-600"></span>风控链路真实触发并正确拦截</span>
        <span class="flex items-center gap-2"><span class="w-2 h-2 rounded-full bg-indigo-600"></span>路由守卫：未选食材 / 无拦截数据 / 未知路径均正确重定向</span>
      </div>
    </div>
  </div>
`);
