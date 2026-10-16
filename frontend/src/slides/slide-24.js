window.slideDataMap.set(24, `
  <div class="w-[1440px] h-[810px] relative overflow-hidden slide-bg">
    <div class="absolute top-0 left-0 w-full h-[8px] bg-emerald-600"></div>
    <div class="w-[1350px] h-[720px] mx-auto my-[45px] relative pt-4 flex flex-col">

      <div class="flex items-center justify-between mb-4">
        <div class="flex items-center gap-4">
          <div class="w-[6px] h-[42px] bg-emerald-600 rounded"></div>
          <div>
            <h2 class="text-[36px] font-bold text-slate-900 leading-tight">项目完成后的收获</h2>
            <p class="text-[15px] text-slate-500 mt-1">从「能跑」到「敢上线」的五项成长 · 三端 74 页 · 47,736 行代码 · 121 个接口</p>
          </div>
        </div>
        <span class="px-4 py-2 bg-emerald-50 border border-emerald-200 text-emerald-700 rounded-full text-[13px] font-medium">五项成长 + 一句总结</span>
      </div>

      <div class="bg-white border border-slate-200 border-l-4 border-l-emerald-600 rounded-xl px-6 py-3.5 shadow-sm mb-4">
        <p class="text-[15px] text-slate-700 leading-relaxed">
          这个项目最大的收获不是「把功能写完」，而是理解了<span class="font-semibold text-emerald-700">软件质量取决于结构，而不是取决于人的自觉</span> ——
          安全不靠开发者记得过滤，而靠代码的调用关系保证一定过滤；一致性不靠逐页点检，而靠注册表与契约保证不会漏。
        </p>
      </div>

      <div class="grid grid-cols-3 grid-rows-2 gap-4 flex-1">
        <div class="bg-white border border-slate-200 border-t-4 border-t-cyan-700 rounded-xl p-5 shadow-sm flex flex-col">
          <div class="flex items-center gap-2.5 mb-2.5">
            <span class="w-7 h-7 rounded-lg bg-cyan-700 text-white flex items-center justify-center text-[13px] font-bold font-mono">01</span>
            <h3 class="text-[17px] font-bold text-slate-800">技术深度：吃透多智能体编排</h3>
          </div>
          <p class="text-[13px] text-slate-600 leading-relaxed">
            第一次把业务系统真正拆成「图」：22 个节点、条件边短路、并行分支汇合、子图嵌套、状态在节点间流转。
            更深一层的收获是理解了<span class="font-semibold text-slate-800">大模型应该被放在哪里</span> —— 让它只做擅长的意图识别，
            把安全判定与排序计算交回规则与算法。
          </p>
        </div>

        <div class="bg-white border border-slate-200 border-t-4 border-t-indigo-600 rounded-xl p-5 shadow-sm flex flex-col">
          <div class="flex items-center gap-2.5 mb-2.5">
            <span class="w-7 h-7 rounded-lg bg-indigo-600 text-white flex items-center justify-center text-[13px] font-bold font-mono">02</span>
            <h3 class="text-[17px] font-bold text-slate-800">工程能力：质量基线与可复现</h3>
          </div>
          <p class="text-[13px] text-slate-600 leading-relaxed">
            后端 319 条单测、Web 端 236 条、小程序端 45 条、43 条端到端用例与 12 条安全红线用例 ——
            它们的意义不在于数量，而在于让「改一处会不会弄坏别处」有了确定答案。同时学会让结果<span class="font-semibold text-slate-800">可复现</span>：
            部署写脚本、口径写文档、结论附命令。
          </p>
        </div>

        <div class="bg-white border border-slate-200 border-t-4 border-t-orange-600 rounded-xl p-5 shadow-sm flex flex-col">
          <div class="flex items-center gap-2.5 mb-2.5">
            <span class="w-7 h-7 rounded-lg bg-orange-600 text-white flex items-center justify-center text-[13px] font-bold font-mono">03</span>
            <h3 class="text-[17px] font-bold text-slate-800">产品思维：用户敢不敢用</h3>
          </div>
          <p class="text-[13px] text-slate-600 leading-relaxed">
            推荐不足时如实说明「宁缺毋滥」而不是用低分菜谱填满列表；被过滤的菜谱提供开关让用户查看原因；营养缺失时标注「未纳入统计」而不是静默按 0 计算。
            这些在功能清单上都不算新功能，却决定了用户是否相信产品 —— <span class="font-semibold text-slate-800">可信度本身就是产品力</span>。
          </p>
        </div>

        <div class="bg-white border border-slate-200 border-t-4 border-t-sky-600 rounded-xl p-5 shadow-sm flex flex-col">
          <div class="flex items-center gap-2.5 mb-2.5">
            <span class="w-7 h-7 rounded-lg bg-sky-600 text-white flex items-center justify-center text-[13px] font-bold font-mono">04</span>
            <h3 class="text-[17px] font-bold text-slate-800">协作规范：把约定变成流程</h3>
          </div>
          <p class="text-[13px] text-slate-600 leading-relaxed">
            在真实甲乙方协作中第一次体会到流程的价值：需求变更一律走变更单、口头变更无效，文档权限分层、冲突以需求文档为准、术语口径严格区分。
            看似繁琐，但它让「上次明明说好了」这类争议不再发生 —— <span class="font-semibold text-slate-800">规范的作用是降低沟通成本</span>。
          </p>
        </div>

        <div class="bg-white border border-slate-200 border-t-4 border-t-rose-600 rounded-xl p-5 shadow-sm flex flex-col">
          <div class="flex items-center gap-2.5 mb-2.5">
            <span class="w-7 h-7 rounded-lg bg-rose-600 text-white flex items-center justify-center text-[13px] font-bold font-mono">05</span>
            <h3 class="text-[17px] font-bold text-slate-800">风险意识：把没做完的写在明面上</h3>
          </div>
          <p class="text-[13px] text-slate-600 leading-relaxed">
            项目后期主动整理了 11 条风险（R-23 ~ R-33），包含备案资质周期、程序倒挂、服务器内存压力、语音依赖 HTTPS 等尚未闭环的问题，
            并逐条标注概率、影响与应对方式。这一课很重要：<span class="font-semibold text-slate-800">把风险说出来不是暴露短板，而是让项目可控</span>。
          </p>
        </div>

        <div class="bg-slate-900 rounded-xl p-5 flex flex-col">
          <div class="flex items-center gap-2.5 mb-2.5">
            <span class="w-7 h-7 rounded-lg bg-white/15 text-white flex items-center justify-center text-[13px] font-bold font-mono">06</span>
            <h3 class="text-[17px] font-bold text-white">一句话总结</h3>
          </div>
          <p class="text-[13px] text-slate-300 leading-relaxed mb-3">
            这次项目让我真正明白：一个能跑通的 Demo，和一个敢交给用户的产品之间，隔着的正是这些看不见的结构、契约与流程。
          </p>
          <div class="mt-auto pt-3 border-t border-white/10">
            <p class="text-[12px] text-slate-400 leading-relaxed">下一步计划：补齐备案与签约资质、上 HTTPS 域名、落地语义向量升级与埋点体系，把阶段二小程序推上正式环境。</p>
          </div>
        </div>
      </div>

      <div class="mt-3 flex items-center justify-between text-[13px] text-slate-400">
        <span class="font-mono tracking-wider">AI 厨娘 · 智能烹饪助手 · 项目答辩</span>
        <span class="font-mono">24 / 25</span>
      </div>
    </div>
  </div>
`);
