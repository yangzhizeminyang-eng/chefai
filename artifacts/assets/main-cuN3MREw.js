(function(){const e=document.createElement("link").relList;if(e&&e.supports&&e.supports("modulepreload"))return;for(const t of document.querySelectorAll('link[rel="modulepreload"]'))l(t);new MutationObserver(t=>{for(const a of t)if(a.type==="childList")for(const d of a.addedNodes)d.tagName==="LINK"&&d.rel==="modulepreload"&&l(d)}).observe(document,{childList:!0,subtree:!0});function s(t){const a={};return t.integrity&&(a.integrity=t.integrity),t.referrerPolicy&&(a.referrerPolicy=t.referrerPolicy),t.crossOrigin==="use-credentials"?a.credentials="include":t.crossOrigin==="anonymous"?a.credentials="omit":a.credentials="same-origin",a}function l(t){if(t.ep)return;t.ep=!0;const a=s(t);fetch(t.href,a)}})();class o{constructor(){this.currentIndex=0,this.slides=[],this.totalSlides=0,this.viewport=document.getElementById("ppt-viewport"),this.prevBtn=document.getElementById("prevBtn"),this.nextBtn=document.getElementById("nextBtn"),this.progressBarFill=document.getElementById("progressBarFill"),this.pageIndicator=document.getElementById("pageIndicator"),this.init(),this.initWindowMessage()}init(){this.loadSlides(),this.bindEvents(),this.initializePage(),this.updateUI(),this.updateViewportScale()}initWindowMessage(){window.addEventListener("message",e=>{if(!e.data||typeof e.data!="object")return;const{type:s,data:l}=e.data;s==="childrenstart"?(this.prevBtn.style.visibility="hidden",this.nextBtn.style.visibility="hidden",this.progressBarFill.style.visibility="hidden",this.pageIndicator.style.visibility="hidden"):s==="childrenstop"&&(this.prevBtn.style.visibility="visible",this.nextBtn.style.visibility="visible",this.progressBarFill.style.visibility="visible",this.pageIndicator.style.visibility="visible")})}initializePage(){const e=new URLSearchParams(window.location.search);let s=e.get("page");if(!s){s="1",e.set("page","1");const a=`${window.location.pathname}?${e.toString()}`;window.history.replaceState({},"",a)}const l=parseInt(s,10),t=l-1;if(!isNaN(l)&&t>=0&&t<this.totalSlides)this.slides[0]&&this.slides[0].classList.remove("active"),this.currentIndex=t,this.slides[t]&&this.slides[t].classList.add("active");else{console.warn(`无效的页码参数: ${s}，将显示第 1 页`),e.set("page","1");const a=`${window.location.pathname}?${e.toString()}`;window.history.replaceState({},"",a)}}loadSlides(){if(typeof window.slideDataMap>"u"){console.error("未找到 slideDataMap");return}const e=Array.from(window.slideDataMap.keys()).sort((s,l)=>s-l);if(this.totalSlides=e.length,this.totalSlides===0){console.warn("slideDataMap 为空，没有幻灯片可加载");return}e.forEach((s,l)=>{const t=document.createElement("div");t.className="slide",l===0&&t.classList.add("active");const a=window.slideDataMap.get(s);if(!a||typeof a!="string"){this.totalSlides--,console.error(`未找到页码 ${s} 的内容, 或者页码 ${s} 的内容为空`);return}const d=document.createElement("div");d.innerHTML=a.trim(),t.appendChild(d),this.viewport.appendChild(t),this.slides.push(t)})}bindEvents(){this.prevBtn.addEventListener("click",()=>this.prevSlide()),this.nextBtn.addEventListener("click",()=>this.nextSlide()),document.addEventListener("keydown",s=>{s.key==="ArrowLeft"?this.prevSlide():s.key==="ArrowRight"||s.key===" "?(s.preventDefault(),this.nextSlide()):s.key==="Home"?this.goToSlide(0):s.key==="End"&&this.goToSlide(this.totalSlides-1)});let e=0;this.viewport.addEventListener("touchstart",s=>{e=s.touches[0].clientX}),this.viewport.addEventListener("touchend",s=>{const l=s.changedTouches[0].clientX,t=e-l;Math.abs(t)>50&&(t>0?this.nextSlide():this.prevSlide())}),window.addEventListener("resize",()=>this.updateViewportScale())}prevSlide(){this.currentIndex>0&&this.goToSlide(this.currentIndex-1)}nextSlide(){this.currentIndex<this.totalSlides-1&&this.goToSlide(this.currentIndex+1)}goToSlide(e){e<0||e>=this.totalSlides||(this.slides[this.currentIndex].classList.remove("active"),this.currentIndex=e,this.slides[this.currentIndex].classList.add("active"),this.updateUrlPage(e+1),this.updateUI())}updateUrlPage(e){const s=new URLSearchParams(window.location.search);s.set("page",e.toString());const l=`${window.location.pathname}?${s.toString()}`;window.history.replaceState({},"",l)}updateUI(){if(this.totalSlides===0){this.prevBtn.disabled=!0,this.nextBtn.disabled=!0,this.progressBarFill.style.width="0%",this.pageIndicator.textContent="制作中";return}this.prevBtn.disabled=this.currentIndex===0,this.nextBtn.disabled=this.currentIndex===this.totalSlides-1;const e=(this.currentIndex+1)/this.totalSlides*100;this.progressBarFill.style.width=`${e}%`,this.pageIndicator.textContent=`${this.currentIndex+1} / ${this.totalSlides}`}updateViewportScale(){const t=window.innerWidth-40,a=window.innerHeight-40,d=t/1440,x=a/810,p=Math.min(d,x,1);this.viewport.style.transform=`scale(${p})`,console.log(`窗口: ${window.innerWidth}x${window.innerHeight}, 缩放: ${p.toFixed(3)}`)}}class i{constructor(){this.validRoutes=["/","/index.html"],this.checkRoute()}checkRoute(){const e=window.location.pathname;if(e.includes("404.html"))return;this.validRoutes.some(l=>l==="/"?e==="/"||e==="/index.html":e===l)||(console.warn(`Invalid route detected: ${e}, redirecting to 404`),window.location.href="/404.html")}addRoute(e){this.validRoutes.includes(e)||this.validRoutes.push(e)}isValidRoute(e){return this.validRoutes.includes(e)}}window.addEventListener("DOMContentLoaded",()=>{new i,new o});window.slideDataMap.set(1,`
  <div class="w-[1440px] h-[810px] relative overflow-hidden slide-bg">
    <div class="absolute inset-0" style="background-image: linear-gradient(#E6EDF5 1px, transparent 1px), linear-gradient(90deg,#E6EDF5 1px, transparent 1px); background-size: 48px 48px;"></div>
    <div class="absolute -bottom-48 -left-40 w-[560px] h-[560px] bg-cyan-100 rounded-full blur-3xl opacity-70"></div>
    <div class="absolute -top-32 -right-24 w-[460px] h-[460px] bg-orange-100 rounded-full blur-3xl opacity-70"></div>
    <div class="absolute top-0 left-0 w-full h-[10px] bg-cyan-700"></div>
    <div class="absolute top-[10px] left-0 w-[36%] h-[5px] bg-orange-600"></div>

    <div class="relative z-10 h-full flex flex-col items-center justify-center px-24 text-center">
      <div class="inline-flex items-center gap-2 bg-cyan-50 border border-cyan-200 text-cyan-800 px-5 py-2 rounded-full text-[15px] font-medium mb-9">
        <span class="w-2 h-2 bg-cyan-700 rounded-full animate-pulse"></span>
        阶段一交付完成 ｜ Web 端已部署上线 ｜ 16/16 页面实测可达
      </div>

      <h1 class="text-[112px] font-bold leading-none tracking-tight mb-7 text-slate-900">
        <span class="text-cyan-700">AI</span> 厨娘
      </h1>
      <p class="text-[30px] text-slate-700 font-light tracking-[0.22em] mb-5">智能烹饪助手 · 项目答辩</p>
      <p class="text-[17px] text-slate-500 leading-relaxed max-w-[1000px] mb-14">
        以 LangGraph 多智能体编排为核心，串联「食材输入 → 智能推荐 → 分步引导 → 营养分析 → 库存管理 → 会员服务」全链路，
        并以纯规则风控引擎守住食品安全底线。三端 74 页、前端 47,736 行代码、后端 121 个接口。
      </p>

      <div class="flex items-center gap-12 bg-white/90 border border-slate-200 rounded-2xl px-14 py-7 shadow-sm">
        <div class="text-center">
          <p class="text-[12px] text-slate-400 font-mono tracking-[0.25em] mb-2">PRESENTED BY</p>
          <p class="text-[28px] font-bold text-slate-900 tracking-[0.18em]">肖裔雄</p>
        </div>
        <div class="w-px h-16 bg-slate-200"></div>
        <div class="text-center">
          <p class="text-[12px] text-slate-400 font-mono tracking-[0.25em] mb-2">DATE</p>
          <p class="text-[28px] font-bold text-slate-900">2026.10.14</p>
        </div>
        <div class="w-px h-16 bg-slate-200"></div>
        <div class="text-center">
          <p class="text-[12px] text-slate-400 font-mono tracking-[0.25em] mb-2">STATUS</p>
          <p class="text-[28px] font-bold text-cyan-700">已上线</p>
        </div>
      </div>
    </div>
  </div>
`);window.slideDataMap.set(2,`
  <div class="w-[1440px] h-[810px] relative overflow-hidden slide-bg">
    <div class="absolute inset-0" style="background-image: linear-gradient(#E6EDF5 1px, transparent 1px), linear-gradient(90deg,#E6EDF5 1px, transparent 1px); background-size: 48px 48px;"></div>
    <div class="absolute top-0 left-0 w-full h-[10px] bg-cyan-700"></div>

    <div class="w-[1350px] h-[720px] mx-auto my-[45px] relative z-10 flex flex-col justify-center pt-6">
      <div class="flex items-end justify-between mb-9">
        <div>
          <h2 class="text-[46px] font-bold text-slate-900 mb-2">目录 <span class="text-[26px] font-normal text-slate-400 font-mono tracking-widest">CONTENTS</span></h2>
          <p class="text-[16px] text-slate-500">四个部分，回答三个问题：做了什么、怎么做的、学到了什么</p>
        </div>
        <div class="text-right">
          <p class="text-[13px] text-slate-400 font-mono">25 PAGES · 4 CHAPTERS</p>
          <p class="text-[13px] text-slate-400 font-mono">2026.10.14</p>
        </div>
      </div>

      <div class="space-y-4">
        <div class="flex items-center gap-7 bg-white border border-slate-200 border-l-[6px] border-l-cyan-700 rounded-xl px-8 py-5 shadow-sm">
          <span class="text-[40px] font-bold text-cyan-700 font-mono leading-none w-[70px]">01</span>
          <div class="flex-1">
            <h3 class="text-[24px] font-bold text-slate-800 mb-1">项目概述与技术架构</h3>
            <p class="text-[15px] text-slate-500">项目背景与产品定位 · 协作模式与交付物 · 交付成果核心指标 · 五层系统架构 · 技术栈选型 · 数据与语料资产</p>
          </div>
          <span class="text-[13px] text-cyan-700 bg-cyan-50 border border-cyan-200 rounded-full px-4 py-1.5 font-medium whitespace-nowrap">7 页</span>
        </div>

        <div class="flex items-center gap-7 bg-white border border-slate-200 border-l-[6px] border-l-orange-600 rounded-xl px-8 py-5 shadow-sm">
          <span class="text-[40px] font-bold text-orange-600 font-mono leading-none w-[70px]">02</span>
          <div class="flex-1">
            <h3 class="text-[24px] font-bold text-slate-800 mb-1">重点模块与精彩代码</h3>
            <p class="text-[15px] text-slate-500">智能菜谱推荐 · <span class="text-orange-600 font-semibold">LangGraph 主图拓扑</span> · 路由机制与两张子图 · 图结构运行期校验与自检发现 · 食品安全风控 · 其余核心能力速览 · 两段关键代码 · 真实界面演示</p>
          </div>
          <span class="text-[13px] text-orange-600 bg-orange-50 border border-orange-200 rounded-full px-4 py-1.5 font-medium whitespace-nowrap">10 页</span>
        </div>

        <div class="flex items-center gap-7 bg-white border border-slate-200 border-l-[6px] border-l-indigo-600 rounded-xl px-8 py-5 shadow-sm">
          <span class="text-[40px] font-bold text-indigo-600 font-mono leading-none w-[70px]">03</span>
          <div class="flex-1">
            <h3 class="text-[24px] font-bold text-slate-800 mb-1">问题与解决方案</h3>
            <p class="text-[15px] text-slate-500">六类问题 × 方案 × 验证结果总览 · 四个典型案例深剖（检索缺口 / 构建 OOM / 镜像加速失效 / 语音静默失效）</p>
          </div>
          <span class="text-[13px] text-indigo-600 bg-indigo-50 border border-indigo-200 rounded-full px-4 py-1.5 font-medium whitespace-nowrap">3 页</span>
        </div>

        <div class="flex items-center gap-7 bg-white border border-slate-200 border-l-[6px] border-l-emerald-600 rounded-xl px-8 py-5 shadow-sm">
          <span class="text-[40px] font-bold text-emerald-600 font-mono leading-none w-[70px]">04</span>
          <div class="flex-1">
            <h3 class="text-[24px] font-bold text-slate-800 mb-1">项目完成后的收获</h3>
            <p class="text-[15px] text-slate-500">技术深度 · 工程能力 · 产品思维 · 协作规范 · 风险意识 —— 从「能跑」到「敢上线」的五项成长</p>
          </div>
          <span class="text-[13px] text-emerald-600 bg-emerald-50 border border-emerald-200 rounded-full px-4 py-1.5 font-medium whitespace-nowrap">2 页</span>
        </div>
      </div>

      <div class="mt-8 flex items-center gap-8 text-[14px] text-slate-500 bg-white/80 border border-slate-200 rounded-xl px-8 py-4">
        <span class="font-medium text-slate-700">本次答辩重点：</span>
        <span class="flex items-center gap-2"><span class="w-2 h-2 rounded-full bg-cyan-700"></span>三大核心模块的实现路径</span>
        <span class="flex items-center gap-2"><span class="w-2 h-2 rounded-full bg-orange-600"></span>LangGraph 图结构与编排设计</span>
        <span class="flex items-center gap-2"><span class="w-2 h-2 rounded-full bg-indigo-600"></span>问题排查与工程取舍</span>
      </div>
    </div>
  </div>
`);window.slideDataMap.set(3,`
  <div class="w-[1440px] h-[810px] relative overflow-hidden slide-bg flex items-center justify-center">
    <div class="absolute inset-0" style="background-image: linear-gradient(#E6EDF5 1px, transparent 1px), linear-gradient(90deg,#E6EDF5 1px, transparent 1px); background-size: 48px 48px;"></div>
    <div class="absolute -top-40 -right-32 w-[520px] h-[520px] bg-cyan-100 rounded-full blur-3xl opacity-60"></div>

    <div class="w-[1180px] bg-white rounded-3xl border border-slate-200 shadow-sm px-16 py-12 relative overflow-hidden">
      <div class="absolute left-0 top-0 w-full h-[8px] bg-cyan-700"></div>
      <div class="absolute right-10 top-6 text-[150px] font-bold text-slate-50 font-mono leading-none select-none">01</div>

      <div class="relative">
        <div class="inline-flex items-center gap-2 bg-cyan-50 border border-cyan-200 text-cyan-800 px-4 py-1.5 rounded-full text-[14px] font-medium mb-6">
          CHAPTER 01
        </div>
        <h1 class="text-[54px] font-bold text-slate-900 mb-4 tracking-tight">项目概述与技术架构</h1>
        <p class="text-[20px] text-slate-500 mb-10 leading-relaxed">
          先回答「这是什么项目、交付了多少、它长什么样」—— 从产品定位与协作模式，到五层系统架构与技术栈选型，建立全局坐标。
        </p>

        <div class="grid grid-cols-3 gap-6">
          <div class="bg-slate-50 border border-slate-200 rounded-xl px-6 py-5">
            <p class="text-[34px] font-bold text-cyan-700 font-mono leading-none mb-2">74<span class="text-[18px] ml-1">页</span></p>
            <p class="text-[14px] text-slate-500">三端页面总数（Web 16 / 小程序 42 / 后台 16）</p>
          </div>
          <div class="bg-slate-50 border border-slate-200 rounded-xl px-6 py-5">
            <p class="text-[34px] font-bold text-orange-600 font-mono leading-none mb-2">47,736<span class="text-[18px] ml-1">行</span></p>
            <p class="text-[14px] text-slate-500">前端代码量（三端合计）</p>
          </div>
          <div class="bg-slate-50 border border-slate-200 rounded-xl px-6 py-5">
            <p class="text-[34px] font-bold text-indigo-600 font-mono leading-none mb-2">121<span class="text-[18px] ml-1">个</span></p>
            <p class="text-[14px] text-slate-500">后端接口端点（118 个 py 模块）</p>
          </div>
        </div>
      </div>
    </div>
  </div>
`);window.slideDataMap.set(4,`
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
`);window.slideDataMap.set(5,`
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
`);window.slideDataMap.set(6,`
  <div class="w-[1440px] h-[810px] relative overflow-hidden slide-bg">
    <div class="absolute top-0 left-0 w-full h-[8px] bg-cyan-700"></div>
    <div class="w-[1350px] h-[720px] mx-auto my-[45px] relative pt-4 flex flex-col">

      <div class="flex items-center justify-between mb-7">
        <div class="flex items-center gap-4">
          <div class="w-[6px] h-11 bg-cyan-700 rounded"></div>
          <div>
            <h2 class="text-[38px] font-bold text-slate-900 leading-tight">交付成果核心指标</h2>
            <p class="text-[15px] text-slate-500 mt-1">全部数据来自本地实测与线上实探，可用附录命令独立复现</p>
          </div>
        </div>
        <div class="bg-white border border-slate-200 rounded-xl px-6 py-3 text-right shadow-sm">
          <p class="text-[12px] text-slate-400 font-mono mb-1">WEIGHTED COMPLETION</p>
          <p class="text-[32px] font-bold text-cyan-700 font-mono leading-none">≈ 88<span class="text-[18px]">%</span></p>
        </div>
      </div>

      <div class="grid grid-cols-4 gap-5 mb-6">
        <div class="bg-white border border-slate-200 border-t-[5px] border-t-cyan-700 rounded-xl px-5 py-5 shadow-sm">
          <p class="text-[38px] font-bold text-cyan-700 font-mono leading-none mb-2">74</p>
          <p class="text-[16px] font-semibold text-slate-800 mb-1">交付页面（三端）</p>
          <p class="text-[13px] text-slate-500 leading-relaxed">Web 16 + 微信小程序 42 + 管理后台 16，全部完成注册与路由配置</p>
        </div>
        <div class="bg-white border border-slate-200 border-t-[5px] border-t-orange-600 rounded-xl px-5 py-5 shadow-sm">
          <p class="text-[38px] font-bold text-orange-600 font-mono leading-none mb-2">47,736</p>
          <p class="text-[16px] font-semibold text-slate-800 mb-1">前端代码行数</p>
          <p class="text-[13px] text-slate-500 leading-relaxed">Web 18,486 + 后台 3,375 + 小程序 25,875，逻辑层通过共享包复用</p>
        </div>
        <div class="bg-white border border-slate-200 border-t-[5px] border-t-indigo-600 rounded-xl px-5 py-5 shadow-sm">
          <p class="text-[38px] font-bold text-indigo-600 font-mono leading-none mb-2">121</p>
          <p class="text-[16px] font-semibold text-slate-800 mb-1">后端接口端点</p>
          <p class="text-[13px] text-slate-500 leading-relaxed">118 个 py 模块、3 个数据库迁移、46 个测试文件，覆盖推荐与风控全链路</p>
        </div>
        <div class="bg-white border border-slate-200 border-t-[5px] border-t-emerald-600 rounded-xl px-5 py-5 shadow-sm">
          <p class="text-[38px] font-bold text-emerald-600 font-mono leading-none mb-2">319</p>
          <p class="text-[16px] font-semibold text-slate-800 mb-1">后端单测通过</p>
          <p class="text-[13px] text-slate-500 leading-relaxed">319 passed / 1 skipped；前端另有 236 + 45 条用例，43 条 E2E 全闭环</p>
        </div>
      </div>

      <div class="flex gap-5 flex-1">
        <div class="w-[62%] bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
          <h3 class="text-[19px] font-bold text-slate-800 mb-4">三端实现明细</h3>
          <div class="space-y-4">
            <div>
              <div class="flex items-center justify-between mb-1.5">
                <span class="text-[15px] font-semibold text-slate-700">Web 演示端 <span class="font-mono text-slate-400 text-[13px]">web-stage1</span></span>
                <span class="text-[14px] font-mono text-slate-500">16 页 · 18,486 行</span>
              </div>
              <div class="h-2.5 bg-slate-100 rounded-full overflow-hidden"><div class="h-full bg-cyan-700 rounded-full" style="width:100%"></div></div>
              <p class="text-[13px] text-slate-500 mt-1.5">Vue 3 + Vite + TS + Pinia + Element Plus；含 W-06 Agent 调度可视化面板等专属交付页</p>
            </div>
            <div>
              <div class="flex items-center justify-between mb-1.5">
                <span class="text-[15px] font-semibold text-slate-700">微信小程序 <span class="font-mono text-slate-400 text-[13px]">web-mini</span></span>
                <span class="text-[14px] font-mono text-slate-500">42 页 · 25,875 行</span>
              </div>
              <div class="h-2.5 bg-slate-100 rounded-full overflow-hidden"><div class="h-full bg-orange-600 rounded-full" style="width:100%"></div></div>
              <p class="text-[13px] text-slate-500 mt-1.5">uni-app + Vue 3 + Pinia，六个分包：主包 / recommend / cooking / nutrition / member / innovation</p>
            </div>
            <div>
              <div class="flex items-center justify-between mb-1.5">
                <span class="text-[15px] font-semibold text-slate-700">管理后台 <span class="font-mono text-slate-400 text-[13px]">admin-web</span></span>
                <span class="text-[14px] font-mono text-slate-500">16 页 · 3,375 行</span>
              </div>
              <div class="h-2.5 bg-slate-100 rounded-full overflow-hidden"><div class="h-full bg-indigo-600 rounded-full" style="width:100%"></div></div>
              <p class="text-[13px] text-slate-500 mt-1.5">风控规则、违禁词、创新巡检、开关管理（远程配置）、操作日志、调度日志等运营侧能力</p>
            </div>
          </div>
        </div>

        <div class="w-[38%] bg-white border border-slate-200 rounded-xl p-6 shadow-sm flex flex-col">
          <h3 class="text-[19px] font-bold text-slate-800 mb-4">质量与上线</h3>
          <div class="space-y-3 flex-1">
            <div class="flex items-center justify-between bg-slate-50 rounded-lg px-4 py-3">
              <span class="text-[14px] text-slate-600">页面实测可达</span>
              <span class="text-[15px] font-bold text-emerald-600 font-mono">16 / 16</span>
            </div>
            <div class="flex items-center justify-between bg-slate-50 rounded-lg px-4 py-3">
              <span class="text-[14px] text-slate-600">控制台 Error</span>
              <span class="text-[15px] font-bold text-emerald-600 font-mono">0</span>
            </div>
            <div class="flex items-center justify-between bg-slate-50 rounded-lg px-4 py-3">
              <span class="text-[14px] text-slate-600">安全红线</span>
              <span class="text-[15px] font-bold text-emerald-600 font-mono">12 条全绿</span>
            </div>
            <div class="flex items-center justify-between bg-slate-50 rounded-lg px-4 py-3">
              <span class="text-[14px] text-slate-600">E2E 用例</span>
              <span class="text-[15px] font-bold text-slate-700 font-mono">43 条 · 缺陷全闭环</span>
            </div>
            <div class="bg-cyan-50 border border-cyan-200 rounded-lg px-4 py-3">
              <p class="text-[13px] text-cyan-800 mb-1 font-semibold">生产环境实探</p>
              <p class="text-[13px] text-cyan-700 font-mono leading-relaxed">YOUR_SERVER_IP:8005<br/>用户端 / 后台 / healthz 全部 200，DB up</p>
            </div>
          </div>
        </div>
      </div>

      <div class="mt-4 flex items-center justify-between text-[13px] text-slate-400">
        <span class="font-mono tracking-wider">AI 厨娘 · 智能烹饪助手 · 项目答辩</span>
        <span class="font-mono">06 / 25</span>
      </div>
    </div>
  </div>
`);window.slideDataMap.set(7,`
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
        <span class="font-mono">07 / 25</span>
      </div>
    </div>
  </div>
`);window.slideDataMap.set(8,`
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
`);window.slideDataMap.set(9,`
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
`);window.slideDataMap.set(10,`
  <div class="w-[1440px] h-[810px] relative overflow-hidden slide-bg flex items-center justify-center">
    <div class="absolute inset-0" style="background-image: linear-gradient(#E6EDF5 1px, transparent 1px), linear-gradient(90deg,#E6EDF5 1px, transparent 1px); background-size: 48px 48px;"></div>
    <div class="absolute -top-40 -left-32 w-[520px] h-[520px] bg-orange-100 rounded-full blur-3xl opacity-60"></div>

    <div class="w-[1180px] bg-white rounded-3xl border border-slate-200 shadow-sm px-16 py-12 relative overflow-hidden">
      <div class="absolute left-0 top-0 w-full h-[8px] bg-orange-600"></div>
      <div class="absolute right-10 top-6 text-[150px] font-bold text-slate-50 font-mono leading-none select-none">02</div>

      <div class="relative">
        <div class="inline-flex items-center gap-2 bg-orange-50 border border-orange-200 text-orange-700 px-4 py-1.5 rounded-full text-[14px] font-medium mb-6">
          CHAPTER 02
        </div>
        <h1 class="text-[54px] font-bold text-slate-900 mb-4 tracking-tight">重点模块与精彩代码</h1>
        <p class="text-[20px] text-slate-500 mb-10 leading-relaxed">
          本部分回答「到底怎么做的」：三个核心模块的真实实现路径，其中包含<span class="font-semibold text-orange-600">编译后导出</span>的完整 LangGraph 图结构、路由机制与两张子图，以及两段最能体现设计取舍的代码。
        </p>

        <div class="grid grid-cols-4 gap-5">
          <div class="bg-slate-50 border border-slate-200 rounded-xl px-5 py-5">
            <p class="text-[30px] font-bold text-cyan-700 font-mono leading-none mb-2">13</p>
            <p class="text-[14px] text-slate-500 leading-relaxed">主图节点数（编译后导出的运行期拓扑）</p>
          </div>
          <div class="bg-slate-50 border border-slate-200 rounded-xl px-5 py-5">
            <p class="text-[30px] font-bold text-orange-600 font-mono leading-none mb-2">24</p>
            <p class="text-[14px] text-slate-500 leading-relaxed">主图边数，其中 13 条为显式白名单条件边</p>
          </div>
          <div class="bg-slate-50 border border-slate-200 rounded-xl px-5 py-5">
            <p class="text-[30px] font-bold text-indigo-600 font-mono leading-none mb-2">3</p>
            <p class="text-[14px] text-slate-500 leading-relaxed">张 StateGraph：1 主图 + 推荐子图 / 创新子图</p>
          </div>
          <div class="bg-slate-50 border border-slate-200 rounded-xl px-5 py-5">
            <p class="text-[30px] font-bold text-emerald-600 font-mono leading-none mb-2">18</p>
            <p class="text-[14px] text-slate-500 leading-relaxed">图结构单测 passed，拓扑红线全部通过</p>
          </div>
        </div>
      </div>
    </div>
  </div>
`);window.slideDataMap.set(11,`
  <div class="w-[1440px] h-[810px] relative overflow-hidden slide-bg">
    <div class="absolute top-0 left-0 w-full h-[8px] bg-cyan-700"></div>
    <div class="w-[1350px] h-[720px] mx-auto my-[45px] relative pt-4 flex flex-col">

      <div class="flex items-center justify-between mb-4">
        <div class="flex items-center gap-4">
          <div class="w-[6px] h-[42px] bg-cyan-700 rounded"></div>
          <div>
            <h2 class="text-[36px] font-bold text-slate-900 leading-tight">重点模块① 智能菜谱推荐</h2>
            <p class="text-[15px] text-slate-500 mt-1">第一主路径 · 推荐子图 5 节点 · <span class="text-cyan-700 font-semibold">全程不调用大模型</span>，确定性、可解释、可审计</p>
          </div>
        </div>
        <div class="flex gap-3">
          <span class="px-4 py-2 bg-cyan-50 border border-cyan-200 text-cyan-800 rounded-full text-[13px] font-medium">模块完成度 98%</span>
          <span class="px-4 py-2 bg-slate-50 border border-slate-200 text-slate-600 rounded-full text-[13px] font-medium">0 次 LLM 调用</span>
        </div>
      </div>

      <div class="bg-white border border-slate-200 rounded-xl px-5 py-4 shadow-sm mb-4">
        <div class="flex items-center gap-2.5">
          <div class="flex-1 bg-cyan-50 border-2 border-cyan-200 rounded-lg px-3 py-2.5 text-center">
            <p class="text-[11px] font-mono text-cyan-700 mb-0.5">assemble_context</p>
            <p class="text-[14px] font-bold text-slate-800 mb-0.5">① 上下文归一</p>
            <p class="text-[11px] text-slate-500">食材名 / 别名 → ingredient_id</p>
          </div>
          <span class="text-slate-300 text-[18px] flex-shrink-0">➜</span>
          <div class="flex-1 bg-sky-50 border-2 border-sky-200 rounded-lg px-3 py-2.5 text-center">
            <p class="text-[11px] font-mono text-sky-700 mb-0.5">recipe_retrieve</p>
            <p class="text-[14px] font-bold text-slate-800 mb-0.5">② 三路混合召回</p>
            <p class="text-[11px] text-slate-500">覆盖率 / 文本 / 向量 · ≤200</p>
          </div>
          <span class="text-slate-300 text-[18px] flex-shrink-0">➜</span>
          <div class="flex-1 bg-orange-50 border-2 border-orange-200 rounded-lg px-3 py-2.5 text-center">
            <p class="text-[11px] font-mono text-orange-700 mb-0.5">hard_filter</p>
            <p class="text-[14px] font-bold text-slate-800 mb-0.5">③ 布尔硬过滤</p>
            <p class="text-[11px] text-slate-500">SQL WHERE 四维布尔运算</p>
          </div>
          <span class="text-slate-300 text-[18px] flex-shrink-0">➜</span>
          <div class="flex-1 bg-indigo-50 border-2 border-indigo-200 rounded-lg px-3 py-2.5 text-center relative">
            <span class="absolute -top-2.5 right-2 text-[10px] px-2 py-0.5 bg-indigo-600 text-white rounded-full">与⑤并行</span>
            <p class="text-[11px] font-mono text-indigo-700 mb-0.5">recipe_rank</p>
            <p class="text-[14px] font-bold text-slate-800 mb-0.5">④ 7 因子加权</p>
            <p class="text-[11px] text-slate-500">输出 rank_reasons → Top 8</p>
          </div>
          <span class="text-slate-300 text-[18px] flex-shrink-0">⇉</span>
          <div class="flex-1 bg-emerald-50 border-2 border-emerald-200 rounded-lg px-3 py-2.5 text-center">
            <p class="text-[11px] font-mono text-emerald-700 mb-0.5">node_nutrition</p>
            <p class="text-[14px] font-bold text-slate-800 mb-0.5">⑤ 营养估算</p>
            <p class="text-[11px] text-slate-500">按过滤输出序取前 3 道</p>
          </div>
        </div>
        <p class="text-[11.5px] text-slate-500 leading-snug mt-3 pt-2.5 border-t border-slate-100">
          <span class="font-semibold text-slate-700">并行语义：</span>④ 与 ⑤ 由 <span class="font-mono text-[11px] text-orange-600">hard_filter</span> 同时 fan-out，在<b>同一 superstep</b> 内并行执行，两条分支都连 END，<b>全部结束后</b>才返回主图进入 compose —— 因此 ⑤ 无法依赖 ④ 的输出，取的是过滤后的前 3 道。
        </p>
      </div>

      <div class="grid grid-cols-3 gap-4 flex-1">
        <div class="bg-white border border-slate-200 rounded-xl p-5 shadow-sm flex flex-col">
          <h3 class="text-[18px] font-bold text-slate-800 mb-3">召回：三路混合与生效条件</h3>
          <div class="space-y-2.5 flex-1">
            <div class="bg-slate-50 rounded-lg px-3.5 py-2.5">
              <div class="flex items-center justify-between mb-1">
                <span class="text-[14px] font-semibold text-slate-800">① 覆盖率召回</span>
                <span class="text-[11px] text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-full px-2.5 py-0.5">恒生效</span>
              </div>
              <p class="text-[12px] text-slate-500 leading-relaxed">按命中食材数量降序排列，是「有什么做什么」这一主场景的基线能力。</p>
            </div>
            <div class="bg-slate-50 rounded-lg px-3.5 py-2.5">
              <div class="flex items-center justify-between mb-1">
                <span class="text-[14px] font-semibold text-slate-800">② 文本召回</span>
                <span class="text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded-full px-2.5 py-0.5">需携带文本</span>
              </div>
              <p class="text-[12px] text-slate-500 leading-relaxed">菜名模糊匹配，并从菜谱正文中解析食材提及，补足「按名字找菜」的场景。</p>
            </div>
            <div class="bg-slate-50 rounded-lg px-3.5 py-2.5">
              <div class="flex items-center justify-between mb-1">
                <span class="text-[14px] font-semibold text-slate-800">③ 向量召回</span>
                <span class="text-[11px] text-rose-700 bg-rose-50 border border-rose-200 rounded-full px-2.5 py-0.5">需 query_text</span>
              </div>
              <p class="text-[12px] text-slate-500 leading-relaxed">用 pgvector 计算相似度取 Top-20，捕捉字面不同但语义相近的菜谱。</p>
            </div>
          </div>
          <p class="text-[12px] text-slate-500 leading-relaxed mt-3 pt-3 border-t border-slate-100">
            三路结果取并集去重，再按固定优先级融合。<span class="font-semibold text-slate-700">诚实说明：</span>纯手选路径不携带文本，因此不触发向量召回，阶段一实际只用到两路。
          </p>
        </div>

        <div class="bg-white border border-slate-200 rounded-xl p-5 shadow-sm flex flex-col">
          <h3 class="text-[18px] font-bold text-slate-800 mb-3">过滤：四个维度命中即剔除</h3>
          <div class="grid grid-cols-2 gap-2.5">
            <div class="bg-red-50 border border-red-200 rounded-lg px-3.5 py-3">
              <p class="text-[14px] font-semibold text-red-700 mb-1">过敏原</p>
              <p class="text-[12px] text-red-600 leading-relaxed">落到数据库布尔运算，绝不降权</p>
            </div>
            <div class="bg-orange-50 border border-orange-200 rounded-lg px-3.5 py-3">
              <p class="text-[14px] font-semibold text-orange-700 mb-1">忌口</p>
              <p class="text-[12px] text-orange-600 leading-relaxed">素食、清真、不吃辣等直接排除</p>
            </div>
            <div class="bg-sky-50 border border-sky-200 rounded-lg px-3.5 py-3">
              <p class="text-[14px] font-semibold text-sky-700 mb-1">难度</p>
              <p class="text-[12px] text-sky-600 leading-relaxed">不高于用户自评的厨艺能力上限</p>
            </div>
            <div class="bg-teal-50 border border-teal-200 rounded-lg px-3.5 py-3">
              <p class="text-[14px] font-semibold text-teal-700 mb-1">设备</p>
              <p class="text-[12px] text-teal-600 leading-relaxed">按家庭厨具做差集，基础工具豁免</p>
            </div>
          </div>
          <div class="space-y-2 mt-3 flex-1">
            <p class="text-[12px] text-slate-500 leading-relaxed">四个维度各自记录 <span class="font-mono text-[11px]">filtered_by</span> 命中计数，前端可逐条重放「这道菜为什么被过滤」。</p>
            <p class="text-[12px] text-slate-500 leading-relaxed">口味上的「不喜欢」走的是降权（−0.5）而不是过滤 —— 不喜欢不等于不能吃，两套语义刻意区分。</p>
            <div class="bg-slate-900 rounded-lg px-3.5 py-3">
              <p class="text-[12px] text-slate-300 leading-relaxed">排序函数的输入集只能是过滤节点的输出集 —— <span class="text-white font-semibold">代码结构本身杜绝「打分后放回」</span>。</p>
            </div>
          </div>
        </div>

        <div class="bg-white border border-slate-200 rounded-xl p-5 shadow-sm flex flex-col">
          <h3 class="text-[18px] font-bold text-slate-800 mb-1">排序：7 因子与结果契约</h3>
          <p class="text-[12px] text-slate-400 font-mono mb-3">权重存于远程配置，可热调而不发版</p>
          <div class="grid grid-cols-4 gap-1.5 mb-3">
            <div class="bg-cyan-50 border border-cyan-200 rounded-md px-1.5 py-1.5 text-center">
              <p class="text-[10px] text-cyan-800">coverage</p><p class="text-[14px] font-bold font-mono text-cyan-700">.30</p><p class="text-[10px] text-emerald-600">生效</p>
            </div>
            <div class="bg-slate-50 border border-slate-200 rounded-md px-1.5 py-1.5 text-center">
              <p class="text-[10px] text-slate-500">expiring</p><p class="text-[14px] font-bold font-mono text-slate-400">.15</p><p class="text-[10px] text-slate-400">未启用</p>
            </div>
            <div class="bg-slate-50 border border-slate-200 rounded-md px-1.5 py-1.5 text-center">
              <p class="text-[10px] text-slate-500">taste</p><p class="text-[14px] font-bold font-mono text-slate-400">.15</p><p class="text-[10px] text-slate-400">未启用</p>
            </div>
            <div class="bg-slate-50 border border-slate-200 rounded-md px-1.5 py-1.5 text-center">
              <p class="text-[10px] text-slate-500">goal</p><p class="text-[14px] font-bold font-mono text-slate-400">.15</p><p class="text-[10px] text-slate-400">未启用</p>
            </div>
            <div class="bg-sky-50 border border-sky-200 rounded-md px-1.5 py-1.5 text-center">
              <p class="text-[10px] text-sky-800">difficulty</p><p class="text-[14px] font-bold font-mono text-sky-700">.10</p><p class="text-[10px] text-emerald-600">生效</p>
            </div>
            <div class="bg-slate-50 border border-slate-200 rounded-md px-1.5 py-1.5 text-center">
              <p class="text-[10px] text-slate-500">history</p><p class="text-[14px] font-bold font-mono text-slate-400">.10</p><p class="text-[10px] text-slate-400">未启用</p>
            </div>
            <div class="bg-slate-50 border border-slate-200 rounded-md px-1.5 py-1.5 text-center">
              <p class="text-[10px] text-slate-500">popularity</p><p class="text-[14px] font-bold font-mono text-slate-400">.05</p><p class="text-[10px] text-slate-400">未启用</p>
            </div>
            <div class="bg-white border border-dashed border-slate-300 rounded-md px-1.5 py-1.5 flex items-center justify-center">
              <p class="text-[10px] text-slate-400 leading-tight text-center">无效权重<br/>摊给 coverage</p>
            </div>
          </div>
          <div class="space-y-1.5 flex-1">
            <p class="text-[12px] text-slate-500 leading-relaxed"><span class="font-semibold text-slate-700">结果分档：</span>按缺失食材数分为「全齐 / 缺 1-2 道 / 缺 3 道以上」三档，缺失过多整条跳过。</p>
            <p class="text-[12px] text-slate-500 leading-relaxed"><span class="font-semibold text-slate-700">只取前 8 条：</span>不足时如实提示「现有食材组合有限，宁缺毋滥」，不填充低分菜谱。</p>
            <p class="text-[12px] text-slate-500 leading-relaxed"><span class="font-semibold text-slate-700">可解释：</span>卡片提供「为什么推荐给你」入口，展开即为 <span class="font-mono text-[11px]">rank_reasons</span>。</p>
          </div>
          <div class="mt-3 bg-amber-50 border border-amber-200 rounded-lg px-3.5 py-2.5">
            <p class="text-[12px] text-amber-800 leading-relaxed">
              <span class="font-semibold">阶段一真实排序口径：</span>实际仅 coverage 与 difficulty 生效，其余因子接口已就位但权重为 0，随阶段二行为数据积累逐项启用。
            </p>
          </div>
        </div>
      </div>

      <div class="mt-3 flex items-center justify-between text-[13px] text-slate-400">
        <span class="font-mono tracking-wider">AI 厨娘 · 智能烹饪助手 · 项目答辩</span>
        <span class="font-mono">11 / 25</span>
      </div>
    </div>
  </div>
`);window.slideDataMap.set(12,`
  <div class="w-[1440px] h-[810px] relative overflow-hidden slide-bg">
    <div class="absolute top-0 left-0 w-full h-[8px] bg-orange-600"></div>
    <div class="w-[1350px] h-[720px] mx-auto my-[45px] relative pt-3 flex flex-col">

      <div class="flex items-center justify-between mb-3">
        <div class="flex items-center gap-4">
          <div class="w-[6px] h-10 bg-orange-600 rounded"></div>
          <div>
            <h2 class="text-[34px] font-bold text-slate-900 leading-tight">LangGraph 主图拓扑（运行期导出）</h2>
            <p class="text-[14px] text-slate-500 mt-0.5">13 个节点 · 24 条边（含 13 条条件边）· 双侧闸门 + 中枢路由 + 汇聚 + 3 个出口</p>
          </div>
        </div>
        <div class="flex gap-2">
          <span class="px-3 py-1.5 bg-slate-50 border border-slate-200 text-slate-600 rounded-full text-[12px] font-medium">实线＝普通边</span>
          <span class="px-3 py-1.5 bg-slate-50 border border-slate-200 text-slate-600 rounded-full text-[12px] font-medium">虚线＝条件边</span>
          <span class="px-3 py-1.5 bg-red-50 border border-red-200 text-red-700 rounded-full text-[12px] font-medium">红＝否决短路</span>
          <span class="px-3 py-1.5 bg-amber-50 border border-amber-200 text-amber-700 rounded-full text-[12px] font-medium">琥珀＝保守模式</span>
        </div>
      </div>

      <div class="bg-white border border-slate-200 rounded-xl shadow-sm px-3 py-2 flex-1 relative overflow-hidden">
        <div class="relative" style="width:1330px;height:452px;">

          <svg width="1330" height="452" class="absolute left-0 top-0" style="pointer-events:none;">
            <defs>
              <marker id="m-s" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6 z" fill="#64748B"/></marker>
              <marker id="m-c" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6 z" fill="#94A3B8"/></marker>
              <marker id="m-r" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6 z" fill="#DC2626"/></marker>
              <marker id="m-a" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6 z" fill="#D97706"/></marker>
              <marker id="m-g" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6 z" fill="#059669"/></marker>
            </defs>

            <path d="M84,250 L98,250" stroke="#64748B" stroke-width="1.6" fill="none" marker-end="url(#m-s)"/>
            <path d="M252,250 L268,250" stroke="#94A3B8" stroke-width="1.6" fill="none" stroke-dasharray="6,4" marker-end="url(#m-c)"/>

            <path d="M185,222 L185,18 L698,18" stroke="#DC2626" stroke-width="1.6" fill="none" stroke-dasharray="6,4" marker-end="url(#m-r)"/>
            <path d="M185,278 L185,440 L1028,440 L1028,396 L1058,396" stroke="#D97706" stroke-width="1.6" fill="none" stroke-dasharray="6,4" marker-end="url(#m-a)"/>

            <path d="M442,250 L460,250" stroke="#94A3B8" stroke-width="1.6" fill="none"/>
            <path d="M460,70 L460,360" stroke="#94A3B8" stroke-width="1.6" fill="none"/>
            <path d="M460,70 L478,70" stroke="#94A3B8" stroke-width="1.6" fill="none" stroke-dasharray="6,4" marker-end="url(#m-c)"/>
            <path d="M460,128 L478,128" stroke="#94A3B8" stroke-width="1.6" fill="none" stroke-dasharray="6,4" marker-end="url(#m-c)"/>
            <path d="M460,186 L478,186" stroke="#94A3B8" stroke-width="1.6" fill="none" stroke-dasharray="6,4" marker-end="url(#m-c)"/>
            <path d="M460,244 L478,244" stroke="#94A3B8" stroke-width="1.6" fill="none" stroke-dasharray="6,4" marker-end="url(#m-c)"/>
            <path d="M460,302 L478,302" stroke="#94A3B8" stroke-width="1.6" fill="none" stroke-dasharray="6,4" marker-end="url(#m-c)"/>
            <path d="M460,360 L478,360" stroke="#94A3B8" stroke-width="1.6" fill="none" stroke-dasharray="6,4" marker-end="url(#m-c)"/>

            <path d="M365,216 L365,42 L698,42" stroke="#DC2626" stroke-width="1.6" fill="none" stroke-dasharray="6,4" marker-end="url(#m-r)"/>

            <path d="M688,70 L708,70" stroke="#64748B" stroke-width="1.6" fill="none"/>
            <path d="M688,128 L708,128" stroke="#64748B" stroke-width="1.6" fill="none"/>
            <path d="M688,186 L708,186" stroke="#64748B" stroke-width="1.6" fill="none"/>
            <path d="M688,244 L708,244" stroke="#64748B" stroke-width="1.6" fill="none"/>
            <path d="M688,302 L708,302" stroke="#64748B" stroke-width="1.6" fill="none"/>
            <path d="M688,360 L708,360" stroke="#64748B" stroke-width="1.6" fill="none"/>
            <path d="M708,70 L708,360" stroke="#64748B" stroke-width="1.6" fill="none"/>
            <path d="M708,250 L724,250" stroke="#64748B" stroke-width="1.6" fill="none" marker-end="url(#m-s)"/>

            <path d="M856,250 L884,250" stroke="#64748B" stroke-width="1.6" fill="none" marker-end="url(#m-s)"/>
            <path d="M1046,250 L1078,250" stroke="#059669" stroke-width="1.8" fill="none" stroke-dasharray="6,4" marker-end="url(#m-g)"/>

            <path d="M966,222 L966,64 L820,64 L820,56" stroke="#DC2626" stroke-width="1.6" fill="none" stroke-dasharray="6,4" marker-end="url(#m-r)"/>
            <path d="M966,278 L966,384 L1058,384" stroke="#D97706" stroke-width="1.6" fill="none" stroke-dasharray="6,4" marker-end="url(#m-a)"/>

            <path d="M1232,250 L1254,250" stroke="#64748B" stroke-width="1.6" fill="none" marker-end="url(#m-s)"/>
            <path d="M940,30 L956,30" stroke="#64748B" stroke-width="1.6" fill="none" marker-end="url(#m-s)"/>
            <path d="M1260,396 L1274,396" stroke="#64748B" stroke-width="1.6" fill="none" marker-end="url(#m-s)"/>
          </svg>

          <div class="absolute text-[12px] text-red-600 font-medium" style="left:188px;top:96px;">hit（含伪科学澄清）</div>
          <div class="absolute text-[12px] text-amber-600 font-medium" style="left:188px;top:340px;">status=UNKNOWN</div>
          <div class="absolute text-[12px] text-slate-500 font-medium" style="left:262px;top:226px;">pass</div>
          <div class="absolute text-[12px] text-red-600 font-medium" style="left:372px;top:22px;">intent=__veto__（双保险）</div>
          <div class="absolute text-[12px] text-slate-400" style="left:462px;top:372px;">← 按 INTENT_ROUTES 字典路由（7 条条件边）</div>
          <div class="absolute text-[12px] text-red-600 font-medium" style="left:866px;top:68px;">hit &amp; block</div>
          <div class="absolute text-[12px] text-emerald-600 font-medium" style="left:1048px;top:228px;">pass</div>
          <div class="absolute text-[12px] text-amber-600 font-medium" style="left:972px;top:328px;">status=UNKNOWN</div>

          <div class="absolute rounded-lg flex items-center justify-center" style="left:6px;top:226px;width:78px;height:48px;background:#1E293B;">
            <span class="text-white text-[11px] font-bold font-mono">__start__</span>
          </div>

          <div class="absolute rounded-lg border-2 border-orange-400 bg-orange-50 flex flex-col items-center justify-center" style="left:100px;top:222px;width:152px;height:56px;">
            <span class="text-[12px] font-mono font-bold text-orange-700">intake_guard</span>
            <span class="text-[11px] text-orange-600">入口闸门 · rule · 500ms</span>
          </div>

          <div class="absolute rounded-lg flex flex-col items-center justify-center" style="left:270px;top:216px;width:172px;height:68px;background:#0E7490;">
            <span class="text-[15px] font-bold text-white font-mono">supervisor</span>
            <span class="text-[11px] text-cyan-100 mt-0.5">意图识别 · llm · 3000ms</span>
            <span class="text-[10px] text-cyan-200 mt-0.5 px-2 py-0.5 rounded-full" style="background:rgba(255,255,255,0.18)">只输出意图标签 · 不选工具</span>
          </div>

          <div class="absolute rounded-lg border border-slate-300 border-l-4 border-l-cyan-700 bg-white flex flex-col items-center justify-center" style="left:480px;top:51px;width:208px;height:38px;">
            <span class="text-[10.5px] font-mono text-slate-700 leading-none mb-1">subgraph_recommend</span><span class="text-[10px] text-slate-500 leading-none">推荐子图 · subgraph · 5000ms</span>
          </div>
          <div class="absolute rounded-lg border border-slate-300 border-l-4 border-l-sky-600 bg-white flex flex-col items-center justify-center" style="left:480px;top:109px;width:208px;height:38px;">
            <span class="text-[10.5px] font-mono text-slate-700 leading-none mb-1">node_free_qa</span><span class="text-[10px] text-slate-500 leading-none">受限问答 · llm · 5000ms</span>
          </div>
          <div class="absolute rounded-lg border border-slate-300 border-l-4 border-l-slate-500 bg-white flex flex-col items-center justify-center" style="left:480px;top:167px;width:208px;height:38px;">
            <span class="text-[10.5px] font-mono text-slate-700 leading-none mb-1">node_inventory_op</span><span class="text-[10px] text-slate-500 leading-none">库存操作 · rule · 1000ms</span>
          </div>
          <div class="absolute rounded-lg border border-slate-300 border-l-4 border-l-slate-500 bg-white flex flex-col items-center justify-center" style="left:480px;top:225px;width:208px;height:38px;">
            <span class="text-[10.5px] font-mono text-slate-700 leading-none mb-1">node_nutrition_query</span><span class="text-[10px] text-slate-500 leading-none">营养查询 · rule · 1000ms</span>
          </div>
          <div class="absolute rounded-lg border border-slate-300 border-l-4 border-l-slate-500 bg-white flex flex-col items-center justify-center" style="left:480px;top:283px;width:208px;height:38px;">
            <span class="text-[10.5px] font-mono text-slate-700 leading-none mb-1">node_cooking_help</span><span class="text-[10px] text-slate-500 leading-none">烹饪求助 · rule · 1000ms</span>
          </div>
          <div class="absolute rounded-lg border border-slate-300 border-l-4 border-l-cyan-700 bg-white flex flex-col items-center justify-center" style="left:480px;top:341px;width:208px;height:38px;">
            <span class="text-[10.5px] font-mono text-slate-700 leading-none mb-1">node_innovation_entry</span><span class="text-[10px] text-slate-500 leading-none">创新入口 · subgraph · 8000ms</span>
          </div>

          <div class="absolute rounded-lg border-2 border-indigo-300 bg-indigo-50 flex flex-col items-center justify-center" style="left:726px;top:226px;width:130px;height:48px;">
            <span class="text-[12px] font-mono font-bold text-indigo-700">compose</span>
            <span class="text-[10px] text-indigo-600">汇总组装 · 1000ms</span>
          </div>

          <div class="absolute rounded-lg border-2 border-orange-400 bg-orange-50 flex flex-col items-center justify-center" style="left:886px;top:222px;width:160px;height:56px;">
            <span class="text-[12px] font-mono font-bold text-orange-700">output_guard</span>
            <span class="text-[11px] text-orange-600">出口闸门 · rule · 500ms</span>
          </div>

          <div class="absolute rounded-lg flex flex-col items-center justify-center" style="left:700px;top:6px;width:240px;height:48px;background:#DC2626;">
            <span class="text-[12px] font-mono font-bold text-white">emit_safety_response</span>
            <span class="text-[10px] text-red-100">一票否决 / 澄清出口 · 仅 6 个安全字段</span>
          </div>
          <div class="absolute rounded-full flex items-center justify-center border-2 border-slate-400 bg-white" style="left:958px;top:14px;width:62px;height:32px;">
            <span class="text-[11px] font-bold font-mono text-slate-600">__end__</span>
          </div>

          <div class="absolute rounded-lg border-2 border-emerald-400 bg-emerald-50 flex flex-col items-center justify-center" style="left:1080px;top:222px;width:152px;height:56px;">
            <span class="text-[12px] font-mono font-bold text-emerald-700">finalize</span>
            <span class="text-[10px] text-emerald-600">trace 落库 + 终响应</span>
          </div>
          <div class="absolute rounded-full flex items-center justify-center border-2 border-slate-400 bg-white" style="left:1256px;top:234px;width:66px;height:32px;">
            <span class="text-[11px] font-bold font-mono text-slate-600">__end__</span>
          </div>

          <div class="absolute rounded-lg border-2 border-amber-400 bg-amber-50 flex flex-col items-center justify-center" style="left:1060px;top:372px;width:200px;height:48px;">
            <span class="text-[12px] font-mono font-bold text-amber-700">safe_mode_handler</span>
            <span class="text-[10px] text-amber-600">保守模式出口 · TXT-G06 固定话术</span>
          </div>
          <div class="absolute rounded-full flex items-center justify-center border-2 border-slate-400 bg-white" style="left:1276px;top:380px;width:50px;height:32px;">
            <span class="text-[10px] font-bold font-mono text-slate-600">__end__</span>
          </div>
        </div>
      </div>

      <div class="mt-3 grid grid-cols-5 gap-2.5">
        <div class="bg-white border border-slate-200 border-t-2 border-t-orange-500 rounded-lg px-3 py-2 shadow-sm">
          <p class="text-[12px] font-bold text-slate-800 mb-0.5">END 入边仅 3 条</p>
          <p class="text-[11px] text-slate-500 leading-snug">全部来自三个出口，无绕过闸门直达 END 的路径</p>
        </div>
        <div class="bg-white border border-slate-200 border-t-2 border-t-orange-500 rounded-lg px-3 py-2 shadow-sm">
          <p class="text-[12px] font-bold text-slate-800 mb-0.5">闸门与 END 无直连</p>
          <p class="text-[11px] text-slate-500 leading-snug">intake_guard 与 END 无直边，否决必经短路出口</p>
        </div>
        <div class="bg-white border border-slate-200 border-t-2 border-t-orange-500 rounded-lg px-3 py-2 shadow-sm">
          <p class="text-[12px] font-bold text-slate-800 mb-0.5">条件边白名单闭合</p>
          <p class="text-[11px] text-slate-500 leading-snug">13 条条件边均显式声明目标白名单，越界编译期报错</p>
        </div>
        <div class="bg-white border border-slate-200 border-t-2 border-t-orange-500 rounded-lg px-3 py-2 shadow-sm">
          <p class="text-[12px] font-bold text-slate-800 mb-0.5">全节点可达无死点</p>
          <p class="text-[11px] text-slate-500 leading-snug">13 个节点从 START 全部可达，无出度为 0 的死节点</p>
        </div>
        <div class="bg-white border border-slate-200 border-t-2 border-t-orange-500 rounded-lg px-3 py-2 shadow-sm">
          <p class="text-[12px] font-bold text-slate-800 mb-0.5">出口闸门不可绕过</p>
          <p class="text-[11px] text-slate-500 leading-snug">output_guard 位于 compose 之后、三出口之前</p>
        </div>
      </div>

      <div class="mt-2.5 flex items-center justify-between text-[12px] text-slate-400">
        <span class="font-mono tracking-wider">AI 厨娘 · 智能烹饪助手 · 项目答辩</span>
        <span class="font-mono">12 / 25</span>
      </div>
    </div>
  </div>
`);window.slideDataMap.set(13,`
  <div class="w-[1440px] h-[810px] relative overflow-hidden slide-bg">
    <div class="absolute top-0 left-0 w-full h-[8px] bg-orange-600"></div>
    <div class="w-[1350px] h-[720px] mx-auto my-[45px] relative pt-3 flex flex-col">

      <div class="flex items-center justify-between mb-3">
        <div class="flex items-center gap-4">
          <div class="w-[6px] h-10 bg-orange-600 rounded"></div>
          <div>
            <h2 class="text-[34px] font-bold text-slate-900 leading-tight">LangGraph 路由机制与两张子图</h2>
            <p class="text-[14px] text-slate-500 mt-0.5">3 个路由函数（确定性、零 LLM 参与）· INTENT_ROUTES 10 类意图 · 推荐子图 5 节点 / 创新子图 4 节点</p>
          </div>
        </div>
        <span class="px-3.5 py-1.5 bg-cyan-50 border border-cyan-200 text-cyan-800 rounded-full text-[12px] font-medium">三张 StateGraph 均裸编译 · 无 checkpointer / 无 interrupt</span>
      </div>

      <div class="flex gap-4 flex-1">
        <div class="w-[47%] flex flex-col gap-3">
          <div class="bg-white border border-slate-200 rounded-xl p-3.5 shadow-sm">
            <h3 class="text-[16px] font-bold text-slate-800 mb-2">三个路由函数 · 挂载点 / 白名单 / 判定</h3>
            <div class="space-y-1.5">
              <div class="bg-slate-50 rounded-lg px-3 py-1.5">
                <div class="flex items-center justify-between mb-0.5">
                  <span class="text-[11.5px] font-mono font-bold text-cyan-700">route_after_intake_guard</span>
                  <span class="text-[10.5px] text-slate-400">挂在 intake_guard</span>
                </div>
                <p class="text-[11px] text-slate-600 leading-snug">UNKNOWN→保守模式 ｜ hit→否决出口 ｜ 否则放行 supervisor</p>
              </div>
              <div class="bg-slate-50 rounded-lg px-3 py-1.5">
                <div class="flex items-center justify-between mb-0.5">
                  <span class="text-[11.5px] font-mono font-bold text-cyan-700">route_after_supervisor</span>
                  <span class="text-[10.5px] text-slate-400">挂在 supervisor</span>
                </div>
                <p class="text-[11px] text-slate-600 leading-snug">intent==__veto__→否决出口 ｜ 否则查 INTENT_ROUTES，未命中兜底 node_free_qa</p>
              </div>
              <div class="bg-slate-50 rounded-lg px-3 py-1.5">
                <div class="flex items-center justify-between mb-0.5">
                  <span class="text-[11.5px] font-mono font-bold text-cyan-700">route_after_output_guard</span>
                  <span class="text-[10.5px] text-slate-400">挂在 output_guard</span>
                </div>
                <p class="text-[11px] text-slate-600 leading-snug">UNKNOWN→保守模式 ｜ hit&amp;&amp;block→否决 ｜ hit&amp;&amp;!block→放行 finalize</p>
              </div>
            </div>
            <p class="text-[11px] text-slate-500 leading-snug mt-2 pt-2 border-t border-slate-100">
              <span class="font-semibold text-slate-700">关键设计点：</span>LLM 只输出意图标签，「意图 → 节点」映射由代码字典固定，模型无权决定调用哪个工具。
            </p>
          </div>

          <div class="bg-white border border-slate-200 rounded-xl p-3.5 shadow-sm flex-1 flex flex-col">
            <div class="flex items-center justify-between mb-2">
              <h3 class="text-[16px] font-bold text-slate-800">INTENT_ROUTES 全量映射</h3>
              <span class="text-[10.5px] text-slate-400 font-mono">10 类 · 无遗漏 / 无多余</span>
            </div>
            <div class="grid grid-cols-2 gap-x-3 gap-y-[5px] flex-1">
              <div class="flex items-center justify-between bg-slate-50 rounded px-2.5 py-1.5">
                <span class="text-[10.5px] font-mono text-slate-700">recommend_by_ingredients</span><span class="text-[10px] font-mono text-cyan-700">→ recommend</span>
              </div>
              <div class="flex items-center justify-between bg-slate-50 rounded px-2.5 py-1.5">
                <span class="text-[10.5px] font-mono text-slate-700">search_recipe</span><span class="text-[10px] font-mono text-cyan-700">→ recommend</span>
              </div>
              <div class="flex items-center justify-between bg-cyan-50 rounded px-2.5 py-1.5">
                <span class="text-[10.5px] font-mono text-cyan-800">composite_recommend_nutrition</span><span class="text-[10px] font-mono text-cyan-700">→ recommend</span>
              </div>
              <div class="flex items-center justify-between bg-slate-50 rounded px-2.5 py-1.5">
                <span class="text-[10.5px] font-mono text-slate-700">nutrition_query</span><span class="text-[10px] font-mono text-slate-600">→ nutrition_query</span>
              </div>
              <div class="flex items-center justify-between bg-slate-50 rounded px-2.5 py-1.5">
                <span class="text-[10.5px] font-mono text-slate-700">cooking_help</span><span class="text-[10px] font-mono text-slate-600">→ cooking_help</span>
              </div>
              <div class="flex items-center justify-between bg-slate-50 rounded px-2.5 py-1.5">
                <span class="text-[10.5px] font-mono text-slate-700">inventory_op</span><span class="text-[10px] font-mono text-slate-600">→ inventory_op</span>
              </div>
              <div class="flex items-center justify-between bg-slate-50 rounded px-2.5 py-1.5">
                <span class="text-[10.5px] font-mono text-slate-700">innovation</span><span class="text-[10px] font-mono text-cyan-700">→ innovation_entry</span>
              </div>
              <div class="flex items-center justify-between bg-slate-50 rounded px-2.5 py-1.5">
                <span class="text-[10.5px] font-mono text-slate-700">photo_recognize</span><span class="text-[10px] font-mono text-slate-600">→ node_free_qa</span>
              </div>
              <div class="flex items-center justify-between bg-slate-50 rounded px-2.5 py-1.5">
                <span class="text-[10.5px] font-mono text-slate-700">free_qa</span><span class="text-[10px] font-mono text-slate-600">→ node_free_qa</span>
              </div>
              <div class="flex items-center justify-between bg-slate-50 rounded px-2.5 py-1.5">
                <span class="text-[10.5px] font-mono text-slate-700">smalltalk_or_out_of_scope</span><span class="text-[10px] font-mono text-slate-600">→ node_free_qa</span>
              </div>
            </div>
            <div class="mt-2 bg-amber-50 border border-amber-200 rounded-lg px-3 py-1.5">
              <p class="text-[11px] text-amber-800 leading-snug">
                <span class="font-semibold">LLM 降级：</span>捕获 LLMError 或 JSON 解析失败 → <span class="font-mono text-[10.5px]">_keyword_fallback</span> 关键词兜底（覆盖复合意图与创新意图），trace span 标 <span class="font-mono text-[10.5px]">degraded</span>。
              </p>
            </div>
          </div>
        </div>

        <div class="w-[53%] flex flex-col gap-3">
          <div class="bg-white border border-slate-200 rounded-xl p-3.5 shadow-sm">
            <div class="flex items-center justify-between mb-2">
              <h3 class="text-[16px] font-bold text-slate-800">推荐子图 <span class="font-mono text-cyan-700 text-[14px]">subgraph_recommend</span></h3>
              <span class="text-[10.5px] px-2.5 py-1 bg-cyan-50 border border-cyan-200 text-cyan-800 rounded-full">5 节点 · 已注册进主图 · recursion_limit 40</span>
            </div>
            <div class="relative" style="width:700px;height:118px;">
              <svg width="700" height="118" class="absolute left-0 top-0">
                <defs><marker id="sg-a" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6 z" fill="#64748B"/></marker></defs>
                <path d="M58,50 L70,50" stroke="#64748B" stroke-width="1.5" fill="none" marker-end="url(#sg-a)"/>
                <path d="M184,50 L196,50" stroke="#64748B" stroke-width="1.5" fill="none" marker-end="url(#sg-a)"/>
                <path d="M310,50 L322,50" stroke="#64748B" stroke-width="1.5" fill="none" marker-end="url(#sg-a)"/>
                <path d="M428,50 L446,50" stroke="#64748B" stroke-width="1.5" fill="none"/>
                <path d="M446,24 L446,88" stroke="#64748B" stroke-width="1.5" fill="none"/>
                <path d="M446,24 L460,24" stroke="#64748B" stroke-width="1.5" fill="none" marker-end="url(#sg-a)"/>
                <path d="M446,88 L460,88" stroke="#64748B" stroke-width="1.5" fill="none" marker-end="url(#sg-a)"/>
                <path d="M572,24 L590,24" stroke="#64748B" stroke-width="1.5" fill="none"/>
                <path d="M572,88 L590,88" stroke="#64748B" stroke-width="1.5" fill="none"/>
                <path d="M590,24 L590,88" stroke="#64748B" stroke-width="1.5" fill="none"/>
                <path d="M590,50 L612,50" stroke="#64748B" stroke-width="1.5" fill="none" marker-end="url(#sg-a)"/>
              </svg>
              <div class="absolute rounded-md flex items-center justify-center" style="left:0px;top:36px;width:58px;height:28px;background:#1E293B;">
                <span class="text-white text-[9.5px] font-bold font-mono">__start__</span>
              </div>
              <div class="absolute rounded-md border-2 border-cyan-300 bg-cyan-50 flex flex-col items-center justify-center" style="left:72px;top:30px;width:112px;height:40px;">
                <span class="text-[9.5px] font-mono text-cyan-700 leading-none mb-1">assemble_context</span>
                <span class="text-[10px] text-slate-600 leading-none">食材名 / 别名 → ID</span>
              </div>
              <div class="absolute rounded-md border-2 border-sky-300 bg-sky-50 flex flex-col items-center justify-center" style="left:198px;top:30px;width:112px;height:40px;">
                <span class="text-[9.5px] font-mono text-sky-700 leading-none mb-1">recipe_retrieve</span>
                <span class="text-[10px] text-slate-600 leading-none">混合召回 ≤200</span>
              </div>
              <div class="absolute rounded-md border-2 border-orange-300 bg-orange-50 flex flex-col items-center justify-center" style="left:324px;top:30px;width:104px;height:40px;">
                <span class="text-[9.5px] font-mono text-orange-700 leading-none mb-1">hard_filter</span>
                <span class="text-[10px] text-slate-600 leading-none">布尔硬过滤 SQL</span>
              </div>
              <div class="absolute rounded-md border-2 border-indigo-300 bg-indigo-50 flex flex-col items-center justify-center" style="left:462px;top:6px;width:110px;height:36px;">
                <span class="text-[9.5px] font-mono text-indigo-700 leading-none mb-1">recipe_rank</span>
                <span class="text-[10px] text-slate-600 leading-none">7 因子 → Top 8</span>
              </div>
              <div class="absolute rounded-md border-2 border-emerald-300 bg-emerald-50 flex flex-col items-center justify-center" style="left:462px;top:70px;width:110px;height:36px;">
                <span class="text-[9.5px] font-mono text-emerald-700 leading-none mb-1">node_nutrition</span>
                <span class="text-[10px] text-slate-600 leading-none">前 3 道并行估算</span>
              </div>
              <div class="absolute rounded-md flex items-center justify-center border-2 border-slate-300 bg-white" style="left:614px;top:36px;width:60px;height:28px;">
                <span class="text-[9.5px] font-bold font-mono text-slate-600">__end__</span>
              </div>
              <div class="absolute text-[10px] text-slate-400" style="left:432px;top:52px;">并行</div>
            </div>
            <div class="grid grid-cols-2 gap-x-3 gap-y-1 mt-1">
              <p class="text-[11px] text-slate-600 leading-snug"><span class="font-semibold text-slate-700">并行语义：</span>hard_filter 同时 fan-out 两条边，二者在<b>同一 superstep</b> 内并行，都连 END，全部结束后才返回主图 compose。</p>
              <p class="text-[11px] text-slate-600 leading-snug"><span class="font-semibold text-slate-700">并行约束：</span>营养节点无法依赖排序输出，按过滤输出序取前 3 道估算（与最终 Top 重合度高）。</p>
              <p class="text-[11px] text-slate-600 leading-snug"><span class="font-semibold text-slate-700">召回双分支：</span>RETRIEVAL_VECTOR 开关默认 on → pgvector raw SQL / embedding_json 点积，兜底降级不抛错。</p>
              <p class="text-[11px] text-slate-600 leading-snug"><span class="font-semibold text-slate-700">反馈接线：</span>user_id 存在时加载 dislike 惩罚 −0.5 传入 weighted_rank；无 user_id 排序不变。</p>
            </div>
          </div>

          <div class="bg-white border border-slate-200 rounded-xl p-3.5 shadow-sm">
            <div class="flex items-center justify-between mb-2">
              <h3 class="text-[16px] font-bold text-slate-800">创新子图 <span class="font-mono text-orange-600 text-[14px]">innovation</span></h3>
              <span class="text-[10.5px] px-2.5 py-1 bg-orange-50 border border-orange-200 text-orange-700 rounded-full">4 节点 · 纯线性 · 未注册进主图</span>
            </div>
            <div class="relative" style="width:700px;height:76px;">
              <svg width="700" height="76" class="absolute left-0 top-0">
                <defs><marker id="ig-a" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6 z" fill="#64748B"/></marker></defs>
                <path d="M58,38 L70,38" stroke="#64748B" stroke-width="1.5" fill="none" marker-end="url(#ig-a)"/>
                <path d="M208,38 L220,38" stroke="#64748B" stroke-width="1.5" fill="none" marker-end="url(#ig-a)"/>
                <path d="M372,38 L384,38" stroke="#64748B" stroke-width="1.5" fill="none" marker-end="url(#ig-a)"/>
                <path d="M532,38 L544,38" stroke="#64748B" stroke-width="1.5" fill="none" marker-end="url(#ig-a)"/>
              </svg>
              <div class="absolute rounded-md flex items-center justify-center" style="left:0px;top:24px;width:58px;height:28px;background:#1E293B;">
                <span class="text-white text-[9.5px] font-bold font-mono">__start__</span>
              </div>
              <div class="absolute rounded-md border-2 border-red-300 bg-red-50 flex flex-col items-center justify-center" style="left:72px;top:20px;width:136px;height:36px;">
                <span class="text-[9.5px] font-mono text-red-700 leading-none mb-1">innovation_precheck</span>
                <span class="text-[10px] text-red-600 leading-none">🔴 安全前置红线</span>
              </div>
              <div class="absolute rounded-md border border-slate-300 bg-white flex flex-col items-center justify-center" style="left:222px;top:20px;width:150px;height:36px;">
                <span class="text-[9.5px] font-mono text-slate-700 leading-none mb-1">innovation_property_match</span>
                <span class="text-[10px] text-slate-500 leading-none">食材五属性查表</span>
              </div>
              <div class="absolute rounded-md border-2 border-red-300 bg-red-50 flex flex-col items-center justify-center" style="left:386px;top:20px;width:146px;height:36px;">
                <span class="text-[9.5px] font-mono text-red-700 leading-none mb-1">innovation_pairing_check</span>
                <span class="text-[10px] text-red-600 leading-none">🔴 搭配结论必须查表</span>
              </div>
              <div class="absolute rounded-md border border-slate-300 bg-white flex flex-col items-center justify-center" style="left:544px;top:20px;width:136px;height:36px;">
                <span class="text-[9.5px] font-mono text-slate-700 leading-none mb-1">innovation_generate</span>
                <span class="text-[10px] text-slate-500 leading-none">受约束生成 + 落库</span>
              </div>
            </div>
            <div class="space-y-0.5 mt-0.5">
              <p class="text-[11px] text-slate-600 leading-snug"><span class="font-semibold text-slate-700">非 LangGraph 子图：</span>它不是主图的子图节点，而是被命令式调用 —— entry 节点 → run_innovation_precheck() + run_innovation_generate() → invoke 子图；同一组函数也被 API 层直接调用，共 <b>3 个调用入口</b>。</p>
              <p class="text-[11px] text-slate-600 leading-snug"><span class="font-semibold text-slate-700">precheck 红线：</span>食材逐个过风控扫描（避免安全食材拼接误伤组合规则）→ 过敏原交集非空直接拒绝 → 特殊人群 + 高危食材拒绝 → taboo 命中拒绝；<b>UNKNOWN / 查表异常一律保守拦截（宁拦不放）</b>。</p>
              <p class="text-[11px] text-slate-600 leading-snug"><span class="font-semibold text-slate-700">generation 约束：</span>用量 100% 量化（禁「适量 / 少许」）、步骤含时长字段 → 违例重试一次 → 再违例降级本地模板；LLM 硬超时 80.0s；blocked=True 后三个下游节点直接返回 status="skipped"。</p>
            </div>
          </div>

          <div class="bg-slate-900 rounded-xl p-3.5 shadow-sm flex-1">
            <h3 class="text-[15px] font-bold text-white mb-1.5">父子图状态隔离（关键工程约束 · 源码明确记载「已实测踩坑」）</h3>
            <div class="flex gap-2 mb-1.5">
              <span class="px-2.5 py-1 bg-white/10 border border-white/15 rounded-md text-[10.5px] font-mono text-slate-200">主图 CookingState.trace</span>
              <span class="px-2.5 py-1 bg-white/10 border border-white/15 rounded-md text-[10.5px] font-mono text-slate-200">推荐子图 RecommendSubgraphState.sub_trace</span>
              <span class="px-2.5 py-1 bg-white/10 border border-white/15 rounded-md text-[10.5px] font-mono text-slate-200">创新子图 InnovationState.sub_trace</span>
            </div>
            <p class="text-[11px] text-slate-300 leading-snug">
              <b>原因：</b>若子图复用同名 trace 通道，子图会把继承自主图的 span 原样写回，再经主图 <span class="font-mono text-[10.5px]">operator.add</span> 累加 → trace 重复。
              <b class="text-emerald-400">运行期验证：</b>一次正常推荐落库 11 行 trace，无重复 span，隔离机制生效。
            </p>
          </div>
        </div>
      </div>

      <div class="mt-2.5 flex items-center justify-between text-[12px] text-slate-400">
        <span class="font-mono tracking-wider">AI 厨娘 · 智能烹饪助手 · 项目答辩</span>
        <span class="font-mono">13 / 25</span>
      </div>
    </div>
  </div>
`);window.slideDataMap.set(14,`
  <div class="w-[1440px] h-[810px] relative overflow-hidden slide-bg">
    <div class="absolute top-0 left-0 w-full h-[8px] bg-orange-600"></div>
    <div class="w-[1350px] h-[720px] mx-auto my-[45px] relative pt-3 flex flex-col">

      <div class="flex items-center justify-between mb-3">
        <div class="flex items-center gap-4">
          <div class="w-[6px] h-10 bg-orange-600 rounded"></div>
          <div>
            <h2 class="text-[34px] font-bold text-slate-900 leading-tight">图结构运行期校验与自检发现</h2>
            <p class="text-[14px] text-slate-500 mt-0.5">编译并导出拓扑 + 真实调用链路埋点验证 · 图结构单测 18 passed · 同步产出 9 项结构性发现</p>
          </div>
        </div>
        <div class="flex gap-2">
          <span class="px-3.5 py-1.5 bg-emerald-50 border border-emerald-200 text-emerald-700 rounded-full text-[12px] font-medium">拓扑红线全部成立</span>
          <span class="px-3.5 py-1.5 bg-emerald-50 border border-emerald-200 text-emerald-700 rounded-full text-[12px] font-medium">18 passed</span>
          <span class="px-3.5 py-1.5 bg-amber-50 border border-amber-200 text-amber-700 rounded-full text-[12px] font-medium">9 项发现已登记</span>
        </div>
      </div>

      <div class="grid grid-cols-3 gap-3.5 mb-3">
        <div class="bg-white border border-slate-200 border-t-4 border-t-emerald-500 rounded-xl p-3.5 shadow-sm">
          <div class="flex items-center justify-between mb-1.5">
            <span class="text-[12.5px] font-mono font-bold text-emerald-700">finalize</span>
            <span class="text-[10.5px] px-2 py-0.5 bg-emerald-50 border border-emerald-200 text-emerald-700 rounded-full">正常路径出口</span>
          </div>
          <p class="text-[11px] text-slate-500 mb-1">触发：正常通过双侧闸门</p>
          <p class="text-[11px] text-slate-600 leading-snug mb-1"><span class="font-semibold text-slate-700">响应：</span>request_id / results / filtered_by / qa_answer / notice / partial_failures / disclaimer_id / trace_id</p>
          <p class="text-[11px] text-slate-600 leading-snug"><span class="font-semibold text-slate-700">取证：</span>全量 span + 自身 span</p>
        </div>

        <div class="bg-white border border-slate-200 border-t-4 border-t-red-500 rounded-xl p-3.5 shadow-sm">
          <div class="flex items-center justify-between mb-1.5">
            <span class="text-[12.5px] font-mono font-bold text-red-700">emit_safety_response</span>
            <span class="text-[10.5px] px-2 py-0.5 bg-red-50 border border-red-200 text-red-700 rounded-full">否决 / 澄清出口</span>
          </div>
          <p class="text-[11px] text-slate-500 mb-1">触发：入口 hit（含伪科学 block=false 的澄清）或出口 hit &amp;&amp; block</p>
          <p class="text-[11px] text-slate-600 leading-snug mb-1"><span class="font-semibold text-slate-700">响应：</span><b>仅 6 个安全字段</b>，绝不含 results / candidates / nutrition</p>
          <p class="text-[11px] text-slate-600 leading-snug"><span class="font-semibold text-slate-700">取证：</span>为缺失业务节点补 not_executed，output_guard 与 finalize 补 skipped_by_veto，并写 risk_log</p>
        </div>

        <div class="bg-white border border-slate-200 border-t-4 border-t-amber-500 rounded-xl p-3.5 shadow-sm">
          <div class="flex items-center justify-between mb-1.5">
            <span class="text-[12.5px] font-mono font-bold text-amber-700">safe_mode_handler</span>
            <span class="text-[10.5px] px-2 py-0.5 bg-amber-50 border border-amber-200 text-amber-700 rounded-full">保守模式出口</span>
          </div>
          <p class="text-[11px] text-slate-500 mb-1">触发：任一闸门 status=UNKNOWN</p>
          <p class="text-[11px] text-slate-600 leading-snug mb-1"><span class="font-semibold text-slate-700">响应：</span>safe_mode=true + TXT-G06 固定话术</p>
          <p class="text-[11px] text-slate-600 leading-snug"><span class="font-semibold text-slate-700">取证：</span>业务节点与 output_guard 补 not_executed，并写 risk_log(action="safe_mode")</p>
        </div>
      </div>

      <div class="flex gap-3.5 flex-1">
        <div class="w-[56%] bg-white border border-slate-200 rounded-xl p-3.5 shadow-sm flex flex-col">
          <div class="flex items-center justify-between mb-2">
            <h3 class="text-[16px] font-bold text-slate-800">结构健康度小结</h3>
            <span class="text-[10.5px] text-slate-400 font-mono">✅ 成立 ／ ⚠️ 部分 ／ ❌ 未落地</span>
          </div>
          <div class="space-y-[5px] flex-1">
            <div class="flex items-start gap-2 bg-slate-50 rounded-lg px-3 py-[7px]">
              <span class="text-[11.5px] leading-snug">✅</span><span class="text-[11.5px] font-semibold text-slate-700 w-[96px] flex-shrink-0">拓扑红线</span>
              <span class="text-[11.5px] text-slate-600 leading-snug">全部成立：无绕闸路径、无直连 END、全节点可达、白名单闭合</span>
            </div>
            <div class="flex items-start gap-2 bg-slate-50 rounded-lg px-3 py-[7px]">
              <span class="text-[11.5px] leading-snug">✅</span><span class="text-[11.5px] font-semibold text-slate-700 w-[96px] flex-shrink-0">可测试性</span>
              <span class="text-[11.5px] text-slate-600 leading-snug">图结构断言已落单测（关键节点 / END 入边 / 否决体纯净），18 passed</span>
            </div>
            <div class="flex items-start gap-2 bg-slate-50 rounded-lg px-3 py-[7px]">
              <span class="text-[11.5px] leading-snug">✅</span><span class="text-[11.5px] font-semibold text-slate-700 w-[96px] flex-shrink-0">状态隔离</span>
              <span class="text-[11.5px] text-slate-600 leading-snug">子图 sub_trace 隔离有效，一次推荐落库 11 行 trace 无重复</span>
            </div>
            <div class="flex items-start gap-2 bg-slate-50 rounded-lg px-3 py-[7px]">
              <span class="text-[11.5px] leading-snug">⚠️</span><span class="text-[11.5px] font-semibold text-slate-700 w-[96px] flex-shrink-0">可插拔 NFR-4.1</span>
              <span class="text-[11.5px] text-slate-600 leading-snug">仅节点实现可插拔，新增节点仍需手改 main_graph.py 的边与白名单</span>
            </div>
            <div class="flex items-start gap-2 bg-rose-50 border border-rose-100 rounded-lg px-3 py-[7px]">
              <span class="text-[11.5px] leading-snug">❌</span><span class="text-[11.5px] font-semibold text-rose-700 w-[96px] flex-shrink-0">超时治理</span>
              <span class="text-[11.5px] text-rose-700/90 leading-snug">注册表 timeout_ms 未接入执行，超时与降级矩阵未落地</span>
            </div>
            <div class="flex items-start gap-2 bg-slate-50 rounded-lg px-3 py-[7px]">
              <span class="text-[11.5px] leading-snug">⚠️</span><span class="text-[11.5px] font-semibold text-slate-700 w-[96px] flex-shrink-0">取证完整性</span>
              <span class="text-[11.5px] text-slate-600 leading-snug">node_innovation_entry 缺 not_executed 补标，否决 trace 取证有缺口</span>
            </div>
            <div class="flex items-start gap-2 bg-slate-50 rounded-lg px-3 py-[7px]">
              <span class="text-[11.5px] leading-snug">⚠️</span><span class="text-[11.5px] font-semibold text-slate-700 w-[96px] flex-shrink-0">trace 一致性</span>
              <span class="text-[11.5px] text-slate-600 leading-snug">创新链路自生成 trace_id，同一请求被拆成两个 thread_id</span>
            </div>
            <div class="flex items-start gap-2 bg-slate-50 rounded-lg px-3 py-[7px]">
              <span class="text-[11.5px] leading-snug">⚠️</span><span class="text-[11.5px] font-semibold text-slate-700 w-[96px] flex-shrink-0">冗余执行</span>
              <span class="text-[11.5px] text-slate-600 leading-snug">创新主图路径上 precheck 被重复执行 3 轮</span>
            </div>
            <div class="flex items-start gap-2 bg-slate-50 rounded-lg px-3 py-[7px]">
              <span class="text-[11.5px] leading-snug">⚠️</span><span class="text-[11.5px] font-semibold text-slate-700 w-[96px] flex-shrink-0">文档一致性</span>
              <span class="text-[11.5px] text-slate-600 leading-snug">设计文档与实现存在多处漂移（子图清单 / checkpointer / 意图类数）</span>
            </div>
          </div>
        </div>

        <div class="w-[44%] flex flex-col gap-3">
          <div class="bg-white border border-slate-200 rounded-xl p-3.5 shadow-sm flex-1">
            <div class="flex items-center justify-between mb-2">
              <h3 class="text-[16px] font-bold text-slate-800">9 项自检发现 · 按修复优先级</h3>
              <span class="text-[10.5px] text-slate-400 font-mono">均为运行期实测确认</span>
            </div>
            <div class="space-y-[6px]">
              <div class="bg-red-50 border-l-4 border-l-red-500 rounded-lg px-3 py-1.5">
                <p class="text-[12px] font-bold text-red-700 mb-0.5">P0 · BUSINESS_NODE_NAMES 追加未生效</p>
                <p class="text-[11px] text-red-700/90 leading-snug">对模块自身命名空间重绑定（import 是值拷贝），common 与 guards 的清单都不受影响 → 否决 trace 漏补该节点；改动量极小但直接影响取证链完整性</p>
              </div>
              <div class="bg-amber-50 border-l-4 border-l-amber-500 rounded-lg px-3 py-1.5">
                <p class="text-[12px] font-bold text-amber-700 mb-0.5">P1 · 创新路径 precheck 重复执行 3 次</p>
                <p class="text-[11px] text-amber-700/90 leading-snug">主图节点 → generate 内部 → 子图节点各跑一遍，纯浪费 DB 往返与规则匹配（功能无错，延迟与负载被放大）</p>
              </div>
              <div class="bg-amber-50 border-l-4 border-l-amber-500 rounded-lg px-3 py-1.5">
                <p class="text-[12px] font-bold text-amber-700 mb-0.5">P1 · 创新子图 trace_id 断裂</p>
                <p class="text-[11px] text-amber-700/90 leading-snug">子图自生成 trace_id 与主图不同 → 按 thread_id 做会话级回放会断裂（按 request_id 查询仍可命中）</p>
              </div>
              <div class="bg-sky-50 border-l-4 border-l-sky-500 rounded-lg px-3 py-1.5">
                <p class="text-[12px] font-bold text-sky-700 mb-0.5">P2 · 注册表 timeout_ms / forms 从未被消费</p>
                <p class="text-[11px] text-sky-700/90 leading-snug">全仓库零读取点 → 超时矩阵未强制执行，声明与实际约束能力不一致，易被误读为已实现</p>
              </div>
              <div class="bg-slate-50 border-l-4 border-l-slate-400 rounded-lg px-3 py-1.5">
                <p class="text-[12px] font-bold text-slate-700 mb-0.5">P3 · 5 项文档与实现漂移</p>
                <p class="text-[11px] text-slate-600 leading-snug">state.safe_mode 只写不读 · 三图均无 checkpointer / interrupt · 设计文档描述的子图大部分不存在 · 若干 docstring 与实现不一致 · 否决 trace 中包装节点未补标</p>
              </div>
            </div>
          </div>

          <div class="bg-slate-900 rounded-xl p-3.5 shadow-sm">
            <h3 class="text-[14px] font-bold text-white mb-1.5">两个运行期取证案例</h3>
            <p class="text-[11px] text-slate-300 leading-snug mb-1">
              <span class="font-mono text-red-300">一票否决</span>　「木耳泡一晚上明天炒行吗」→ 落库 <b class="text-white">15 行</b> trace：业务节点全为 not_executed，响应键恰为 6 个安全字段，无业务字段泄漏。
            </p>
            <p class="text-[11px] text-slate-300 leading-snug">
              <span class="font-mono text-amber-300">伪科学澄清</span>　「豆腐和菠菜一起吃会相克吗」→ 走同一出口但 blocked=false、risk=PS-001 → 返回<b class="text-white">科普澄清</b>而非拦截。
            </p>
          </div>
        </div>
      </div>

      <div class="mt-2.5 flex items-center justify-between text-[12px] text-slate-400">
        <span class="font-mono tracking-wider">AI 厨娘 · 智能烹饪助手 · 项目答辩</span>
        <span class="font-mono">14 / 25</span>
      </div>
    </div>
  </div>
`);window.slideDataMap.set(15,`
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
        <span class="font-mono">15 / 25</span>
      </div>
    </div>
  </div>
`);window.slideDataMap.set(16,`
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
`);window.slideDataMap.set(17,`
  <div class="w-[1440px] h-[810px] relative overflow-hidden slide-bg">
    <div class="absolute top-0 left-0 w-full h-[8px] bg-cyan-700"></div>
    <div class="w-[1350px] h-[720px] mx-auto my-[45px] relative pt-4 flex flex-col">

      <div class="flex items-center gap-4 mb-5">
        <div class="w-[6px] h-[42px] bg-cyan-700 rounded"></div>
        <div>
          <h2 class="text-[36px] font-bold text-slate-900 leading-tight">精彩代码① 三路召回与布尔硬过滤</h2>
          <p class="text-[15px] text-slate-500 mt-1">过敏原硬过滤为什么必须是布尔运算，而不是「降权」—— 一段代码讲清设计取舍</p>
        </div>
      </div>

      <div class="flex gap-5 flex-1">
        <div class="w-[63%] bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden flex flex-col">
          <div class="bg-slate-50 border-b border-slate-200 px-5 py-2.5 flex items-center justify-between">
            <div class="flex items-center gap-2.5">
              <span class="w-2.5 h-2.5 rounded-full bg-rose-400"></span>
              <span class="w-2.5 h-2.5 rounded-full bg-amber-400"></span>
              <span class="w-2.5 h-2.5 rounded-full bg-emerald-400"></span>
              <span class="text-[13px] font-mono text-slate-600 ml-2">backend/app/graph/subgraphs/recommend.py</span>
            </div>
            <span class="text-[12px] font-mono text-slate-400">Python 3.11 ｜ 推荐子图</span>
          </div>

          <div class="p-4 font-mono text-[13px] leading-[1.8] text-slate-700 flex-1">
            <div class="flex">
              <div class="text-slate-300 pr-4 select-none text-right">
                <div>1</div><div>2</div><div>3</div><div>4</div><div>5</div><div>6</div><div>7</div><div>8</div><div>9</div><div>10</div><div>11</div>
              </div>
              <div class="flex-1">
                <div><span class="text-slate-400"># 1) 三路混合召回：覆盖率恒生效，文本需带 query，向量需 query_text 非空</span></div>
                <div><span class="text-sky-800">candidates</span> <span class="text-slate-500">=</span> <span class="text-indigo-700">coverage_recall</span><span class="text-slate-600">(ctx)</span> <span class="text-rose-600">|</span> <span class="text-indigo-700">text_recall</span><span class="text-slate-600">(ctx)</span></div>
                <div><span class="text-rose-600">if</span> <span class="text-sky-800">use_vector</span> <span class="text-rose-600">and</span> <span class="text-sky-800">query_text</span><span class="text-slate-600">:</span></div>
                <div>&nbsp;&nbsp;&nbsp;&nbsp;<span class="text-sky-800">candidates</span> <span class="text-rose-600">|=</span> <span class="text-indigo-700">vector_recall</span><span class="text-slate-600">(query_text, top_k=</span><span class="text-amber-700">20</span><span class="text-slate-600">)</span></div>
                <div>&nbsp;</div>
                <div><span class="text-slate-400"># 2) 四维布尔硬过滤：过敏原落到 SQL 布尔运算，绝不降权</span></div>
                <div><span class="text-sky-800">rows</span> <span class="text-slate-500">=</span> <span class="text-sky-800">session</span><span class="text-slate-600">.</span><span class="text-indigo-700">execute</span><span class="text-slate-600">(</span></div>
                <div>&nbsp;&nbsp;&nbsp;&nbsp;<span class="text-emerald-700">"WHERE NOT (allergen_codes &amp;&amp; %s::text[]) AND difficulty &lt;= %s"</span><span class="text-slate-600">,</span></div>
                <div>&nbsp;&nbsp;&nbsp;&nbsp;<span class="text-slate-600">(</span><span class="text-sky-800">user_allergens</span><span class="text-slate-600">,</span> <span class="text-sky-800">skill_level</span><span class="text-slate-600">))</span></div>
                <div>&nbsp;</div>
                <div><span class="text-slate-400"># 3) 排序输入只能来自 hard_filter 输出集 —— 结构上杜绝「打分后放回」</span></div>
              </div>
            </div>
          </div>

          <div class="bg-slate-50 border-t border-slate-200 px-5 py-2.5 flex items-center justify-between text-[12px] font-mono">
            <span class="text-rose-600">● 过敏原：布尔硬过滤，不降权</span>
            <span class="text-slate-500">dislike：降权 −0.5</span>
            <span class="text-emerald-600">✓ 12 条安全红线全绿</span>
          </div>
        </div>

        <div class="w-[37%] flex flex-col gap-4">
          <div class="bg-white border border-slate-200 border-l-4 border-l-rose-500 rounded-xl p-5 shadow-sm">
            <h3 class="text-[17px] font-bold text-slate-800 mb-2">为什么过敏原不能用「降权」</h3>
            <p class="text-[13px] text-slate-600 leading-relaxed">
              降权只是把分数调低，菜谱仍在候选集里 —— 一旦候选不足、或权重被远程调低，含过敏原的菜谱就可能重新浮上来。
              硬过滤则在数据层面直接剔除，<span class="font-semibold text-rose-600">不存在「浮上来」的路径</span>。
            </p>
          </div>

          <div class="bg-white border border-slate-200 border-l-4 border-l-cyan-700 rounded-xl p-5 shadow-sm">
            <h3 class="text-[17px] font-bold text-slate-800 mb-2">权重可远程热调</h3>
            <p class="text-[13px] text-slate-600 leading-relaxed">
              排序权重存放在远程配置中，运营侧可在不重新发版的前提下调整因子配比；但<span class="font-semibold">无论如何调整，都改不动过滤节点的布尔条件</span> —— 可调的是排序，不是安全。
            </p>
          </div>

          <div class="bg-white border border-slate-200 border-l-4 border-l-amber-500 rounded-xl p-5 shadow-sm flex-1">
            <h3 class="text-[17px] font-bold text-slate-800 mb-2">被过滤的菜谱可以「翻案」</h3>
            <p class="text-[13px] text-slate-600 leading-relaxed mb-2">
              过滤时逐项记录 <span class="font-mono text-[12px]">filtered_by</span> 计数，前端提供「显示被我过滤掉的菜」开关，用户可查看每道菜被过滤的具体原因。
            </p>
            <p class="text-[13px] text-slate-600 leading-relaxed">
              这个设计的价值在于：如果档案填错导致误过滤，用户能看见原因并及时修正，而不是面对一个「怎么推荐这么少」的黑盒。
            </p>
          </div>

          <div class="flex gap-2 flex-wrap">
            <span class="px-3.5 py-1.5 bg-cyan-50 border border-cyan-200 text-cyan-800 rounded-full text-[12px] font-mono">Python 3.11</span>
            <span class="px-3.5 py-1.5 bg-sky-50 border border-sky-200 text-sky-800 rounded-full text-[12px] font-mono">PostgreSQL 16</span>
            <span class="px-3.5 py-1.5 bg-indigo-50 border border-indigo-200 text-indigo-800 rounded-full text-[12px] font-mono">pgvector</span>
            <span class="px-3.5 py-1.5 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-full text-[12px] font-mono">SQL 布尔过滤</span>
          </div>
        </div>
      </div>

      <div class="mt-4 flex items-center justify-between text-[13px] text-slate-400">
        <span class="font-mono tracking-wider">AI 厨娘 · 智能烹饪助手 · 项目答辩</span>
        <span class="font-mono">17 / 25</span>
      </div>
    </div>
  </div>
`);window.slideDataMap.set(18,`
  <div class="w-[1440px] h-[810px] relative overflow-hidden slide-bg">
    <div class="absolute top-0 left-0 w-full h-[8px] bg-cyan-700"></div>
    <div class="w-[1350px] h-[720px] mx-auto my-[45px] relative pt-1 flex flex-col">

      <div class="flex items-center gap-4 mb-5">
        <div class="w-[6px] h-[42px] bg-cyan-700 rounded"></div>
        <div>
          <h2 class="text-[36px] font-bold text-slate-900 leading-tight">精彩代码② 风控短路与节点动态装配</h2>
          <p class="text-[15px] text-slate-500 mt-1">一票否决 = 控制流短路，不是「标记后丢弃」—— 三行代码守住整条安全底线</p>
        </div>
      </div>

      <div class="flex gap-5 flex-1">
        <div class="w-[37%] flex flex-col gap-4">
          <div class="bg-white border border-slate-200 border-l-4 border-l-rose-500 rounded-xl p-5 shadow-sm">
            <h3 class="text-[17px] font-bold text-slate-800 mb-2">「短路」和「丢弃」的区别</h3>
            <p class="text-[13px] text-slate-600 leading-relaxed">
              标记后丢弃意味着业务节点仍然执行了一遍，只是最后不返回结果 —— 中间可能已经调用了模型、写入了数据。
              短路则是条件边直接越过全部业务节点，<span class="font-semibold text-rose-600">连执行机会都不给</span>。
            </p>
          </div>

          <div class="bg-white border border-slate-200 border-l-4 border-l-cyan-700 rounded-xl p-5 shadow-sm">
            <h3 class="text-[17px] font-bold text-slate-800 mb-2">为什么风控不交给大模型</h3>
            <p class="text-[13px] text-slate-600 leading-relaxed">
              安全判定需要的是<span class="font-semibold">确定性</span>：同一句话今天判拦截、明天也必须拦截。
              规则引擎毫秒级返回、零 token 成本、可逐条审计，而且用户输入无法通过提示词绕过它 —— 因为它根本不读提示词。
            </p>
          </div>

          <div class="bg-white border border-slate-200 border-l-4 border-l-indigo-600 rounded-xl p-5 shadow-sm">
            <h3 class="text-[17px] font-bold text-slate-800 mb-2">动态装配带来的扩展性</h3>
            <p class="text-[13px] text-slate-600 leading-relaxed">
              节点按注册表装配，新增一个 Agent 只需注册一项，不需要改动图的构建逻辑。
              这让「22 个节点」不是一次性写死的结构，而是可持续生长的骨架。
            </p>
          </div>

          <div class="bg-slate-50 border border-slate-200 rounded-xl p-5 flex-1">
            <h3 class="text-[17px] font-bold text-slate-800 mb-2">双保险：两层拦截</h3>
            <p class="text-[13px] text-slate-600 leading-relaxed mb-2">
              第一层在图入口拦截用户输入；第二层在处理完成后拦截输出。
              即便某个节点被绕过，各节点入口还会再次检查否决标记，命中即以 <span class="font-mono text-[12px]">skipped_by_veto</span> 返回。
            </p>
            <p class="text-[13px] text-slate-600 leading-relaxed">
              规则、节点、出口三层防护叠加，才让「12 条安全红线全绿」这个结论站得住。
            </p>
          </div>
        </div>

        <div class="w-[63%] bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden flex flex-col">
          <div class="bg-slate-50 border-b border-slate-200 px-5 py-2.5 flex items-center justify-between">
            <div class="flex items-center gap-2.5">
              <span class="w-2.5 h-2.5 rounded-full bg-rose-400"></span>
              <span class="w-2.5 h-2.5 rounded-full bg-amber-400"></span>
              <span class="w-2.5 h-2.5 rounded-full bg-emerald-400"></span>
              <span class="text-[13px] font-mono text-slate-600 ml-2">backend/app/graph/nodes/guards.py ｜ main_graph.py</span>
            </div>
            <span class="text-[12px] font-mono text-slate-400">纯规则 · 零 LLM</span>
          </div>

          <div class="p-4 font-mono text-[13px] leading-[1.6] text-slate-700 flex-1">
            <div class="flex">
              <div class="text-slate-300 pr-4 select-none text-right">
                <div>1</div><div>2</div><div>3</div><div>4</div><div>5</div><div>6</div><div>7</div><div>8</div><div>9</div><div>10</div><div>11</div><div>12</div>
              </div>
              <div class="flex-1">
                <div><span class="text-slate-400"># ① 风控节点：纯规则引擎，不调用大模型</span></div>
                <div><span class="text-sky-800">verdict</span> <span class="text-slate-500">=</span> <span class="text-sky-800">safety_engine</span><span class="text-slate-600">.</span><span class="text-indigo-700">check</span><span class="text-slate-600">(text, stage=</span><span class="text-emerald-700">"intake"</span><span class="text-slate-600">)</span></div>
                <div><span class="text-rose-600">if</span> <span class="text-sky-800">verdict</span><span class="text-slate-600">.overrides_all:</span> <span class="text-slate-400"># 一票否决</span></div>
                <div>&nbsp;&nbsp;&nbsp;&nbsp;<span class="text-rose-600">return</span> <span class="text-slate-600">{</span><span class="text-emerald-700">"route"</span><span class="text-slate-600">:</span> <span class="text-emerald-700">"emit_safety_response"</span><span class="text-slate-600">}</span> <span class="text-slate-400"># 条件边 → 短路</span></div>
                <div>&nbsp;</div>
                <div><span class="text-slate-400"># ② 图装配：节点按注册表动态加入，新增 Agent 不必改装配逻辑</span></div>
                <div><span class="text-rose-600">for</span> <span class="text-sky-800">name</span><span class="text-slate-600">,</span> <span class="text-sky-800">builder</span> <span class="text-rose-600">in</span> <span class="text-sky-800">AGENT_REGISTRY</span><span class="text-slate-600">.</span><span class="text-indigo-700">items</span><span class="text-slate-600">():</span></div>
                <div>&nbsp;&nbsp;&nbsp;&nbsp;<span class="text-sky-800">graph</span><span class="text-slate-600">.</span><span class="text-indigo-700">add_node</span><span class="text-slate-600">(name,</span> <span class="text-indigo-700">builder</span><span class="text-slate-600">())</span></div>
                <div>&nbsp;</div>
                <div><span class="text-slate-400"># ③ 各节点入口统一检查否决标记，命中即跳过业务逻辑</span></div>
                <div><span class="text-rose-600">if</span> <span class="text-sky-800">state</span><span class="text-slate-600">[</span><span class="text-emerald-700">"input_verdict"</span><span class="text-slate-600">].overrides_all:</span></div>
                <div>&nbsp;&nbsp;&nbsp;&nbsp;<span class="text-rose-600">return</span> <span class="text-slate-600">{</span><span class="text-emerald-700">"skipped_by_veto"</span><span class="text-slate-600">:</span> <span class="text-amber-700">True</span><span class="text-slate-600">}</span> <span class="text-slate-400"># 不执行任何业务逻辑</span></div>
              </div>
            </div>
          </div>

          <div class="bg-slate-50 border-t border-slate-200 px-5 py-2.5 flex items-center justify-between text-[12px] font-mono">
            <span class="text-rose-600">● 一票否决：控制流短路</span>
            <span class="text-indigo-600">AGENT_REGISTRY：动态装配</span>
            <span class="text-slate-500">trace：FS-003@rules-v1.0 可回放</span>
          </div>
        </div>
      </div>

      <div class="mt-4 flex items-center justify-between text-[13px] text-slate-400">
        <span class="font-mono tracking-wider">AI 厨娘 · 智能烹饪助手 · 项目答辩</span>
        <span class="font-mono">18 / 25</span>
      </div>
    </div>
  </div>
`);window.slideDataMap.set(19,`
  <div class="w-[1440px] h-[810px] relative overflow-hidden slide-bg">
    <div class="absolute top-0 left-0 w-full h-[8px] bg-cyan-700"></div>
    <div class="w-[1350px] h-[720px] mx-auto my-[45px] relative pt-4 flex flex-col">

      <div class="flex items-end justify-between mb-4">
        <div class="flex items-center gap-4">
          <div class="w-[6px] h-[42px] bg-cyan-700 rounded"></div>
          <div>
            <h2 class="text-[36px] font-bold text-slate-900 leading-tight">功能演示 · 真实界面</h2>
            <p class="text-[15px] text-slate-500 mt-1">浏览器自动化实测 · 真实导航 + 交互操作 + 截图取证</p>
          </div>
        </div>
        <div class="flex gap-7">
          <div class="text-center">
            <p class="text-[26px] font-bold text-cyan-700 font-mono leading-none mb-1">16/16</p>
            <p class="text-[13px] text-slate-500">页面可达</p>
          </div>
          <div class="text-center">
            <p class="text-[26px] font-bold text-emerald-600 font-mono leading-none mb-1">0</p>
            <p class="text-[13px] text-slate-500">控制台 Error</p>
          </div>
          <div class="text-center">
            <p class="text-[26px] font-bold text-orange-600 font-mono leading-none mb-1">19</p>
            <p class="text-[13px] text-slate-500">截图存证</p>
          </div>
        </div>
      </div>

      <div class="grid grid-cols-2 gap-4 flex-1">
        <div class="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm flex flex-col">
          <img src="/assets/images/03-recommend.png" class="w-full h-[198px] object-cover object-top"/>
          <div class="px-4 py-2.5 border-t border-slate-200 flex-1">
            <p class="text-[16px] font-bold text-slate-800 mb-1">推荐结果页 · 可解释的推荐</p>
            <p class="text-[13px] text-slate-500 leading-relaxed">按匹配程度分三档分组，卡片展示耗时、难度、热量、覆盖率与缺失食材；提供「为什么推荐给你」入口与被过滤明细重放开关；匹配不足时如实说明并提示「宁缺毋滥」。</p>
          </div>
        </div>

        <div class="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm flex flex-col">
          <img src="/assets/images/06-recipe-detail.png" class="w-full h-[198px] object-cover object-top"/>
          <div class="px-4 py-2.5 border-t border-slate-200 flex-1">
            <p class="text-[16px] font-bold text-slate-800 mb-1">菜谱详情页 · 安全信息前置</p>
            <p class="text-[13px] text-slate-500 leading-relaxed">顶部常驻致敏原警示条（实测检出大豆）；主料、辅料、调味料三表用量量化并逐行标注致敏原；支持份数缩放重算；页面底部给出营养估算入口与设备要求。</p>
          </div>
        </div>

        <div class="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm flex flex-col">
          <img src="/assets/images/07-cook-guide.png" class="w-full h-[198px] object-cover object-top"/>
          <div class="px-4 py-2.5 border-t border-slate-200 flex-1">
            <p class="text-[16px] font-bold text-slate-800 mb-1">分步烹饪引导 · 厨房场景优先</p>
            <p class="text-[13px] text-slate-500 leading-relaxed">大字单步显示，进度条标注「第 N 步 / 共 M 步」；上一步下一步本地即时切换无需网络；并行计时器提供 5 个预设计时与自定义；退出需二次确认，支持断点续做。</p>
          </div>
        </div>

        <div class="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm flex flex-col">
          <img src="/assets/images/08-blocked.png" class="w-full h-[198px] object-cover object-top"/>
          <div class="px-4 py-2.5 border-t border-slate-200 flex-1">
            <p class="text-[16px] font-bold text-slate-800 mb-1">风控拦截页 · 真实触发</p>
            <p class="text-[13px] text-slate-500 leading-relaxed">实测输入「发芽土豆能吃吗」命中 FS-003，页面三段式呈现风险说明、正确做法与就医引导，并明确标注「本次请求未生成任何内容」，同时提供「我认为这是误判」的上报入口。</p>
          </div>
        </div>
      </div>

      <div class="mt-3 bg-white border border-slate-200 rounded-lg px-5 py-2.5 flex items-center gap-8 text-[13px] text-slate-600 shadow-sm">
        <span class="font-medium text-slate-700">核心链路验证：</span>
        <span class="flex items-center gap-2"><span class="w-2 h-2 rounded-full bg-cyan-700"></span>选食材 → 推荐 → 详情 → 烹饪 全链路跑通</span>
        <span class="flex items-center gap-2"><span class="w-2 h-2 rounded-full bg-rose-600"></span>风控链路真实触发并正确拦截</span>
        <span class="flex items-center gap-2"><span class="w-2 h-2 rounded-full bg-indigo-600"></span>路由守卫：未选食材 / 无拦截数据 / 未知路径均正确重定向</span>
      </div>
    </div>
  </div>
`);window.slideDataMap.set(20,`
  <div class="w-[1440px] h-[810px] relative overflow-hidden slide-bg flex items-center justify-center">
    <div class="absolute inset-0" style="background-image: linear-gradient(#E6EDF5 1px, transparent 1px), linear-gradient(90deg,#E6EDF5 1px, transparent 1px); background-size: 48px 48px;"></div>
    <div class="absolute -bottom-40 -right-32 w-[520px] h-[520px] bg-indigo-100 rounded-full blur-3xl opacity-60"></div>

    <div class="w-[1180px] bg-white rounded-3xl border border-slate-200 shadow-sm px-16 py-12 relative overflow-hidden">
      <div class="absolute left-0 top-0 w-full h-[8px] bg-indigo-600"></div>
      <div class="absolute right-10 top-6 text-[150px] font-bold text-slate-50 font-mono leading-none select-none">03</div>

      <div class="relative">
        <div class="inline-flex items-center gap-2 bg-indigo-50 border border-indigo-200 text-indigo-700 px-4 py-1.5 rounded-full text-[14px] font-medium mb-6">
          CHAPTER 03
        </div>
        <h1 class="text-[54px] font-bold text-slate-900 mb-4 tracking-tight">问题与解决方案</h1>
        <p class="text-[20px] text-slate-500 mb-10 leading-relaxed">
          这一部分不复述成绩，只讲踩过的坑：六类问题的「问题 → 方案 → 验证结果」，以及四个从现象追到根因的典型案例。
        </p>

        <div class="grid grid-cols-3 gap-5">
          <div class="bg-slate-50 border border-slate-200 rounded-xl px-6 py-5">
            <p class="text-[30px] font-bold text-indigo-600 font-mono leading-none mb-2">6</p>
            <p class="text-[14px] text-slate-500 leading-relaxed">问题类别，覆盖算法、资源、基础设施与浏览器安全模型</p>
          </div>
          <div class="bg-slate-50 border border-slate-200 rounded-xl px-6 py-5">
            <p class="text-[30px] font-bold text-emerald-600 font-mono leading-none mb-2">3<span class="text-[18px]">/4</span></p>
            <p class="text-[14px] text-slate-500 leading-relaxed">典型案例已闭环，剩余一项已登记为风险并给出触发条件</p>
          </div>
          <div class="bg-slate-50 border border-slate-200 rounded-xl px-6 py-5">
            <p class="text-[30px] font-bold text-cyan-700 font-mono leading-none mb-2">11</p>
            <p class="text-[14px] text-slate-500 leading-relaxed">风险登记册条目（R-23 ~ R-33），未闭环项主动披露</p>
          </div>
        </div>
      </div>
    </div>
  </div>
`);window.slideDataMap.set(21,`
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
`);window.slideDataMap.set(22,`
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
`);window.slideDataMap.set(23,`
  <div class="w-[1440px] h-[810px] relative overflow-hidden slide-bg flex items-center justify-center">
    <div class="absolute inset-0" style="background-image: linear-gradient(#E6EDF5 1px, transparent 1px), linear-gradient(90deg,#E6EDF5 1px, transparent 1px); background-size: 48px 48px;"></div>
    <div class="absolute -top-40 -left-32 w-[520px] h-[520px] bg-emerald-100 rounded-full blur-3xl opacity-60"></div>

    <div class="w-[1180px] bg-white rounded-3xl border border-slate-200 shadow-sm px-16 py-12 relative overflow-hidden">
      <div class="absolute left-0 top-0 w-full h-[8px] bg-emerald-600"></div>
      <div class="absolute right-10 top-6 text-[150px] font-bold text-slate-50 font-mono leading-none select-none">04</div>

      <div class="relative">
        <div class="inline-flex items-center gap-2 bg-emerald-50 border border-emerald-200 text-emerald-700 px-4 py-1.5 rounded-full text-[14px] font-medium mb-6">
          CHAPTER 04
        </div>
        <h1 class="text-[54px] font-bold text-slate-900 mb-4 tracking-tight">项目完成后的收获</h1>
        <p class="text-[20px] text-slate-500 mb-10 leading-relaxed">
          最后回答「做这个项目我得到了什么」—— 技术深度、工程能力、产品思维，以及两项在课程里学不到、只有在真实交付中才会长出来的意识。
        </p>

        <div class="grid grid-cols-5 gap-4">
          <div class="bg-slate-50 border border-slate-200 rounded-xl px-4 py-5 text-center">
            <p class="text-[26px] font-bold text-cyan-700 font-mono leading-none mb-2">01</p>
            <p class="text-[14px] font-semibold text-slate-700">技术深度</p>
          </div>
          <div class="bg-slate-50 border border-slate-200 rounded-xl px-4 py-5 text-center">
            <p class="text-[26px] font-bold text-indigo-600 font-mono leading-none mb-2">02</p>
            <p class="text-[14px] font-semibold text-slate-700">工程能力</p>
          </div>
          <div class="bg-slate-50 border border-slate-200 rounded-xl px-4 py-5 text-center">
            <p class="text-[26px] font-bold text-orange-600 font-mono leading-none mb-2">03</p>
            <p class="text-[14px] font-semibold text-slate-700">产品思维</p>
          </div>
          <div class="bg-slate-50 border border-slate-200 rounded-xl px-4 py-5 text-center">
            <p class="text-[26px] font-bold text-sky-600 font-mono leading-none mb-2">04</p>
            <p class="text-[14px] font-semibold text-slate-700">协作规范</p>
          </div>
          <div class="bg-slate-50 border border-slate-200 rounded-xl px-4 py-5 text-center">
            <p class="text-[26px] font-bold text-rose-600 font-mono leading-none mb-2">05</p>
            <p class="text-[14px] font-semibold text-slate-700">风险意识</p>
          </div>
        </div>
      </div>
    </div>
  </div>
`);window.slideDataMap.set(24,`
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
`);window.slideDataMap.set(25,`
  <div class="w-[1440px] h-[810px] relative overflow-hidden slide-bg flex items-center justify-center">
    <div class="absolute inset-0" style="background-image: linear-gradient(#E6EDF5 1px, transparent 1px), linear-gradient(90deg,#E6EDF5 1px, transparent 1px); background-size: 48px 48px;"></div>
    <div class="absolute -bottom-48 -left-40 w-[560px] h-[560px] bg-cyan-100 rounded-full blur-3xl opacity-70"></div>
    <div class="absolute -top-32 -right-24 w-[460px] h-[460px] bg-orange-100 rounded-full blur-3xl opacity-70"></div>
    <div class="absolute top-0 left-0 w-full h-[10px] bg-cyan-700"></div>
    <div class="absolute top-[10px] left-0 w-[36%] h-[5px] bg-orange-600"></div>

    <div class="relative z-10 text-center px-24">
      <h1 class="text-[88px] font-bold text-slate-900 mb-6 tracking-[0.08em]">谢谢</h1>
      <p class="text-[26px] text-slate-600 font-light tracking-[0.24em] mb-4">感谢您的耐心聆听 · 请老师指正</p>
      <div class="w-[420px] h-px bg-slate-300 mx-auto my-9"></div>

      <div class="flex items-center justify-center gap-12 bg-white/90 border border-slate-200 rounded-2xl px-14 py-7 shadow-sm">
        <div class="text-center">
          <p class="text-[12px] text-slate-400 font-mono tracking-[0.25em] mb-2">PRESENTED BY</p>
          <p class="text-[26px] font-bold text-slate-900 tracking-[0.18em]">肖裔雄</p>
        </div>
        <div class="w-px h-16 bg-slate-200"></div>
        <div class="text-center">
          <p class="text-[12px] text-slate-400 font-mono tracking-[0.25em] mb-2">PROJECT</p>
          <p class="text-[26px] font-bold text-slate-900">AI 厨娘 · 智能烹饪助手</p>
        </div>
        <div class="w-px h-16 bg-slate-200"></div>
        <div class="text-center">
          <p class="text-[12px] text-slate-400 font-mono tracking-[0.25em] mb-2">DATE</p>
          <p class="text-[26px] font-bold text-slate-900">2026.10.14</p>
        </div>
      </div>

      <p class="text-[15px] text-slate-500 mt-9 font-mono tracking-wider">LANGGRAPH MULTI-AGENT · FOOD SAFETY GUARDRAILS · EXPLAINABLE RECOMMENDATION</p>
    </div>
  </div>
`);
