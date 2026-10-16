window.slideDataMap.set(14, `
  <div class="w-[1440px] h-[810px] relative overflow-hidden slide-bg">
    <div class="absolute top-0 left-0 w-full h-[8px] bg-cyan-700"></div>
    <div class="w-[1350px] h-[720px] mx-auto my-[45px] relative pt-4 flex flex-col">

      <div class="flex items-center justify-between mb-5">
        <div class="flex items-center gap-4">
          <div class="w-[6px] h-[42px] bg-cyan-700 rounded"></div>
          <div>
            <h2 class="text-[36px] font-bold text-slate-900 leading-tight">其余核心能力速览</h2>
            <p class="text-[15px] text-slate-500 mt-1">除推荐、风控、编排三条主线外，另有六项能力同样进入阶段一交付范围</p>
          </div>
        </div>
        <span class="px-4 py-2 bg-slate-50 border border-slate-200 text-slate-600 rounded-full text-[13px] font-medium">15 个模块中 12 个完成度 ≥ 90%</span>
      </div>

      <div class="grid grid-cols-3 gap-5 flex-1">
        <div class="bg-white border border-slate-200 rounded-xl p-5 shadow-sm flex flex-col">
          <div class="flex items-center gap-2.5 mb-3">
            <span class="w-8 h-8 rounded-lg bg-cyan-50 border border-cyan-200 text-cyan-700 flex items-center justify-center text-[13px] font-bold font-mono">F</span>
            <h3 class="text-[18px] font-bold text-slate-800">分步烹饪引导</h3>
          </div>
          <p class="text-[13px] text-slate-600 leading-relaxed mb-3">把菜谱转成厨房里真正能照着做的操作流：大字单步显示、进度条、上一步/下一步本地即时切换、并行计时器（5 个预设计时 + 自定义）。</p>
          <div class="space-y-1.5 mt-auto">
            <p class="text-[12px] text-slate-500"><span class="text-cyan-700 font-semibold">5 态状态机：</span>未开始 → 进行中 → 评分 → 完成，仅进行中可放弃</p>
            <p class="text-[12px] text-slate-500"><span class="text-cyan-700 font-semibold">过敏原前置检查：</span>创建会话即检出冲突，须用户确认才能开工</p>
            <p class="text-[12px] text-slate-500"><span class="text-cyan-700 font-semibold">求助限 3 次/会话：</span>防滥用，退出需二次确认</p>
          </div>
        </div>

        <div class="bg-white border border-slate-200 rounded-xl p-5 shadow-sm flex flex-col">
          <div class="flex items-center gap-2.5 mb-3">
            <span class="w-8 h-8 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-700 flex items-center justify-center text-[13px] font-bold font-mono">G</span>
            <h3 class="text-[18px] font-bold text-slate-800">营养分析</h3>
          </div>
          <p class="text-[13px] text-slate-600 leading-relaxed mb-3">单菜谱营养按「每份」口径给出，支持份数缩放重算；另有按日、按餐的汇总接口，为控糖与健身人群提供可累积的饮食数据。</p>
          <div class="space-y-1.5 mt-auto">
            <p class="text-[12px] text-slate-500"><span class="text-emerald-700 font-semibold">缺失不按 0 计：</span>数据缺失如实标注「未纳入统计」，分母同步排除</p>
            <p class="text-[12px] text-slate-500"><span class="text-emerald-700 font-semibold">手动补录先过闸门：</span>描述文本先经风控校验再落库</p>
            <p class="text-[12px] text-slate-500"><span class="text-emerald-700 font-semibold">避免误导性结论：</span>不给出法定营养声称类表述</p>
          </div>
        </div>

        <div class="bg-white border border-slate-200 rounded-xl p-5 shadow-sm flex flex-col">
          <div class="flex items-center gap-2.5 mb-3">
            <span class="w-8 h-8 rounded-lg bg-sky-50 border border-sky-200 text-sky-700 flex items-center justify-center text-[13px] font-bold font-mono">H</span>
            <h3 class="text-[18px] font-bold text-slate-800">库存与购物清单</h3>
          </div>
          <p class="text-[13px] text-slate-600 leading-relaxed mb-3">维护家庭在库食材，按临期天数优先排序；临期数据会回流到推荐排序的 expiring 因子，形成「快过期先吃掉」的正向循环。</p>
          <div class="space-y-1.5 mt-auto">
            <p class="text-[12px] text-slate-500"><span class="text-sky-700 font-semibold">扣减两段式：</span>先出建议、再确认生效，防误扣</p>
            <p class="text-[12px] text-slate-500"><span class="text-sky-700 font-semibold">留痕设计：</span>确认扣减时写入变更记录，可回溯</p>
            <p class="text-[12px] text-slate-500"><span class="text-sky-700 font-semibold">与购物清单联动：</span>缺料自动汇总为采购项</p>
          </div>
        </div>

        <div class="bg-white border border-slate-200 rounded-xl p-5 shadow-sm flex flex-col">
          <div class="flex items-center gap-2.5 mb-3">
            <span class="w-8 h-8 rounded-lg bg-orange-50 border border-orange-200 text-orange-700 flex items-center justify-center text-[13px] font-bold font-mono">J</span>
            <h3 class="text-[18px] font-bold text-slate-800">会员与支付</h3>
          </div>
          <p class="text-[13px] text-slate-600 leading-relaxed mb-3">六项会员权益口径已对齐；支付回调做了幂等处理，重复请求不会重复入账。识别额度按免费 3 次/日、会员 10 次/日区分。</p>
          <div class="space-y-1.5 mt-auto">
            <p class="text-[12px] text-slate-500"><span class="text-orange-700 font-semibold">平台支付抽象层已建：</span>接真实支付只需实现适配器</p>
            <p class="text-[12px] text-slate-500"><span class="font-semibold text-rose-600">红线：</span>虚拟支付必须走小程序虚拟支付，禁止跨端引流</p>
            <p class="text-[12px] text-slate-500"><span class="font-semibold text-rose-600">红线：</span>iOS 未签约时完全隐藏购买入口</p>
          </div>
        </div>

        <div class="bg-white border border-slate-200 rounded-xl p-5 shadow-sm flex flex-col">
          <div class="flex items-center gap-2.5 mb-3">
            <span class="w-8 h-8 rounded-lg bg-indigo-50 border border-indigo-200 text-indigo-700 flex items-center justify-center text-[13px] font-bold font-mono">C</span>
            <h3 class="text-[18px] font-bold text-slate-800">用户档案与合规同意</h3>
          </div>
          <p class="text-[13px] text-slate-600 leading-relaxed mb-3">家庭成员、过敏原、厨艺与设备、饮食目标在同一页承载。档案不是普通设置页 —— 它直接驱动推荐硬过滤的四个维度。</p>
          <div class="space-y-1.5 mt-auto">
            <p class="text-[12px] text-slate-500"><span class="text-indigo-700 font-semibold">过敏原为必填：</span>缺失档案会直接放大食品安全风险</p>
            <p class="text-[12px] text-slate-500"><span class="text-indigo-700 font-semibold">设备白名单校验：</span>避免出现无法执行的菜谱</p>
            <p class="text-[12px] text-slate-500"><span class="text-indigo-700 font-semibold">PIPL 单独同意：</span>RL-14 提前落地并落库留证</p>
          </div>
        </div>

        <div class="bg-white border border-slate-200 rounded-xl p-5 shadow-sm flex flex-col">
          <div class="flex items-center gap-2.5 mb-3">
            <span class="w-8 h-8 rounded-lg bg-teal-50 border border-teal-200 text-teal-700 flex items-center justify-center text-[13px] font-bold font-mono">♪</span>
            <h3 class="text-[18px] font-bold text-slate-800">语音交互能力</h3>
          </div>
          <p class="text-[13px] text-slate-600 leading-relaxed mb-3">做菜的双手是湿的、眼睛在看锅，语音是最自然的输入方式。已支持语音转文字、文字转语音、流式边合成边播，以及语音指令意图识别。</p>
          <div class="space-y-1.5 mt-auto">
            <p class="text-[12px] text-slate-500"><span class="text-teal-700 font-semibold">工程特点：</span>全走 HTTP 外部服务，无新增依赖、不落盘</p>
            <p class="text-[12px] text-slate-500"><span class="text-teal-700 font-semibold">配置项均有默认值：</span>缺省回退 mock，不影响启动</p>
            <p class="text-[12px] text-slate-500"><span class="font-semibold text-rose-600">硬约束：</span>语音输入依赖 HTTPS，http 下麦克风静默失效</p>
          </div>
        </div>
      </div>

      <div class="mt-4 flex items-center justify-between text-[13px] text-slate-400">
        <span class="font-mono tracking-wider">AI 厨娘 · 智能烹饪助手 · 项目答辩</span>
        <span class="font-mono">14 / 24</span>
      </div>
    </div>
  </div>
`);
