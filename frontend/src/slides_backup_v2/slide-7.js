window.slideDataMap.set(7, `
  <div class="w-[1440px] h-[810px] relative overflow-hidden slide-bg">
    <div class="absolute top-0 left-0 w-full h-[8px] bg-cyan-700"></div>
    <div class="w-[1350px] h-[720px] mx-auto my-[45px] relative pt-4 flex flex-col">

      <div class="flex items-center gap-4 mb-6">
        <div class="w-[6px] h-11 bg-cyan-700 rounded"></div>
        <div>
          <h2 class="text-[38px] font-bold text-slate-900 leading-tight">系统架构总览</h2>
          <p class="text-[15px] text-slate-500 mt-1">五层分层架构 · 端到端单机 Docker Compose 部署 · 四服务（web / api / db / redis）</p>
        </div>
      </div>

      <div class="flex gap-6 flex-1">
        <div class="w-[64%] flex flex-col gap-3">
          <div class="flex items-stretch gap-4">
            <div class="w-[168px] bg-cyan-700 rounded-xl flex flex-col items-center justify-center py-3 flex-shrink-0">
              <p class="text-white font-bold text-[16px]">① 用户侧</p>
              <p class="text-cyan-100 text-[12px] font-mono mt-0.5">CLIENTS</p>
            </div>
            <div class="flex-1 bg-white border border-slate-200 rounded-xl px-5 py-3 shadow-sm">
              <p class="text-[15px] text-slate-700 leading-relaxed"><span class="font-semibold text-slate-800">Web 演示端（16 页）</span> · <span class="font-semibold text-slate-800">微信小程序（42 页）</span> · <span class="font-semibold text-slate-800">管理后台（16 页）</span></p>
              <p class="text-[13px] text-slate-500 mt-1">三端共用同一套 REST 接口；Web 与后台使用 Vue 3 + Element Plus，小程序使用 uni-app，业务逻辑在共享包中复用</p>
            </div>
          </div>

          <div class="flex items-stretch gap-4">
            <div class="w-[168px] bg-sky-600 rounded-xl flex flex-col items-center justify-center py-3 flex-shrink-0">
              <p class="text-white font-bold text-[16px]">② 接入层</p>
              <p class="text-sky-100 text-[12px] font-mono mt-0.5">NGINX</p>
            </div>
            <div class="flex-1 bg-white border border-slate-200 rounded-xl px-5 py-3 shadow-sm">
              <p class="text-[15px] text-slate-700 leading-relaxed">Nginx 容器 80 端口映射到宿主机 <span class="font-mono font-semibold text-slate-800">8005</span>：静态资源托管 + <span class="font-mono">/v1</span>、<span class="font-mono">/api</span>、<span class="font-mono">/admin/v1</span> 反向代理</p>
              <p class="text-[13px] text-slate-500 mt-1">已启用 gzip 与静态资源缓存；TTS 流式接口单独配置 <span class="font-mono">proxy_buffering off</span>，保证边合成边播</p>
            </div>
          </div>

          <div class="flex items-stretch gap-4">
            <div class="w-[168px] bg-indigo-600 rounded-xl flex flex-col items-center justify-center py-3 flex-shrink-0">
              <p class="text-white font-bold text-[16px]">③ 应用层</p>
              <p class="text-indigo-100 text-[12px] font-mono mt-0.5">FASTAPI</p>
            </div>
            <div class="flex-1 bg-white border border-slate-200 rounded-xl px-5 py-3 shadow-sm">
              <p class="text-[15px] text-slate-700 leading-relaxed">Python 3.11 + FastAPI，<span class="font-semibold text-slate-800">121 个接口端点</span>，按业务域分组：<span class="font-mono text-[13px]">auth / recommend / cooking / nutrition / inventory / member / innovation / speech / vision / profile / home / trace</span></p>
              <p class="text-[13px] text-slate-500 mt-1">应用层依赖 Provider 抽象：LLM、视觉模型、语音、Embedding 全部可切换，缺省回退 mock 不影响启动</p>
            </div>
          </div>

          <div class="flex items-stretch gap-4">
            <div class="w-[168px] bg-orange-600 rounded-xl flex flex-col items-center justify-center py-3 flex-shrink-0">
              <p class="text-white font-bold text-[16px]">④ 编排与风控</p>
              <p class="text-orange-100 text-[12px] font-mono mt-0.5">LANGGRAPH</p>
            </div>
            <div class="flex-1 bg-white border-2 border-orange-200 rounded-xl px-5 py-3 shadow-sm">
              <p class="text-[15px] text-slate-700 leading-relaxed"><span class="font-semibold text-slate-800">LangGraph 编排中枢：22 个节点</span>（主图 13 + 子图 9），全图仅 1 个 LLM 节点（supervisor，仅做意图识别）</p>
              <p class="text-[13px] text-slate-500 mt-1">风控引擎为纯规则实现（27 条规则），位于主图入口与出口两侧，形成输入 / 输出双闸门；命中即控制流短路</p>
            </div>
          </div>

          <div class="flex items-stretch gap-4">
            <div class="w-[168px] bg-emerald-600 rounded-xl flex flex-col items-center justify-center py-3 flex-shrink-0">
              <p class="text-white font-bold text-[16px]">⑤ 数据层</p>
              <p class="text-emerald-100 text-[12px] font-mono mt-0.5">POSTGRES</p>
            </div>
            <div class="flex-1 bg-white border border-slate-200 rounded-xl px-5 py-3 shadow-sm">
              <p class="text-[15px] text-slate-700 leading-relaxed">PostgreSQL 16 + pgvector（单库 <span class="font-mono">aicook</span>，28–32 张表，3 个 Alembic 迁移）＋ Redis 7 缓存预留</p>
              <p class="text-[13px] text-slate-500 mt-1">语料 373 篇菜谱 md + 371 张封面图；创新菜写入用户私有向量分区，与公共知识库物理隔离</p>
            </div>
          </div>
        </div>

        <div class="w-[36%] bg-white border border-slate-200 rounded-xl p-6 shadow-sm flex flex-col">
          <h3 class="text-[19px] font-bold text-slate-800 mb-1">写进设计里的六条硬约束</h3>
          <p class="text-[13px] text-slate-500 mb-4">这些不是「建议」，而是代码结构中强制的规则</p>
          <div class="space-y-2.5 flex-1">
            <div class="flex items-start gap-2.5">
              <span class="text-cyan-700 font-bold text-[15px] mt-0.5">✓</span>
              <p class="text-[14px] text-slate-600 leading-relaxed">风控引擎<span class="font-semibold text-slate-800">不调用大模型</span>，保持确定性</p>
            </div>
            <div class="flex items-start gap-2.5">
              <span class="text-cyan-700 font-bold text-[15px] mt-0.5">✓</span>
              <p class="text-[14px] text-slate-600 leading-relaxed">一票否决 = <span class="font-semibold text-slate-800">控制流短路</span>，不是标记后丢弃</p>
            </div>
            <div class="flex items-start gap-2.5">
              <span class="text-cyan-700 font-bold text-[15px] mt-0.5">✓</span>
              <p class="text-[14px] text-slate-600 leading-relaxed">过敏原走<span class="font-semibold text-slate-800">布尔硬过滤</span>，绝不降权</p>
            </div>
            <div class="flex items-start gap-2.5">
              <span class="text-cyan-700 font-bold text-[15px] mt-0.5">✓</span>
              <p class="text-[14px] text-slate-600 leading-relaxed"><span class="font-semibold text-slate-800">双重风控</span>：输入侧与输出侧都不可省</p>
            </div>
            <div class="flex items-start gap-2.5">
              <span class="text-cyan-700 font-bold text-[15px] mt-0.5">✓</span>
              <p class="text-[14px] text-slate-600 leading-relaxed">风控异常或超时 → <span class="font-semibold text-slate-800">保守模式</span>，绝不直连模型</p>
            </div>
            <div class="flex items-start gap-2.5">
              <span class="text-cyan-700 font-bold text-[15px] mt-0.5">✓</span>
              <p class="text-[14px] text-slate-600 leading-relaxed"><span class="font-mono text-[13px]">need_user_confirm</span> 恒为 true，识别结果必须用户确认</p>
            </div>
          </div>
          <div class="mt-4 bg-slate-50 border border-slate-200 rounded-lg px-4 py-3">
            <p class="text-[13px] text-slate-500 leading-relaxed">另有 4 个模块级远程开关强制交付，可通过后台热更新，无需重新发版。</p>
          </div>
        </div>
      </div>

      <div class="mt-4 flex items-center justify-between text-[13px] text-slate-400">
        <span class="font-mono tracking-wider">AI 厨娘 · 智能烹饪助手 · 项目答辩</span>
        <span class="font-mono">07 / 24</span>
      </div>
    </div>
  </div>
`);
