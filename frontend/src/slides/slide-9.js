window.slideDataMap.set(9, `
  <div class="w-[1440px] h-[810px] relative overflow-hidden slide-bg">
    <div class="absolute top-0 left-0 w-full h-[8px] bg-cyan-700"></div>
    <div class="w-[1350px] h-[720px] mx-auto my-[45px] relative pt-4 flex flex-col">

      <div class="flex items-center gap-4 mb-6">
        <div class="w-[6px] h-11 bg-cyan-700 rounded"></div>
        <div>
          <h2 class="text-[38px] font-bold text-slate-900 leading-tight">数据与语料资产</h2>
          <p class="text-[15px] text-slate-500 mt-1">推荐质量的地基不是模型，而是语料本身 —— 373 篇菜谱 + 371 张封面 + 27 条风控规则</p>
        </div>
      </div>

      <div class="flex gap-6 flex-1">
        <div class="w-[34%] flex flex-col gap-5">
          <div class="bg-white border border-slate-200 rounded-xl p-6 shadow-sm flex-1">
            <h3 class="text-[19px] font-bold text-slate-800 mb-3">菜谱语料库</h3>
            <div class="flex gap-4 mb-4">
              <div class="flex-1 bg-cyan-50 border border-cyan-200 rounded-lg px-4 py-3 text-center">
                <p class="text-[30px] font-bold text-cyan-700 font-mono leading-none mb-1">373</p>
                <p class="text-[13px] text-cyan-800">篇菜谱 md</p>
              </div>
              <div class="flex-1 bg-orange-50 border border-orange-200 rounded-lg px-4 py-3 text-center">
                <p class="text-[30px] font-bold text-orange-600 font-mono leading-none mb-1">371</p>
                <p class="text-[13px] text-orange-800">张封面图</p>
              </div>
            </div>
            <div class="space-y-2.5">
              <p class="text-[14px] text-slate-600 leading-relaxed"><span class="font-semibold text-slate-800">来源与授权：</span>HowToCook 开源菜谱集（Unlicense 公有领域，v1.6.0），版权风险可控。</p>
              <p class="text-[14px] text-slate-600 leading-relaxed"><span class="font-semibold text-slate-800">组织方式：</span>按 10 个分类目录存放，带图菜谱采用「同目录同名 .md + .jpg」约定，解析器递归扫描并剥离图片行。</p>
              <p class="text-[14px] text-slate-600 leading-relaxed"><span class="font-semibold text-slate-800">运维支持：</span>配套 7 个语料工具脚本，可批量迁移缺图、分发封面、规范化命名、校验结构。</p>
            </div>
          </div>

          <div class="bg-amber-50 border border-amber-200 rounded-xl p-5">
            <p class="text-[15px] font-bold text-amber-800 mb-2">⚠ 一条容易被误读的口径</p>
            <p class="text-[14px] text-amber-800 leading-relaxed">
              语料导入时<span class="font-semibold">不落库图片行</span>，封面字段默认留空——也就是说「补了图」不等于「产品里有图」，
              卡片上真正显示图片还需要独立的图片链路改造。这条口径在验收文档中单独标注，避免验收时产生分歧。
            </p>
          </div>
        </div>

        <div class="w-[36%] bg-white border border-slate-200 rounded-xl p-6 shadow-sm flex flex-col">
          <h3 class="text-[19px] font-bold text-slate-800 mb-1">风控规则库 · 27 条</h3>
          <p class="text-[13px] text-slate-500 mb-4">主库 24 条 + 创新菜专项 3 条</p>
          <div class="flex-1 space-y-2.5">
            <div class="flex items-center justify-between bg-slate-50 border-l-4 border-l-red-500 rounded-lg px-4 py-2.5">
              <div>
                <p class="text-[15px] font-semibold text-slate-800"><span class="font-mono text-red-600">FS-</span> 食品安全高风险</p>
                <p class="text-[12px] text-slate-500">发芽土豆、久泡木耳、未熟四季豆等</p>
              </div>
              <span class="text-[16px] font-bold text-red-600 font-mono">11</span>
            </div>
            <div class="flex items-center justify-between bg-slate-50 border-l-4 border-l-orange-500 rounded-lg px-4 py-2.5">
              <div>
                <p class="text-[15px] font-semibold text-slate-800"><span class="font-mono text-orange-600">MR-</span> 医疗拒答</p>
                <p class="text-[12px] text-slate-500">诊断、治疗类诉求一律拒答</p>
              </div>
              <span class="text-[16px] font-bold text-orange-600 font-mono">4</span>
            </div>
            <div class="flex items-center justify-between bg-slate-50 border-l-4 border-l-indigo-500 rounded-lg px-4 py-2.5">
              <div>
                <p class="text-[15px] font-semibold text-slate-800"><span class="font-mono text-indigo-600">OB-</span> 输出禁用表述</p>
                <p class="text-[12px] text-slate-500">绝对化用语、安全承诺、违禁词</p>
              </div>
              <span class="text-[16px] font-bold text-indigo-600 font-mono">5</span>
            </div>
            <div class="flex items-center justify-between bg-slate-50 border-l-4 border-l-amber-500 rounded-lg px-4 py-2.5">
              <div>
                <p class="text-[15px] font-semibold text-slate-800"><span class="font-mono text-amber-600">SP-</span> 特殊人群</p>
                <p class="text-[12px] text-slate-500">孕产妇、婴幼儿等敏感人群提示</p>
              </div>
              <span class="text-[16px] font-bold text-amber-600 font-mono">2</span>
            </div>
            <div class="flex items-center justify-between bg-slate-50 border-l-4 border-l-teal-500 rounded-lg px-4 py-2.5">
              <div>
                <p class="text-[15px] font-semibold text-slate-800"><span class="font-mono text-teal-600">PS-</span> 伪科学 / 食物相克</p>
                <p class="text-[12px] text-slate-500">仅提示不阻断，避免误伤正常提问</p>
              </div>
              <span class="text-[16px] font-bold text-teal-600 font-mono">2</span>
            </div>
            <div class="flex items-center justify-between bg-cyan-50 border-l-4 border-l-cyan-600 rounded-lg px-4 py-2.5">
              <div>
                <p class="text-[15px] font-semibold text-slate-800"><span class="font-mono text-cyan-700">INNO-</span> 创新菜专项</p>
                <p class="text-[12px] text-slate-500">医疗 / 输出禁用 / 伪科学，输入输出双侧</p>
              </div>
              <span class="text-[16px] font-bold text-cyan-700 font-mono">3</span>
            </div>
          </div>
        </div>

        <div class="w-[30%] flex flex-col gap-5">
          <div class="bg-white border border-slate-200 rounded-xl p-6 shadow-sm flex-1">
            <h3 class="text-[19px] font-bold text-slate-800 mb-3">合规待办与红线</h3>
            <div class="space-y-3">
              <div class="flex gap-3">
                <span class="w-1.5 rounded bg-orange-500 mt-1 flex-shrink-0"></span>
                <p class="text-[14px] text-slate-600 leading-relaxed"><span class="font-semibold text-slate-800">语料文本清洗：</span>上游语料部分描述带功效与医疗宣称表述，需按 RL-7 / RL-11 做专项清洗后才能上架。</p>
              </div>
              <div class="flex gap-3">
                <span class="w-1.5 rounded bg-orange-500 mt-1 flex-shrink-0"></span>
                <p class="text-[14px] text-slate-600 leading-relaxed"><span class="font-semibold text-slate-800">备案类资质：</span>生成式 AI 备案、小程序备案、类目资质、虚拟支付签约均未启动，是全项目唯一外部不可压缩的关键路径。</p>
              </div>
              <div class="flex gap-3">
                <span class="w-1.5 rounded bg-emerald-500 mt-1 flex-shrink-0"></span>
                <p class="text-[14px] text-slate-600 leading-relaxed"><span class="font-semibold text-slate-800">已提前落地：</span>RL-14 敏感个人信息单独同意已完成，准入与免责声明在首屏强制拦截。</p>
              </div>
            </div>
          </div>

          <div class="bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
            <h3 class="text-[17px] font-bold text-slate-800 mb-3">阶段豁免说明</h3>
            <p class="text-[14px] text-slate-600 leading-relaxed">
              阶段一产物不对外提供服务，因此备案与专家签字在合同层面豁免；但阶段二小程序必须全部补齐，
              且备案周期不受开发进度影响 —— 这也是我们在阶段一收尾时就把资质办理清单列入 P0 的原因。
            </p>
          </div>
        </div>
      </div>

      <div class="mt-4 flex items-center justify-between text-[13px] text-slate-400">
        <span class="font-mono tracking-wider">AI 厨娘 · 智能烹饪助手 · 项目答辩</span>
        <span class="font-mono">09 / 25</span>
      </div>
    </div>
  </div>
`);
