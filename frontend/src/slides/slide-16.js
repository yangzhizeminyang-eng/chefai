window.slideDataMap.set(16, `
  <div class="w-[1440px] h-[810px] relative overflow-hidden slide-bg">
    <div class="absolute top-0 left-0 w-full h-[8px] bg-rose-600"></div>
    <div class="w-[1350px] h-[720px] mx-auto my-[45px] relative flex flex-col">

      <div class="flex items-center justify-between mb-2">
        <div class="flex items-center gap-4">
          <div class="w-[6px] h-[42px] bg-rose-600 rounded"></div>
          <div>
            <h2 class="text-[36px] font-bold text-slate-900 leading-tight">重点模块② 食品安全与过敏原风控</h2>
            <p class="text-[15px] text-slate-500 mt-1">安全底线 · 零容忍 · 27 条规则 · 纯规则引擎不调用大模型</p>
          </div>
        </div>
        <div class="flex gap-2.5">
          <span class="px-4 py-2 bg-rose-50 border border-rose-200 text-rose-700 rounded-full text-[13px] font-medium">12 条安全红线全绿</span>
          <span class="px-4 py-2 bg-slate-50 border border-slate-200 text-slate-600 rounded-full text-[13px] font-medium">模块完成度 97%</span>
        </div>
      </div>

      <div class="flex gap-6 flex-1">
        <div class="w-[46%] bg-white border border-slate-200 rounded-xl p-3.5 shadow-sm flex flex-col">
          <h3 class="text-[18px] font-bold text-slate-800 mb-1">四条设计铁律</h3>
          <p class="text-[13px] text-slate-500 mb-4">风控的可靠性不来自规则数量，而来自这四条不可妥协的结构约束</p>
          <div class="space-y-2 flex-1">
            <div class="bg-rose-50 border border-rose-200 rounded-lg p-3">
              <p class="text-[15px] font-bold text-rose-700 mb-1.5">① 不调用大模型</p>
              <p class="text-[13px] text-rose-800/90 leading-relaxed">纯规则实现意味着确定性、可审计、毫秒级响应、零 token 成本，而且<span class="font-semibold">不存在 Prompt 注入的攻击面</span>。安全判定不能是概率问题。</p>
            </div>
            <div class="bg-slate-50 border border-slate-200 rounded-lg p-3">
              <p class="text-[15px] font-bold text-slate-800 mb-1.5">② 一票否决 = 控制流短路</p>
              <p class="text-[13px] text-slate-600 leading-relaxed">命中即经条件边直达终止节点，<span class="font-semibold">不是「打个标记然后丢掉结果」</span>。区别在于：短路状态下业务节点根本不执行，也不产生任何业务字段。</p>
            </div>
            <div class="bg-slate-50 border border-slate-200 rounded-lg p-3">
              <p class="text-[15px] font-bold text-slate-800 mb-1.5">③ 双重风控不可省</p>
              <p class="text-[13px] text-slate-600 leading-relaxed">输入侧拦截用户提问，输出侧拦截模型生成内容。两个闸门面对的风险不同：前者是「不该问的」，后者是「不该说的」，任何一个都不能替代另一个。</p>
            </div>
            <div class="bg-amber-50 border border-amber-200 rounded-lg p-3">
              <p class="text-[15px] font-bold text-amber-700 mb-1.5">④ 降级保守，绝不冒险</p>
              <p class="text-[13px] text-amber-800/90 leading-relaxed">风控引擎异常或超时，一律进入保守模式并返回安全话术，<span class="font-semibold">绝不因为「风控挂了」就直接把请求透传给模型</span>。可用性让位于安全性。</p>
            </div>
          </div>
        </div>

        <div class="w-[54%] flex flex-col gap-2.5">
          <div class="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
            <h3 class="text-[18px] font-bold text-slate-800 mb-3">过敏原处理的架构位置 —— 这是全项目最关键的一处设计</h3>
            <div class="flex items-center gap-3 mb-3">
              <span class="px-3.5 py-2 bg-sky-50 border border-sky-300 text-sky-800 rounded-lg text-[13px] font-medium">检索召回</span>
              <span class="text-slate-400">→</span>
              <span class="px-3.5 py-2 bg-rose-600 text-white rounded-lg text-[13px] font-bold shadow-sm">独立布尔过滤节点</span>
              <span class="text-slate-400">→</span>
              <span class="px-3.5 py-2 bg-indigo-50 border border-indigo-300 text-indigo-800 rounded-lg text-[13px] font-medium">加权排序</span>
            </div>
            <div class="space-y-2">
              <p class="text-[13px] text-slate-600 leading-relaxed">过敏原<span class="font-semibold text-rose-600">不是降权项，而是布尔硬过滤</span>，独立夹在检索与排序之间，最终落到数据库的 WHERE 条件上。</p>
              <p class="text-[13px] text-slate-600 leading-relaxed">更关键的是调用关系：排序函数的输入集<span class="font-semibold text-slate-800">只能</span>是过滤节点的输出集。这意味着即便后续有人想改动逻辑，也无法让一道含过敏原的菜谱进入打分环节 —— 代码结构本身杜绝了这种可能。</p>
              <p class="text-[13px] text-slate-600 leading-relaxed">与之对照，口味上的 <span class="font-mono text-[12px]">dislike</span> 采用<span class="font-semibold">降权（−0.5）</span>而非过滤：用户不喜欢不等于不能吃，两者语义刻意区分开。</p>
            </div>
          </div>

          <div class="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
            <h3 class="text-[18px] font-bold text-slate-800 mb-2">拦截链路 · 四步闭环</h3>
            <div class="grid grid-cols-4 gap-3">
              <div class="bg-slate-50 border border-slate-200 rounded-lg px-3 py-3">
                <p class="text-[13px] font-bold text-slate-700 mb-1">① 规则命中</p>
                <p class="text-[12px] text-slate-500 leading-relaxed">输入或输出文本匹配规则库，记录规则 ID 与版本</p>
              </div>
              <div class="bg-slate-50 border border-slate-200 rounded-lg px-3 py-3">
                <p class="text-[13px] font-bold text-slate-700 mb-1">② 控制流短路</p>
                <p class="text-[12px] text-slate-500 leading-relaxed">条件边直达终止节点，跳过全部业务逻辑</p>
              </div>
              <div class="bg-slate-50 border border-slate-200 rounded-lg px-3 py-3">
                <p class="text-[13px] font-bold text-slate-700 mb-1">③ 前端拦截页</p>
                <p class="text-[12px] text-slate-500 leading-relaxed">三段式呈现：风险说明 / 正确做法 / 就医引导</p>
              </div>
              <div class="bg-slate-50 border border-slate-200 rounded-lg px-3 py-3">
                <p class="text-[13px] font-bold text-slate-700 mb-1">④ 可追溯留证</p>
                <p class="text-[12px] text-slate-500 leading-relaxed">trace 记录规则依据，支持「我认为这是误判」上报</p>
              </div>
            </div>
          </div>

          <div class="bg-slate-900 rounded-xl p-5 flex-1">
            <div class="flex items-center gap-2 mb-2">
              <span class="w-2 h-2 rounded-full bg-emerald-400"></span>
              <p class="text-[14px] font-bold text-white">实测证据（全页面测试中真实触发）</p>
            </div>
            <p class="text-[13px] text-slate-300 leading-relaxed mb-3">
              在首页输入「发芽土豆能吃吗」并提交 —— 后端风控闸门命中规则 <span class="font-mono text-rose-300">FS-003</span>（发芽 / 变青土豆 · 龙葵素），
              控制流立即短路，前端跳转至风控拦截页。
            </p>
            <div class="bg-black/40 border border-slate-700 rounded-lg px-4 py-3">
              <p class="text-[12px] font-mono text-slate-400 leading-relaxed">命中规则：FS-003 ｜ 类别：食品安全高风险 ｜ 等级：high<br/>规则版本：FS-003@rules-v1.0 ｜ 返回体：不含任何业务字段<br/>页面标注：「本次请求未生成任何内容」</p>
            </div>
          </div>
        </div>
      </div>

      <div class="mt-4 flex items-center justify-between text-[13px] text-slate-400">
        <span class="font-mono tracking-wider">AI 厨娘 · 智能烹饪助手 · 项目答辩</span>
        <span class="font-mono">16 / 25</span>
      </div>
    </div>
  </div>
`);
