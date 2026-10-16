window.slideDataMap.set(5, `
  <div class="w-[1440px] h-[810px] relative overflow-hidden slide-bg">
    <div class="absolute top-0 left-0 w-full h-[8px] bg-cyan-700"></div>
    <div class="w-[1350px] h-[720px] mx-auto my-[45px] relative pt-4 flex flex-col">

      <div class="flex items-center gap-4 mb-6">
        <div class="w-[6px] h-11 bg-cyan-700 rounded"></div>
        <div>
          <h2 class="text-[38px] font-bold text-slate-900 leading-tight">协作模式与交付物</h2>
          <p class="text-[15px] text-slate-500 mt-1">甲乙方外包 · 我方为乙方（开发方）· 交付物 B-D1 ~ B-D8 八类</p>
        </div>
      </div>

      <div class="flex gap-6 flex-1">
        <div class="w-[41%] bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
          <h3 class="text-[20px] font-bold text-slate-800 mb-4">四条协作约定</h3>
          <div class="space-y-4">
            <div class="flex gap-3">
              <span class="w-7 h-7 rounded-lg bg-cyan-50 border border-cyan-200 text-cyan-700 flex items-center justify-center text-[13px] font-bold flex-shrink-0">01</span>
              <div>
                <p class="text-[16px] font-semibold text-slate-800 mb-1">文档权限分层</p>
                <p class="text-[14px] text-slate-600 leading-relaxed">01 需求基线乙方只能评论不能修改；06 合规区只读；07 项目管理区双方共编。权限边界清晰，避免需求被单方面改动。</p>
              </div>
            </div>
            <div class="flex gap-3">
              <span class="w-7 h-7 rounded-lg bg-cyan-50 border border-cyan-200 text-cyan-700 flex items-center justify-center text-[13px] font-bold flex-shrink-0">02</span>
              <div>
                <p class="text-[16px] font-semibold text-slate-800 mb-1">冲突以需求文档为准</p>
                <p class="text-[14px] text-slate-600 leading-relaxed">乙方产出的 PRD 与需求文档发生冲突时，一律以甲方需求文档为准。PRD 不重写需求，只做交互细化与章节引用。</p>
              </div>
            </div>
            <div class="flex gap-3">
              <span class="w-7 h-7 rounded-lg bg-orange-50 border border-orange-200 text-orange-600 flex items-center justify-center text-[13px] font-bold flex-shrink-0">03</span>
              <div>
                <p class="text-[16px] font-semibold text-slate-800 mb-1">变更必须走变更单</p>
                <p class="text-[14px] text-slate-600 leading-relaxed">任何需求调整都必须提报 <span class="font-mono text-orange-600">CR-YYYYMMDD-NN</span> 变更单，<span class="font-semibold">口头变更一律无效</span>，保证需求基线可追溯。</p>
              </div>
            </div>
            <div class="flex gap-3">
              <span class="w-7 h-7 rounded-lg bg-indigo-50 border border-indigo-200 text-indigo-600 flex items-center justify-center text-[13px] font-bold flex-shrink-0">04</span>
              <div>
                <p class="text-[16px] font-semibold text-slate-800 mb-1">术语口径统一</p>
                <p class="text-[14px] text-slate-600 leading-relaxed"><span class="font-mono">US-xx</span> 用户故事 ｜ <span class="font-mono">FR-x.x</span> 功能需求 ｜ <span class="font-mono">NFR-x</span> 非功能 ｜ <span class="font-mono">RL-x</span> 合规红线 ｜ <span class="font-mono">Q-xx</span> 待确认项。红线与变更单严格区分，不混用。</p>
              </div>
            </div>
          </div>
        </div>

        <div class="w-[59%] flex flex-col gap-5">
          <div class="bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
            <h3 class="text-[20px] font-bold text-slate-800 mb-4">八类交付物清单</h3>
            <div class="grid grid-cols-4 gap-3">
              <div class="bg-slate-50 border border-slate-200 rounded-lg px-3 py-3 text-center">
                <p class="text-[15px] font-bold text-cyan-700 font-mono mb-1">B-D1</p>
                <p class="text-[13px] text-slate-600">PRD 产品需求</p>
              </div>
              <div class="bg-slate-50 border border-slate-200 rounded-lg px-3 py-3 text-center">
                <p class="text-[15px] font-bold text-cyan-700 font-mono mb-1">B-D2</p>
                <p class="text-[13px] text-slate-600">UI 设计稿</p>
              </div>
              <div class="bg-slate-50 border border-slate-200 rounded-lg px-3 py-3 text-center">
                <p class="text-[15px] font-bold text-cyan-700 font-mono mb-1">B-D3</p>
                <p class="text-[13px] text-slate-600">架构设计</p>
              </div>
              <div class="bg-slate-50 border border-slate-200 rounded-lg px-3 py-3 text-center">
                <p class="text-[15px] font-bold text-cyan-700 font-mono mb-1">B-D4</p>
                <p class="text-[13px] text-slate-600">测试方案</p>
              </div>
              <div class="bg-cyan-50 border border-cyan-200 rounded-lg px-3 py-3 text-center">
                <p class="text-[15px] font-bold text-cyan-800 font-mono mb-1">B-D5</p>
                <p class="text-[13px] text-cyan-800">源码交付</p>
              </div>
              <div class="bg-cyan-50 border border-cyan-200 rounded-lg px-3 py-3 text-center">
                <p class="text-[15px] font-bold text-cyan-800 font-mono mb-1">B-D6</p>
                <p class="text-[13px] text-cyan-800">部署运维接口</p>
              </div>
              <div class="bg-cyan-50 border border-cyan-200 rounded-lg px-3 py-3 text-center">
                <p class="text-[15px] font-bold text-cyan-800 font-mono mb-1">B-D7</p>
                <p class="text-[13px] text-cyan-800">测试报告</p>
              </div>
              <div class="bg-cyan-50 border border-cyan-200 rounded-lg px-3 py-3 text-center">
                <p class="text-[15px] font-bold text-cyan-800 font-mono mb-1">B-D8</p>
                <p class="text-[13px] text-cyan-800">开源组件清单</p>
              </div>
            </div>
          </div>

          <div class="bg-white border border-slate-200 rounded-xl p-6 shadow-sm flex-1">
            <h3 class="text-[20px] font-bold text-slate-800 mb-4">交付节奏</h3>
            <div class="relative pl-8">
              <div class="absolute left-[9px] top-2 bottom-2 w-[2px] bg-cyan-200"></div>

              <div class="relative mb-5">
                <span class="absolute -left-8 top-1 w-[20px] h-[20px] rounded-full bg-cyan-700 border-4 border-white shadow"></span>
                <p class="text-[17px] font-bold text-slate-800 mb-1">阶段一 · 7 个工作日：Web 可演示原型</p>
                <p class="text-[14px] text-slate-600 leading-relaxed">合同基准为 6 页（W-01 ~ W-06），实际交付 <span class="font-semibold text-cyan-700">16 页</span>，超额 167%；后端接口、风控引擎、推荐子图同步完成，并提前把 RL-14 敏感信息单独同意落地。</p>
              </div>

              <div class="relative">
                <span class="absolute -left-8 top-1 w-[20px] h-[20px] rounded-full bg-orange-600 border-4 border-white shadow"></span>
                <p class="text-[17px] font-bold text-slate-800 mb-1">阶段二 · 16 周：微信小程序 + 管理后台</p>
                <p class="text-[14px] text-slate-600 leading-relaxed">代码层已完成 42 页小程序与 16 页后台，并全部注册进 pages.json；剩余工作集中在备案、支付签约、真机联调三件事上。</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="mt-4 flex items-center justify-between text-[13px] text-slate-400">
        <span class="font-mono tracking-wider">AI 厨娘 · 智能烹饪助手 · 项目答辩</span>
        <span class="font-mono">05 / 25</span>
      </div>
    </div>
  </div>
`);
