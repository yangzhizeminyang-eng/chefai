window.slideDataMap.set(8, `
  <div class="w-[1440px] h-[810px] relative overflow-hidden slide-bg">
    <div class="absolute top-0 left-0 w-full h-[8px] bg-cyan-700"></div>
    <div class="w-[1350px] h-[720px] mx-auto my-[45px] relative pt-4 flex flex-col">

      <div class="flex items-center gap-4 mb-6">
        <div class="w-[6px] h-11 bg-cyan-700 rounded"></div>
        <div>
          <h2 class="text-[38px] font-bold text-slate-900 leading-tight">技术栈选型</h2>
          <p class="text-[15px] text-slate-500 mt-1">一个核心服务 + 三类技术支撑 · 外部 AI 能力全部 Provider 化，可 mock 与真实一键切换</p>
        </div>
      </div>

      <div class="grid grid-cols-4 gap-5 mb-5">
        <div class="bg-white border border-slate-200 border-t-[5px] border-t-cyan-700 rounded-xl p-5 shadow-sm">
          <h3 class="text-[19px] font-bold text-slate-800 mb-3">前端 · 三端同源</h3>
          <div class="space-y-2.5">
            <p class="text-[14px] text-slate-600 leading-relaxed"><span class="font-semibold text-slate-800">Web / 后台：</span>Vue 3 + Vite + TypeScript + Pinia + Element Plus</p>
            <p class="text-[14px] text-slate-600 leading-relaxed"><span class="font-semibold text-slate-800">小程序：</span>uni-app + Vue 3 + Pinia，六个分包组织 42 页</p>
            <p class="text-[14px] text-slate-600 leading-relaxed"><span class="font-semibold text-slate-800">共享层：</span>packages/shared 沉淀请求、状态与业务逻辑</p>
          </div>
          <p class="text-[13px] text-slate-400 mt-3 pt-3 border-t border-slate-100 leading-relaxed">选型理由：一套 Vue 心智模型覆盖三端，降低多端维护成本</p>
        </div>

        <div class="bg-white border border-slate-200 border-t-[5px] border-t-indigo-600 rounded-xl p-5 shadow-sm">
          <h3 class="text-[19px] font-bold text-slate-800 mb-3">后端 · 单体服务</h3>
          <div class="space-y-2.5">
            <p class="text-[14px] text-slate-600 leading-relaxed"><span class="font-semibold text-slate-800">框架：</span>Python 3.11 + FastAPI（异步、自动 OpenAPI 文档）</p>
            <p class="text-[14px] text-slate-600 leading-relaxed"><span class="font-semibold text-slate-800">数据访问：</span>SQLAlchemy 2.0 + Pydantic v2 校验</p>
            <p class="text-[14px] text-slate-600 leading-relaxed"><span class="font-semibold text-slate-800">规模：</span>118 个 py 模块、121 个端点、46 个测试文件</p>
          </div>
          <p class="text-[13px] text-slate-400 mt-3 pt-3 border-t border-slate-100 leading-relaxed">选型理由：Pydantic 让接口契约与文档同源，前端联调成本大幅下降</p>
        </div>

        <div class="bg-white border border-slate-200 border-t-[5px] border-t-emerald-600 rounded-xl p-5 shadow-sm">
          <h3 class="text-[19px] font-bold text-slate-800 mb-3">数据 · 单库起步</h3>
          <div class="space-y-2.5">
            <p class="text-[14px] text-slate-600 leading-relaxed"><span class="font-semibold text-slate-800">主库：</span>PostgreSQL 16，单库 aicook，28–32 张表</p>
            <p class="text-[14px] text-slate-600 leading-relaxed"><span class="font-semibold text-slate-800">向量：</span>pgvector 扩展，与业务数据同库事务一致</p>
            <p class="text-[14px] text-slate-600 leading-relaxed"><span class="font-semibold text-slate-800">缓存：</span>Redis 7 已部署并预留，阶段二接入</p>
          </div>
          <p class="text-[13px] text-slate-400 mt-3 pt-3 border-t border-slate-100 leading-relaxed">选型理由：阶段一不引入额外中间件，规模化后再迁 Milvus</p>
        </div>

        <div class="bg-white border border-slate-200 border-t-[5px] border-t-orange-600 rounded-xl p-5 shadow-sm">
          <h3 class="text-[19px] font-bold text-slate-800 mb-3">AI 能力 · 全部可换</h3>
          <div class="space-y-2.5">
            <p class="text-[14px] text-slate-600 leading-relaxed"><span class="font-semibold text-slate-800">意图识别：</span>LLM（全图唯一 LLM 节点）</p>
            <p class="text-[14px] text-slate-600 leading-relaxed"><span class="font-semibold text-slate-800">拍照识别：</span>VLM Provider，真实模型与 mock 可切</p>
            <p class="text-[14px] text-slate-600 leading-relaxed"><span class="font-semibold text-slate-800">语音：</span>ASR / TTS（qwen3-asr-flash / qwen3-tts-flash）</p>
            <p class="text-[14px] text-slate-600 leading-relaxed"><span class="font-semibold text-slate-800">嵌入：</span>当前为哈希伪向量，可切语义模型</p>
          </div>
          <p class="text-[13px] text-slate-400 mt-3 pt-3 border-t border-slate-100 leading-relaxed">选型理由：Provider 抽象让 AI 能力可替换、可降级、可测试</p>
        </div>
      </div>

      <div class="bg-white border border-slate-200 rounded-xl p-6 shadow-sm flex-1">
        <h3 class="text-[19px] font-bold text-slate-800 mb-4">部署与运行方式</h3>
        <div class="grid grid-cols-4 gap-5">
          <div>
            <p class="text-[15px] font-semibold text-slate-800 mb-1.5">容器编排</p>
            <p class="text-[14px] text-slate-600 leading-relaxed">Docker Compose 单机四服务；<span class="font-mono text-[13px]">api / db / redis</span> 端口不对外发布，仅 nginx 暴露 8005，减少攻击面。</p>
          </div>
          <div>
            <p class="text-[15px] font-semibold text-slate-800 mb-1.5">构建策略</p>
            <p class="text-[14px] text-slate-600 leading-relaxed">前端镜像峰值内存超 1.5GB，采用「本地构建 → save → scp → load」，规避 2C2G 服务器 OOM。</p>
          </div>
          <div>
            <p class="text-[15px] font-semibold text-slate-800 mb-1.5">资源守卫</p>
            <p class="text-[14px] text-slate-600 leading-relaxed">Compose 设定保守上限：web 192M、api 768M、db 512M、redis 128M，防止单服务拖垮整机。</p>
          </div>
          <div>
            <p class="text-[15px] font-semibold text-slate-800 mb-1.5">部署脚本</p>
            <p class="text-[14px] text-slate-600 leading-relaxed">deploy.sh 固化 8 个步骤，含语料硬校验、占位符拒绝、端口断言与健康检查轮询，可重复执行。</p>
          </div>
        </div>
      </div>

      <div class="mt-4 flex items-center justify-between text-[13px] text-slate-400">
        <span class="font-mono tracking-wider">AI 厨娘 · 智能烹饪助手 · 项目答辩</span>
        <span class="font-mono">08 / 25</span>
      </div>
    </div>
  </div>
`);
