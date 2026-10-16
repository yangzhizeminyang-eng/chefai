window.slideDataMap.set(22, `
  <div class="w-[1440px] h-[810px] relative overflow-hidden slide-bg">
    <div class="absolute top-0 left-0 w-full h-[8px] bg-indigo-600"></div>
    <div class="w-[1350px] h-[720px] mx-auto my-[45px] relative pt-4 flex flex-col">

      <div class="flex items-center gap-4 mb-5">
        <div class="w-[6px] h-[42px] bg-indigo-600 rounded"></div>
        <div>
          <h2 class="text-[36px] font-bold text-slate-900 leading-tight">关键问题深剖</h2>
          <p class="text-[15px] text-slate-500 mt-1">四个从现象追到根因的案例，按「现象 → 根因 → 解法 → 结论」四段式展开</p>
        </div>
      </div>

      <div class="grid grid-cols-2 gap-5 flex-1">
        <div class="bg-white border border-slate-200 rounded-xl p-5 shadow-sm flex flex-col">
          <div class="flex items-center gap-3 mb-3">
            <span class="w-8 h-8 rounded-lg bg-cyan-700 text-white flex items-center justify-center text-[14px] font-bold font-mono">01</span>
            <div>
              <h3 class="text-[18px] font-bold text-slate-800">检索召回只用到一半</h3>
              <p class="text-[12px] text-slate-400 font-mono">RAG 链路 · 算法层</p>
            </div>
            <span class="ml-auto px-3 py-1 bg-emerald-50 border border-emerald-200 text-emerald-700 rounded-full text-[12px]">已闭环</span>
          </div>
          <div class="space-y-2 flex-1">
            <p class="text-[13px] text-slate-600 leading-relaxed"><span class="font-semibold text-slate-800">现象：</span>用户手工勾选三样食材后，推荐结果明显少于预期，且完全不像「语义相近」的菜。</p>
            <p class="text-[13px] text-slate-600 leading-relaxed"><span class="font-semibold text-slate-800">根因：</span>向量召回分支的触发条件写成了 <span class="font-mono text-[12px] text-rose-600">if use_vector and query_text</span>，而纯手选路径不产生文本，条件恒为假。</p>
            <p class="text-[13px] text-slate-600 leading-relaxed"><span class="font-semibold text-slate-800">解法：</span>逐项核查三路召回生效条件并补齐缺口，同时修复向量升级遗留的三个工程缺口（构建命令、环境变量、嵌入空间版本迁移）。</p>
            <p class="text-[13px] text-slate-600 leading-relaxed"><span class="font-semibold text-slate-800">结论：</span>三缺口已闭环并双文档留痕；剩余限制（伪向量非语义）明确登记为改进项，不掩盖。</p>
          </div>
        </div>

        <div class="bg-white border border-slate-200 rounded-xl p-5 shadow-sm flex flex-col">
          <div class="flex items-center gap-3 mb-3">
            <span class="w-8 h-8 rounded-lg bg-orange-600 text-white flex items-center justify-center text-[14px] font-bold font-mono">02</span>
            <div>
              <h3 class="text-[18px] font-bold text-slate-800">2C2G 上构建必然 OOM</h3>
              <p class="text-[12px] text-slate-400 font-mono">部署链路 · 资源约束</p>
            </div>
            <span class="ml-auto px-3 py-1 bg-emerald-50 border border-emerald-200 text-emerald-700 rounded-full text-[12px]">已闭环</span>
          </div>
          <div class="space-y-2 flex-1">
            <p class="text-[13px] text-slate-600 leading-relaxed"><span class="font-semibold text-slate-800">现象：</span>在服务器上执行前端镜像构建，进程被系统杀死，构建无法完成。</p>
            <p class="text-[13px] text-slate-600 leading-relaxed"><span class="font-semibold text-slate-800">根因：</span>前端 Dockerfile 需要两次依赖安装加一次类型检查，峰值内存超过 1.5GB，而目标机器只有 2GB 内存。</p>
            <p class="text-[13px] text-slate-600 leading-relaxed"><span class="font-semibold text-slate-800">解法：</span>改为「构建与运行分离」—— 本地完成构建后 save 成 tar，scp 传到服务器再 load，服务器只负责运行镜像。</p>
            <p class="text-[13px] text-slate-600 leading-relaxed"><span class="font-semibold text-slate-800">结论：</span>该策略已固化进部署脚本，换机器也能一次跑通；同时给 Compose 加上保守内存上限，避免运行期互相拖垮。</p>
          </div>
        </div>

        <div class="bg-white border border-slate-200 rounded-xl p-5 shadow-sm flex flex-col">
          <div class="flex items-center gap-3 mb-3">
            <span class="w-8 h-8 rounded-lg bg-sky-600 text-white flex items-center justify-center text-[14px] font-bold font-mono">03</span>
            <div>
              <h3 class="text-[18px] font-bold text-slate-800">镜像加速源「配了但不生效」</h3>
              <p class="text-[12px] text-slate-400 font-mono">基础设施 · 镜像拉取</p>
            </div>
            <span class="ml-auto px-3 py-1 bg-emerald-50 border border-emerald-200 text-emerald-700 rounded-full text-[12px]">已闭环</span>
          </div>
          <div class="space-y-2 flex-1">
            <p class="text-[13px] text-slate-600 leading-relaxed"><span class="font-semibold text-slate-800">现象：</span>daemon.json 已配置镜像加速地址，拉取部分镜像仍然超时失败。</p>
            <p class="text-[13px] text-slate-600 leading-relaxed"><span class="font-semibold text-slate-800">根因：</span>加速源只对「不带 registry 前缀」的官方镜像名生效；一旦镜像名写死为某个具体 registry 域名，Docker 会直连该域名，绕过加速配置。</p>
            <p class="text-[13px] text-slate-600 leading-relaxed"><span class="font-semibold text-slate-800">解法：</span>先经加速源拉取官方镜像，再用 docker tag 打上带前缀的别名，让构建脚本引用的名字与本地已有镜像对齐。</p>
            <p class="text-[13px] text-slate-600 leading-relaxed"><span class="font-semibold text-slate-800">结论：</span>该处理已写进部署脚本第 1 步，属于「准备基础镜像」的一部分，后续部署不再卡在这一环。</p>
          </div>
        </div>

        <div class="bg-white border border-slate-200 border-l-4 border-l-amber-500 rounded-xl p-5 shadow-sm flex flex-col">
          <div class="flex items-center gap-3 mb-3">
            <span class="w-8 h-8 rounded-lg bg-amber-500 text-white flex items-center justify-center text-[14px] font-bold font-mono">04</span>
            <div>
              <h3 class="text-[18px] font-bold text-slate-800">语音输入静默失效</h3>
              <p class="text-[12px] text-slate-400 font-mono">浏览器安全模型 · 待办</p>
            </div>
            <span class="ml-auto px-3 py-1 bg-amber-50 border border-amber-200 text-amber-700 rounded-full text-[12px]">已登记 R-31</span>
          </div>
          <div class="space-y-2 flex-1">
            <p class="text-[13px] text-slate-600 leading-relaxed"><span class="font-semibold text-slate-800">现象：</span>功能代码与接口全部就绪，但在公网 IP + http 环境下点击录音没有任何反应，控制台也不报错。</p>
            <p class="text-[13px] text-slate-600 leading-relaxed"><span class="font-semibold text-slate-800">根因：</span>麦克风采集 API 只在安全上下文（HTTPS 或 localhost）可用；http 页面下浏览器直接禁用权限，属于规范行为而非程序缺陷。</p>
            <p class="text-[13px] text-slate-600 leading-relaxed"><span class="font-semibold text-slate-800">解法：</span>短期用自签证书内网验证；正式环境必须上 HTTPS 域名 —— 小程序体验版与正式版也强制要求 HTTPS。</p>
            <p class="text-[13px] text-slate-600 leading-relaxed"><span class="font-semibold text-slate-800">结论：</span>作为已知风险登记 R-31 并给出触发条件；值得注意的是纯 TTS 播报走音频元素不受影响，因此功能是「部分可用」而非「全不可用」。</p>
          </div>
        </div>
      </div>

      <div class="mt-4 flex items-center justify-between text-[13px] text-slate-400">
        <span class="font-mono tracking-wider">AI 厨娘 · 智能烹饪助手 · 项目答辩</span>
        <span class="font-mono">22 / 25</span>
      </div>
    </div>
  </div>
`);
