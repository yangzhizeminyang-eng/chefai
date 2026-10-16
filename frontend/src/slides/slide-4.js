window.slideDataMap.set(4, `
  <div class="w-[1440px] h-[810px] relative overflow-hidden slide-bg">
    <div class="absolute top-0 left-0 w-full h-[8px] bg-cyan-700"></div>
    <div class="w-[1350px] h-[720px] mx-auto my-[45px] relative pt-4 flex flex-col">

      <div class="flex items-center gap-4 mb-7">
        <div class="w-[6px] h-11 bg-cyan-700 rounded"></div>
        <div>
          <h2 class="text-[38px] font-bold text-slate-900 leading-tight">项目背景与产品定位</h2>
          <p class="text-[15px] text-slate-500 mt-1">面向家庭做饭人群的智能烹饪助手 · 把「今天吃什么」的决策成本降到最低</p>
        </div>
      </div>

      <div class="flex gap-7 flex-1">
        <div class="w-[49%] flex flex-col gap-4">
          <div class="bg-white border border-slate-200 rounded-xl p-6 shadow-sm flex-1">
            <h3 class="text-[20px] font-bold text-slate-800 mb-3 flex items-center gap-2">
              <span class="w-7 h-7 rounded-lg bg-orange-50 border border-orange-200 text-orange-600 flex items-center justify-center text-[14px] font-bold">1</span>
              真实场景里的四个痛点
            </h3>
            <p class="text-[15px] text-slate-600 leading-relaxed mb-3">
              家庭做饭的困难并不在「不会做菜」，而在决策与核对环节。围绕这一判断，项目立项时明确了四个必须解决的现实问题：
            </p>
            <div class="space-y-2.5">
              <p class="text-[15px] text-slate-600 leading-relaxed"><span class="text-slate-800 font-semibold">① 食材有了，不知道做什么。</span>冰箱里剩三样食材，用户需要在多个菜谱站之间反复比对，最后往往还是点外卖。</p>
              <p class="text-[15px] text-slate-600 leading-relaxed"><span class="text-slate-800 font-semibold">② 菜谱不适配个人条件。</span>网上菜谱不考虑厨艺水平与家里的厨具设备，新手照着做经常卡在第一步。</p>
              <p class="text-[15px] text-slate-600 leading-relaxed"><span class="text-slate-800 font-semibold">③ 过敏原与忌口靠人记。</span>家里有过敏成员时，用户只能逐条阅读配料表自行判断，一旦疏漏后果严重。</p>
              <p class="text-[15px] text-slate-600 leading-relaxed"><span class="text-slate-800 font-semibold">④ 做完不知道营养是否达标。</span>缺少可累积、可回顾的饮食数据，控糖、健身人群无从调整。</p>
            </div>
          </div>
        </div>

        <div class="w-[51%] flex flex-col gap-4">
          <div class="bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
            <h3 class="text-[20px] font-bold text-slate-800 mb-3 flex items-center gap-2">
              <span class="w-7 h-7 rounded-lg bg-cyan-50 border border-cyan-200 text-cyan-700 flex items-center justify-center text-[14px] font-bold">2</span>
              产品定位
            </h3>
            <p class="text-[15px] text-slate-600 leading-relaxed mb-3">
              一句话概括：<span class="font-semibold text-slate-800">面向家庭做饭人群的智能烹饪助手</span>，覆盖「食材 → 推荐 → 分步引导 → 营养 → 库存 → 会员」全链路，
              把分散在多个 App 里的动作收敛到一条主路径上。
            </p>
            <p class="text-[15px] text-slate-600 leading-relaxed">
              更关键的一点是定位差异：本产品不把食品安全交给用户「自己注意」，而是由系统在<span class="font-semibold text-orange-600">检索与排序之间强制拦截</span>——
              这是它区别于普通菜谱类应用的核心。
            </p>
            <div class="flex gap-3 mt-4 flex-wrap">
              <span class="px-4 py-1.5 bg-cyan-50 border border-cyan-200 text-cyan-800 rounded-full text-[13px]">家庭做饭人群</span>
              <span class="px-4 py-1.5 bg-cyan-50 border border-cyan-200 text-cyan-800 rounded-full text-[13px]">有过敏成员的家庭</span>
              <span class="px-4 py-1.5 bg-cyan-50 border border-cyan-200 text-cyan-800 rounded-full text-[13px]">厨房新手</span>
              <span class="px-4 py-1.5 bg-cyan-50 border border-cyan-200 text-cyan-800 rounded-full text-[13px]">控糖 / 健身人群</span>
            </div>
          </div>

          <div class="bg-white border border-slate-200 rounded-xl p-6 shadow-sm flex-1">
            <h3 class="text-[20px] font-bold text-slate-800 mb-3 flex items-center gap-2">
              <span class="w-7 h-7 rounded-lg bg-indigo-50 border border-indigo-200 text-indigo-600 flex items-center justify-center text-[14px] font-bold">3</span>
              核心形态与技术主张
            </h3>
            <div class="space-y-3">
              <div class="flex items-start gap-3">
                <span class="w-2 h-2 rounded-full bg-cyan-700 mt-2 flex-shrink-0"></span>
                <p class="text-[15px] text-slate-600 leading-relaxed"><span class="font-semibold text-slate-800">多智能体编排：</span>用 LangGraph 把意图识别、推荐、烹饪引导、营养、库存、创新菜等能力组织成一张可观测、可扩展的图，而不是一堆互相调用的函数。</p>
              </div>
              <div class="flex items-start gap-3">
                <span class="w-2 h-2 rounded-full bg-orange-600 mt-2 flex-shrink-0"></span>
                <p class="text-[15px] text-slate-600 leading-relaxed"><span class="font-semibold text-slate-800">风控独立且不调大模型：</span>食品安全引擎是纯规则实现，确定性、可审计、毫秒级响应，且从结构上没有 Prompt 注入面。</p>
              </div>
              <div class="flex items-start gap-3">
                <span class="w-2 h-2 rounded-full bg-indigo-600 mt-2 flex-shrink-0"></span>
                <p class="text-[15px] text-slate-600 leading-relaxed"><span class="font-semibold text-slate-800">推荐全程无 LLM：</span>推荐主路径由「三路召回 + 布尔硬过滤 + 多因子加权」构成，结果可解释、可复现、可测试。</p>
              </div>
              <div class="flex items-start gap-3">
                <span class="w-2 h-2 rounded-full bg-emerald-600 mt-2 flex-shrink-0"></span>
                <p class="text-[15px] text-slate-600 leading-relaxed"><span class="font-semibold text-slate-800">三端同源：</span>Web 演示端、微信小程序、管理后台共享同一套接口与业务逻辑，逻辑层沉淀在共享包中复用。</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="mt-5 flex items-center justify-between text-[13px] text-slate-400">
        <span class="font-mono tracking-wider">AI 厨娘 · 智能烹饪助手 · 项目答辩</span>
        <span class="font-mono">04 / 25</span>
      </div>
    </div>
  </div>
`);
