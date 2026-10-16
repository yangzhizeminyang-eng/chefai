window.slideDataMap.set(21, `
  <div class="w-[1440px] h-[810px] relative overflow-hidden slide-bg">
    <div class="absolute top-0 left-0 w-full h-[8px] bg-indigo-600"></div>
    <div class="w-[1350px] h-[720px] mx-auto my-[45px] relative pt-4 flex flex-col">

      <div class="flex items-center justify-between mb-5">
        <div class="flex items-center gap-4">
          <div class="w-[6px] h-[42px] bg-indigo-600 rounded"></div>
          <div>
            <h2 class="text-[36px] font-bold text-slate-900 leading-tight">问题与解决方案总览</h2>
            <p class="text-[15px] text-slate-500 mt-1">问题 → 方案 → 结果：六类问题全部有落地动作与可验证结论，不做口头承诺</p>
          </div>
        </div>
        <span class="px-4 py-2 bg-indigo-50 border border-indigo-200 text-indigo-700 rounded-full text-[13px] font-medium">横向逐行对照阅读</span>
      </div>

      <div class="flex gap-4 flex-1">
        <div class="w-1/3 flex flex-col">
          <div class="bg-rose-600 rounded-t-xl px-5 py-3">
            <p class="text-white font-bold text-[16px]">① 遇到的问题</p>
            <p class="text-rose-100 text-[12px]">六类典型问题</p>
          </div>
          <div class="bg-white border border-slate-200 border-t-0 rounded-b-xl p-3 space-y-2 flex-1">
            <div class="bg-rose-50/70 border border-rose-100 rounded-lg px-3.5 py-2.5"><p class="text-[13px] text-slate-700 leading-relaxed">纯手选食材路径不携带文本，向量召回不触发，RAG 只用到一半</p></div>
            <div class="bg-rose-50/70 border border-rose-100 rounded-lg px-3.5 py-2.5"><p class="text-[13px] text-slate-700 leading-relaxed">默认嵌入为哈希伪向量，是字面重叠而非语义相似</p></div>
            <div class="bg-rose-50/70 border border-rose-100 rounded-lg px-3.5 py-2.5"><p class="text-[13px] text-slate-700 leading-relaxed">过敏原必须硬过滤，而口味偏好只应降权，两套语义容易混用</p></div>
            <div class="bg-rose-50/70 border border-rose-100 rounded-lg px-3.5 py-2.5"><p class="text-[13px] text-slate-700 leading-relaxed">2C2G 服务器构建前端镜像峰值超 1.5GB，必定 OOM</p></div>
            <div class="bg-rose-50/70 border border-rose-100 rounded-lg px-3.5 py-2.5"><p class="text-[13px] text-slate-700 leading-relaxed">镜像加速源对写死 registry 前缀的镜像名不生效</p></div>
            <div class="bg-rose-50/70 border border-rose-100 rounded-lg px-3.5 py-2.5"><p class="text-[13px] text-slate-700 leading-relaxed">http + 公网 IP 下麦克风静默失效，不报错也不工作</p></div>
          </div>
        </div>

        <div class="w-1/3 flex flex-col">
          <div class="bg-amber-500 rounded-t-xl px-5 py-3">
            <p class="text-white font-bold text-[16px]">② 解决方案</p>
            <p class="text-amber-50 text-[12px]">对应的六个动作</p>
          </div>
          <div class="bg-white border border-slate-200 border-t-0 rounded-b-xl p-3 space-y-2 flex-1">
            <div class="bg-amber-50/70 border border-amber-100 rounded-lg px-3.5 py-2.5"><p class="text-[13px] text-slate-700 leading-relaxed">补齐三路召回：覆盖率恒生效、文本召回补文本解析、向量召回补条件判定</p></div>
            <div class="bg-amber-50/70 border border-amber-100 rounded-lg px-3.5 py-2.5"><p class="text-[13px] text-slate-700 leading-relaxed">修复向量升级三缺口：建库命令、环境变量、嵌入空间版本迁移并留痕</p></div>
            <div class="bg-amber-50/70 border border-amber-100 rounded-lg px-3.5 py-2.5"><p class="text-[13px] text-slate-700 leading-relaxed">过敏原走布尔硬过滤，dislike 走降权 −0.5，语义与实现双重区分</p></div>
            <div class="bg-amber-50/70 border border-amber-100 rounded-lg px-3.5 py-2.5"><p class="text-[13px] text-slate-700 leading-relaxed">构建与运行分离：本地 build → save → scp → load，脚本固化进部署流程</p></div>
            <div class="bg-amber-50/70 border border-amber-100 rounded-lg px-3.5 py-2.5"><p class="text-[13px] text-slate-700 leading-relaxed">先经加速拉取官方镜像，再 docker tag 打上带前缀的别名</p></div>
            <div class="bg-amber-50/70 border border-amber-100 rounded-lg px-3.5 py-2.5"><p class="text-[13px] text-slate-700 leading-relaxed">上 HTTPS 或自签证书；同时把该约束登记为风险条目 R-31</p></div>
          </div>
        </div>

        <div class="w-1/3 flex flex-col">
          <div class="bg-emerald-600 rounded-t-xl px-5 py-3">
            <p class="text-white font-bold text-[16px]">③ 验证结果</p>
            <p class="text-emerald-50 text-[12px]">可复现的结论</p>
          </div>
          <div class="bg-white border border-slate-200 border-t-0 rounded-b-xl p-3 space-y-2 flex-1">
            <div class="bg-emerald-50/70 border border-emerald-100 rounded-lg px-3.5 py-2.5"><p class="text-[13px] text-slate-700 leading-relaxed">三缺口已闭环，方案与代码口径对齐并双文档留痕（R-27）</p></div>
            <div class="bg-emerald-50/70 border border-emerald-100 rounded-lg px-3.5 py-2.5"><p class="text-[13px] text-slate-700 leading-relaxed">剩余限制登记为改进项，随语义嵌入模型升级一并解决</p></div>
            <div class="bg-emerald-50/70 border border-emerald-100 rounded-lg px-3.5 py-2.5"><p class="text-[13px] text-slate-700 leading-relaxed">12 条安全红线全绿；被过滤菜谱可在前端逐条重放原因</p></div>
            <div class="bg-emerald-50/70 border border-emerald-100 rounded-lg px-3.5 py-2.5"><p class="text-[13px] text-slate-700 leading-relaxed">生产环境 8005 全端点 200，健康检查返回数据库 up</p></div>
            <div class="bg-emerald-50/70 border border-emerald-100 rounded-lg px-3.5 py-2.5"><p class="text-[13px] text-slate-700 leading-relaxed">部署脚本固化 8 步，含基础镜像准备、语料校验与端口断言</p></div>
            <div class="bg-emerald-50/70 border border-emerald-100 rounded-lg px-3.5 py-2.5"><p class="text-[13px] text-slate-700 leading-relaxed">端口安全复查与 HTTPS 落地登记为 R-31 / R-33，明确触发条件</p></div>
          </div>
        </div>
      </div>

      <div class="mt-4 flex items-center justify-between text-[13px] text-slate-400">
        <span class="font-mono tracking-wider">AI 厨娘 · 智能烹饪助手 · 项目答辩</span>
        <span class="font-mono">21 / 25</span>
      </div>
    </div>
  </div>
`);
