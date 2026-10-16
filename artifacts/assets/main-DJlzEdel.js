(function(){const e=document.createElement("link").relList;if(e&&e.supports&&e.supports("modulepreload"))return;for(const t of document.querySelectorAll('link[rel="modulepreload"]'))l(t);new MutationObserver(t=>{for(const a of t)if(a.type==="childList")for(const i of a.addedNodes)i.tagName==="LINK"&&i.rel==="modulepreload"&&l(i)}).observe(document,{childList:!0,subtree:!0});function s(t){const a={};return t.integrity&&(a.integrity=t.integrity),t.referrerPolicy&&(a.referrerPolicy=t.referrerPolicy),t.crossOrigin==="use-credentials"?a.credentials="include":t.crossOrigin==="anonymous"?a.credentials="omit":a.credentials="same-origin",a}function l(t){if(t.ep)return;t.ep=!0;const a=s(t);fetch(t.href,a)}})();class o{constructor(){this.currentIndex=0,this.slides=[],this.totalSlides=0,this.viewport=document.getElementById("ppt-viewport"),this.prevBtn=document.getElementById("prevBtn"),this.nextBtn=document.getElementById("nextBtn"),this.progressBarFill=document.getElementById("progressBarFill"),this.pageIndicator=document.getElementById("pageIndicator"),this.init(),this.initWindowMessage()}init(){this.loadSlides(),this.bindEvents(),this.initializePage(),this.updateUI(),this.updateViewportScale()}initWindowMessage(){window.addEventListener("message",e=>{if(!e.data||typeof e.data!="object")return;const{type:s,data:l}=e.data;s==="childrenstart"?(this.prevBtn.style.visibility="hidden",this.nextBtn.style.visibility="hidden",this.progressBarFill.style.visibility="hidden",this.pageIndicator.style.visibility="hidden"):s==="childrenstop"&&(this.prevBtn.style.visibility="visible",this.nextBtn.style.visibility="visible",this.progressBarFill.style.visibility="visible",this.pageIndicator.style.visibility="visible")})}initializePage(){const e=new URLSearchParams(window.location.search);let s=e.get("page");if(!s){s="1",e.set("page","1");const a=`${window.location.pathname}?${e.toString()}`;window.history.replaceState({},"",a)}const l=parseInt(s,10),t=l-1;if(!isNaN(l)&&t>=0&&t<this.totalSlides)this.slides[0]&&this.slides[0].classList.remove("active"),this.currentIndex=t,this.slides[t]&&this.slides[t].classList.add("active");else{console.warn(`无效的页码参数: ${s}，将显示第 1 页`),e.set("page","1");const a=`${window.location.pathname}?${e.toString()}`;window.history.replaceState({},"",a)}}loadSlides(){if(typeof window.slideDataMap>"u"){console.error("未找到 slideDataMap");return}const e=Array.from(window.slideDataMap.keys()).sort((s,l)=>s-l);if(this.totalSlides=e.length,this.totalSlides===0){console.warn("slideDataMap 为空，没有幻灯片可加载");return}e.forEach((s,l)=>{const t=document.createElement("div");t.className="slide",l===0&&t.classList.add("active");const a=window.slideDataMap.get(s);if(!a||typeof a!="string"){this.totalSlides--,console.error(`未找到页码 ${s} 的内容, 或者页码 ${s} 的内容为空`);return}const i=document.createElement("div");i.innerHTML=a.trim(),t.appendChild(i),this.viewport.appendChild(t),this.slides.push(t)})}bindEvents(){this.prevBtn.addEventListener("click",()=>this.prevSlide()),this.nextBtn.addEventListener("click",()=>this.nextSlide()),document.addEventListener("keydown",s=>{s.key==="ArrowLeft"?this.prevSlide():s.key==="ArrowRight"||s.key===" "?(s.preventDefault(),this.nextSlide()):s.key==="Home"?this.goToSlide(0):s.key==="End"&&this.goToSlide(this.totalSlides-1)});let e=0;this.viewport.addEventListener("touchstart",s=>{e=s.touches[0].clientX}),this.viewport.addEventListener("touchend",s=>{const l=s.changedTouches[0].clientX,t=e-l;Math.abs(t)>50&&(t>0?this.nextSlide():this.prevSlide())}),window.addEventListener("resize",()=>this.updateViewportScale())}prevSlide(){this.currentIndex>0&&this.goToSlide(this.currentIndex-1)}nextSlide(){this.currentIndex<this.totalSlides-1&&this.goToSlide(this.currentIndex+1)}goToSlide(e){e<0||e>=this.totalSlides||(this.slides[this.currentIndex].classList.remove("active"),this.currentIndex=e,this.slides[this.currentIndex].classList.add("active"),this.updateUrlPage(e+1),this.updateUI())}updateUrlPage(e){const s=new URLSearchParams(window.location.search);s.set("page",e.toString());const l=`${window.location.pathname}?${s.toString()}`;window.history.replaceState({},"",l)}updateUI(){if(this.totalSlides===0){this.prevBtn.disabled=!0,this.nextBtn.disabled=!0,this.progressBarFill.style.width="0%",this.pageIndicator.textContent="制作中";return}this.prevBtn.disabled=this.currentIndex===0,this.nextBtn.disabled=this.currentIndex===this.totalSlides-1;const e=(this.currentIndex+1)/this.totalSlides*100;this.progressBarFill.style.width=`${e}%`,this.pageIndicator.textContent=`${this.currentIndex+1} / ${this.totalSlides}`}updateViewportScale(){const t=window.innerWidth-40,a=window.innerHeight-40,i=t/1440,n=a/810,r=Math.min(i,n,1);this.viewport.style.transform=`scale(${r})`,console.log(`窗口: ${window.innerWidth}x${window.innerHeight}, 缩放: ${r.toFixed(3)}`)}}class p{constructor(){this.validRoutes=["/","/index.html"],this.checkRoute()}checkRoute(){const e=window.location.pathname;if(e.includes("404.html"))return;this.validRoutes.some(l=>l==="/"?e==="/"||e==="/index.html":e===l)||(console.warn(`Invalid route detected: ${e}, redirecting to 404`),window.location.href="/404.html")}addRoute(e){this.validRoutes.includes(e)||this.validRoutes.push(e)}isValidRoute(e){return this.validRoutes.includes(e)}}window.addEventListener("DOMContentLoaded",()=>{new p,new o});window.slideDataMap.set(1,`
  <div class="cover-wrapper relative w-[1440px] h-[810px] slide-bg">
    <div class="absolute inset-0" style="background-image: linear-gradient(rgba(34,211,238,0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(34,211,238,0.05) 1px, transparent 1px); background-size: 60px 60px;"></div>
    <div class="absolute top-0 left-0 flex items-center justify-center w-[1440px] h-[810px]">
      <div class="text-center max-w-[1150px] relative z-10">
        <div class="relative inline-block mb-8">
          <div class="absolute inset-0 bg-cyan-500 blur-3xl opacity-50"></div>
          <div class="relative text-[104px] font-bold text-cyan-400 leading-none" style="letter-spacing: 0.12em; text-shadow: 0 0 30px rgba(34,211,238,0.85), 0 0 70px rgba(34,211,238,0.45); font-family: 'Noto Sans SC', sans-serif;">
            AI 厨娘
          </div>
        </div>
        <div class="text-[30px] text-cyan-300 font-light tracking-[0.32em] mb-7">智能烹饪助手 · 项目答辩</div>
        <div class="w-[520px] h-px mx-auto bg-cyan-500/50 mb-10"></div>
        <div class="flex items-center justify-center gap-4 mb-14">
          <div class="w-3 h-3 bg-cyan-500 rounded-full animate-pulse"></div>
          <div class="text-cyan-400 font-mono text-[17px] tracking-[0.26em]">SMART COOKING · LANGGRAPH MULTI-AGENT</div>
        </div>
        <div class="flex items-center justify-center gap-12">
          <div class="text-center">
            <p class="text-[12px] text-cyan-600 font-mono tracking-[0.3em] mb-2">PRESENTED BY</p>
            <p class="text-[28px] font-bold text-cyan-100 tracking-[0.22em]">肖裔雄</p>
          </div>
          <div class="w-px h-16 bg-cyan-500/40"></div>
          <div class="text-center">
            <p class="text-[12px] text-cyan-600 font-mono tracking-[0.3em] mb-2">DELIVERED</p>
            <p class="text-[28px] font-bold text-cyan-100 tracking-[0.06em]">2026.10.14</p>
          </div>
          <div class="w-px h-16 bg-cyan-500/40"></div>
          <div class="text-center">
            <p class="text-[12px] text-cyan-600 font-mono tracking-[0.3em] mb-2">STATUS</p>
            <p class="text-[28px] font-bold text-cyan-100 tracking-[0.06em]">已上线</p>
          </div>
        </div>
      </div>
    </div>
  </div>
`);window.slideDataMap.set(2,`
  <div class="w-[1440px] h-[810px] shadow-2xl relative overflow-hidden slide-bg">
    <div class="absolute inset-0" style="background-image: linear-gradient(rgba(34,211,238,0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(34,211,238,0.05) 1px, transparent 1px); background-size: 50px 50px;"></div>
    <div class="absolute inset-0" style="opacity: 0.08; background: repeating-linear-gradient(0deg, rgba(34,211,238,0.35) 0px, transparent 2px, transparent 5px);"></div>
    <div class="absolute top-[9%] left-0 w-full h-[2px] bg-cyan-400/50"></div>
    <div class="absolute bottom-[12%] left-0 w-full h-[2px] bg-cyan-400/30"></div>

    <div class="w-[1350px] h-[720px] mx-auto my-[45px] relative">
      <div class="flex items-center h-full">
        <div style="width: 34%; padding-right: 50px;">
          <h1 class="text-[64px] font-bold text-cyan-400 mb-5" style="letter-spacing: 8px; text-shadow: 0 0 30px rgba(34,211,238,0.5); font-family: 'Montserrat', sans-serif;">CONTENTS</h1>
          <p class="text-[26px] text-cyan-200 tracking-[0.35em] mb-8">目 录</p>
          <div class="space-y-2">
            <div class="w-full h-[3px] bg-cyan-400/70"></div>
            <div class="w-3/4 h-[3px] bg-blue-400/50"></div>
            <div class="w-1/2 h-[3px] bg-purple-400/40"></div>
          </div>
          <p class="text-[14px] text-gray-500 font-mono mt-10 leading-relaxed">AI 厨娘 · 智能烹饪助手<br/>项目答辩 · 肖裔雄</p>
        </div>

        <div style="flex: 1;" class="space-y-4">
          <div style="position: relative; padding: 16px 26px; background: rgba(34,211,238,0.06); border-left: 4px solid #22d3ee; clip-path: polygon(0 0, calc(100% - 14px) 0, 100% 14px, 100% 100%, 14px 100%, 0 calc(100% - 14px));">
            <div class="flex items-center gap-6">
              <div class="w-[54px] h-[54px] border-2 border-cyan-400 flex items-center justify-center" style="background: rgba(34,211,238,0.12);">
                <span class="text-[22px] font-bold text-cyan-300 font-mono">01</span>
              </div>
              <div style="flex: 1;">
                <h3 class="text-[24px] font-bold text-cyan-200 mb-1">项目概述与技术架构</h3>
                <p class="text-cyan-400/70 text-[15px]">产品定位 · 交付指标 · 系统架构 · 技术栈选型</p>
              </div>
            </div>
          </div>

          <div style="position: relative; padding: 16px 26px; background: rgba(56,189,248,0.06); border-left: 4px solid #38bdf8; clip-path: polygon(0 0, calc(100% - 14px) 0, 100% 14px, 100% 100%, 14px 100%, 0 calc(100% - 14px));">
            <div class="flex items-center gap-6">
              <div class="w-[54px] h-[54px] border-2 border-blue-400 flex items-center justify-center" style="background: rgba(56,189,248,0.12);">
                <span class="text-[22px] font-bold text-blue-300 font-mono">02</span>
              </div>
              <div style="flex: 1;">
                <h3 class="text-[24px] font-bold text-blue-200 mb-1">重点模块与精彩代码</h3>
                <p class="text-blue-400/70 text-[15px]">推荐子图 · 风控引擎 · 中枢调度 · 两段关键实现</p>
              </div>
            </div>
          </div>

          <div style="position: relative; padding: 16px 26px; background: rgba(167,139,250,0.06); border-left: 4px solid #a78bfa; clip-path: polygon(0 0, calc(100% - 14px) 0, 100% 14px, 100% 100%, 14px 100%, 0 calc(100% - 14px));">
            <div class="flex items-center gap-6">
              <div class="w-[54px] h-[54px] border-2 border-purple-400 flex items-center justify-center" style="background: rgba(167,139,250,0.12);">
                <span class="text-[22px] font-bold text-purple-300 font-mono">03</span>
              </div>
              <div style="flex: 1;">
                <h3 class="text-[24px] font-bold text-purple-200 mb-1">问题与解决方案</h3>
                <p class="text-purple-400/70 text-[15px]">4 类问题总览 · 4 个典型案例深剖</p>
              </div>
            </div>
          </div>

          <div style="position: relative; padding: 16px 26px; background: rgba(16,185,129,0.06); border-left: 4px solid #10b981; clip-path: polygon(0 0, calc(100% - 14px) 0, 100% 14px, 100% 100%, 14px 100%, 0 calc(100% - 14px));">
            <div class="flex items-center gap-6">
              <div class="w-[54px] h-[54px] border-2 border-emerald-400 flex items-center justify-center" style="background: rgba(16,185,129,0.12);">
                <span class="text-[22px] font-bold text-emerald-300 font-mono">04</span>
              </div>
              <div style="flex: 1;">
                <h3 class="text-[24px] font-bold text-emerald-200 mb-1">项目完成后的收获</h3>
                <p class="text-emerald-400/70 text-[15px]">技术深度 · 工程能力 · 产品思维 · 协作与风险意识</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
`);window.slideDataMap.set(3,`
  <div class="w-[1440px] h-[810px] shadow-2xl relative overflow-hidden slide-bg">
    <div class="w-[1350px] h-[720px] mx-auto my-[45px] relative">
      <div class="absolute inset-0 opacity-20" style="background-image: linear-gradient(rgba(34,211,238,0.1) 1px, transparent 1px), linear-gradient(90deg, rgba(34,211,238,0.1) 1px, transparent 1px); background-size: 40px 40px;"></div>
      <div class="absolute top-1/2 left-0 right-0 h-px bg-cyan-400/60"></div>
      <div class="absolute top-1/2 left-0 right-0 h-16 bg-cyan-500/10"></div>
      <div class="relative z-10 flex items-center justify-center h-full">
        <div class="text-center">
          <div class="text-[52px] font-bold text-cyan-500 mb-6 font-mono">
            <span class="inline-block border-2 border-cyan-500 px-8 py-3">&lt; 01 /&gt;</span>
          </div>
          <h1 class="text-[56px] font-bold text-white mb-4 tracking-[0.1em]">项目概述与技术架构</h1>
          <p class="text-[22px] text-cyan-400 tracking-[0.12em]">从产品定位到 47,736 行代码的落地路径</p>
          <div class="flex items-center justify-center gap-2 mt-8">
            <div class="w-2 h-2 bg-cyan-400 rounded-full animate-pulse"></div>
            <div class="w-2 h-2 bg-cyan-400 rounded-full animate-pulse" style="animation-delay: 0.2s;"></div>
            <div class="w-2 h-2 bg-cyan-400 rounded-full animate-pulse" style="animation-delay: 0.4s;"></div>
          </div>
        </div>
      </div>
    </div>
  </div>
`);window.slideDataMap.set(4,`
  <div class="w-[1440px] h-[810px] shadow-2xl relative overflow-hidden slide-bg">
    <div class="absolute inset-0 bg-blue-950/20"></div>
    <div class="w-[1350px] h-[720px] mx-auto my-[45px] relative">
      <h2 class="text-[36px] font-bold text-cyan-400 mb-2">项目定位与交付事实</h2>
      <p class="text-[16px] text-gray-400 font-mono mb-8">面向家庭做饭人群的智能烹饪助手 · 甲乙方外包项目</p>

      <div class="flex gap-8 items-start justify-center">
        <div class="w-[350px]">
          <div class="h-11 bg-slate-800 border-b border-cyan-500/40 flex items-center justify-center rounded-t">
            <span class="text-cyan-400 font-mono text-[15px] font-bold tracking-wider">01 · 项目定位</span>
          </div>
          <div class="h-[420px] bg-slate-900/80 border-2 border-cyan-500/40 border-t-0 rounded-b p-3 space-y-[6px]">
            <div class="min-h-[42px] bg-slate-700/70 border border-cyan-500/40 rounded flex items-center px-3 py-2"><span class="text-cyan-200 text-[15px] leading-snug">面向家庭做饭人群</span></div>
            <div class="min-h-[42px] bg-slate-700/70 border border-cyan-500/40 rounded flex items-center px-3 py-2"><span class="text-cyan-200 text-[15px] leading-snug">食材 → 推荐 → 引导 → 营养 全链路</span></div>
            <div class="min-h-[42px] bg-slate-700/70 border border-cyan-500/40 rounded flex items-center px-3 py-2"><span class="text-cyan-200 text-[15px] leading-snug">多智能体 LangGraph 编排</span></div>
            <div class="min-h-[42px] bg-slate-700/70 border border-cyan-500/40 rounded flex items-center px-3 py-2"><span class="text-cyan-200 text-[15px] leading-snug">食品安全风控作为安全底线</span></div>
            <div class="min-h-[42px] bg-slate-700/70 border border-cyan-500/40 rounded flex items-center px-3 py-2"><span class="text-cyan-200 text-[15px] leading-snug">三端同源：Web / 小程序 / 后台</span></div>
            <div class="min-h-[42px] bg-slate-700/70 border border-cyan-500/40 rounded flex items-center px-3 py-2"><span class="text-cyan-200 text-[15px] leading-snug">推荐主路径全程不调大模型</span></div>
            <div class="min-h-[42px] bg-slate-700/70 border border-cyan-500/40 rounded flex items-center px-3 py-2"><span class="text-cyan-200 text-[15px] leading-snug">过敏原布尔硬过滤，绝不降权</span></div>
          </div>
        </div>

        <div class="w-[350px]">
          <div class="h-11 bg-slate-800 border-b border-purple-500/40 flex items-center justify-center rounded-t">
            <span class="text-purple-400 font-mono text-[15px] font-bold tracking-wider">02 · 协作模式</span>
          </div>
          <div class="h-[420px] bg-slate-900/80 border-2 border-purple-500/40 border-t-0 rounded-b p-3 space-y-[6px]">
            <div class="min-h-[42px] bg-slate-700/70 border border-purple-500/40 rounded flex items-center px-3 py-2"><span class="text-purple-200 text-[15px] leading-snug">甲乙方外包，我方为乙方</span></div>
            <div class="min-h-[42px] bg-slate-700/70 border border-purple-500/40 rounded flex items-center px-3 py-2"><span class="text-purple-200 text-[15px] leading-snug">阶段一 7 工作日 Web 原型</span></div>
            <div class="min-h-[42px] bg-slate-700/70 border border-purple-500/40 rounded flex items-center px-3 py-2"><span class="text-purple-200 text-[15px] leading-snug">合同 6 页 / 实交 16 页（超额）</span></div>
            <div class="min-h-[42px] bg-slate-700/70 border border-purple-500/40 rounded flex items-center px-3 py-2"><span class="text-purple-200 text-[15px] leading-snug">阶段二 16 周：小程序 + 后台</span></div>
            <div class="min-h-[42px] bg-slate-700/70 border border-purple-500/40 rounded flex items-center px-3 py-2"><span class="text-purple-200 text-[15px] leading-snug">需求变更必须走 CR 变更单</span></div>
            <div class="min-h-[42px] bg-slate-700/70 border border-purple-500/40 rounded flex items-center px-3 py-2"><span class="text-purple-200 text-[15px] leading-snug">文档冲突以需求文档为准</span></div>
            <div class="min-h-[42px] bg-slate-700/70 border border-purple-500/40 rounded flex items-center px-3 py-2"><span class="text-purple-200 text-[15px] leading-snug">交付物 B-D1 ~ B-D8 八类</span></div>
          </div>
        </div>

        <div class="w-[350px]">
          <div class="h-11 bg-slate-800 border-b border-emerald-500/40 flex items-center justify-center rounded-t">
            <span class="text-emerald-400 font-mono text-[15px] font-bold tracking-wider">03 · 交付事实</span>
          </div>
          <div class="h-[420px] bg-slate-900/80 border-2 border-emerald-500/40 border-t-0 rounded-b p-3 space-y-[6px]">
            <div class="min-h-[42px] bg-slate-700/70 border border-emerald-500/40 rounded flex items-center px-3 py-2"><span class="text-emerald-200 text-[15px] leading-snug">三端共 <span class="font-bold text-emerald-300">74 页</span></span></div>
            <div class="min-h-[42px] bg-slate-700/70 border border-emerald-500/40 rounded flex items-center px-3 py-2"><span class="text-emerald-200 text-[15px] leading-snug">Web 16 / 小程序 42 / 后台 16</span></div>
            <div class="min-h-[42px] bg-slate-700/70 border border-emerald-500/40 rounded flex items-center px-3 py-2"><span class="text-emerald-200 text-[15px] leading-snug">前端代码 <span class="font-bold text-emerald-300">47,736 行</span></span></div>
            <div class="min-h-[42px] bg-slate-700/70 border border-emerald-500/40 rounded flex items-center px-3 py-2"><span class="text-emerald-200 text-[15px] leading-snug">后端 118 模块 / 121 接口</span></div>
            <div class="min-h-[42px] bg-slate-700/70 border border-emerald-500/40 rounded flex items-center px-3 py-2"><span class="text-emerald-200 text-[15px] leading-snug">后端单测 319 passed</span></div>
            <div class="min-h-[42px] bg-slate-700/70 border border-emerald-500/40 rounded flex items-center px-3 py-2"><span class="text-emerald-200 text-[15px] leading-snug">12 条安全红线全绿</span></div>
            <div class="min-h-[42px] bg-slate-700/70 border border-emerald-500/40 rounded flex items-center px-3 py-2"><span class="text-emerald-200 text-[15px] leading-snug">生产环境 8005 全端点 200</span></div>
          </div>
        </div>
      </div>
    </div>
  </div>
`);window.slideDataMap.set(5,`
  <div class="w-[1440px] h-[810px] shadow-2xl relative overflow-hidden slide-bg">
    <div class="absolute inset-0 opacity-10" style="background-image: repeating-linear-gradient(0deg, transparent, transparent 40px, #22d3ee 40px, #22d3ee 41px), repeating-linear-gradient(90deg, transparent, transparent 40px, #22d3ee 40px, #22d3ee 41px);"></div>
    <div class="w-full h-full flex items-center justify-center relative">
      <div class="w-[1350px] h-[720px] mx-auto p-10 flex flex-col items-center justify-center relative">
        <h2 class="text-[42px] font-bold text-cyan-400 mb-3 relative z-10">交付成果核心指标</h2>
        <p class="text-[17px] text-gray-400 font-mono mb-14 relative z-10">三端 74 页 · 47,736 行前端代码 · 121 个接口端点 · 加权完成度 ≈88%</p>

        <div class="relative w-full max-w-5xl" style="perspective: 1200px;">
          <div class="flex justify-center items-center gap-16">
            <div class="relative w-60 h-60" style="transform-style: preserve-3d; transform: rotateX(-15deg) rotateY(-25deg);">
              <div class="absolute w-full h-full bg-cyan-600/80 border-2 border-cyan-400 flex items-center justify-center" style="transform: translateZ(120px);">
                <div class="text-center">
                  <div class="text-[34px] mb-2">🌐</div>
                  <p class="text-white font-bold text-[24px]">Web 演示端</p>
                  <p class="text-cyan-200 text-[15px] mt-2">16 页 · Vue 3</p>
                </div>
              </div>
              <div class="absolute w-full h-full bg-cyan-700/60 border-2 border-cyan-500" style="transform: rotateY(90deg) translateZ(120px);"></div>
              <div class="absolute w-full h-full bg-cyan-500/40 border-2 border-cyan-600" style="transform: rotateX(90deg) translateZ(120px);"></div>
            </div>

            <div class="relative w-60 h-60" style="transform-style: preserve-3d; transform: rotateX(-15deg) rotateY(-25deg);">
              <div class="absolute w-full h-full bg-purple-600/80 border-2 border-purple-400 flex items-center justify-center" style="transform: translateZ(120px);">
                <div class="text-center">
                  <div class="text-[34px] mb-2">📱</div>
                  <p class="text-white font-bold text-[24px]">微信小程序</p>
                  <p class="text-purple-200 text-[15px] mt-2">42 页 · uni-app</p>
                </div>
              </div>
              <div class="absolute w-full h-full bg-purple-700/60 border-2 border-purple-500" style="transform: rotateY(90deg) translateZ(120px);"></div>
              <div class="absolute w-full h-full bg-purple-500/40 border-2 border-purple-600" style="transform: rotateX(90deg) translateZ(120px);"></div>
            </div>

            <div class="relative w-60 h-60" style="transform-style: preserve-3d; transform: rotateX(-15deg) rotateY(-25deg);">
              <div class="absolute w-full h-full bg-emerald-600/80 border-2 border-emerald-400 flex items-center justify-center" style="transform: translateZ(120px);">
                <div class="text-center">
                  <div class="text-[34px] mb-2">⚙️</div>
                  <p class="text-white font-bold text-[24px]">管理后台</p>
                  <p class="text-emerald-200 text-[15px] mt-2">16 页 · Element</p>
                </div>
              </div>
              <div class="absolute w-full h-full bg-emerald-700/60 border-2 border-emerald-500" style="transform: rotateY(90deg) translateZ(120px);"></div>
              <div class="absolute w-full h-full bg-emerald-500/40 border-2 border-emerald-600" style="transform: rotateX(90deg) translateZ(120px);"></div>
            </div>
          </div>
        </div>

        <div class="mt-16 flex justify-center gap-28 relative z-10">
          <div class="text-center">
            <p class="text-[36px] font-bold text-cyan-400 mb-2 font-mono">47,736</p>
            <p class="text-gray-400 text-[16px]">前端代码行数</p>
          </div>
          <div class="text-center">
            <p class="text-[36px] font-bold text-purple-400 mb-2 font-mono">121</p>
            <p class="text-gray-400 text-[16px]">后端接口端点</p>
          </div>
          <div class="text-center">
            <p class="text-[36px] font-bold text-emerald-400 mb-2 font-mono">373</p>
            <p class="text-gray-400 text-[16px]">菜谱语料篇数</p>
          </div>
        </div>
      </div>
    </div>
  </div>
`);window.slideDataMap.set(6,`
  <div class="w-[1440px] h-[810px] shadow-2xl relative overflow-hidden slide-bg">
    <div class="absolute inset-0 opacity-10" style="background-image: repeating-linear-gradient(0deg, transparent, transparent 40px, #22d3ee 40px, #22d3ee 41px), repeating-linear-gradient(90deg, transparent, transparent 40px, #22d3ee 40px, #22d3ee 41px);"></div>
    <div class="w-full h-full flex items-center justify-center relative">
      <div class="w-[1350px] h-[720px] mx-auto p-10 flex flex-col items-center justify-center relative">
        <h2 class="text-[40px] font-bold text-cyan-400 mb-1">系统架构总览</h2>
        <p class="text-[16px] text-gray-400 font-mono mb-8">五层架构 · 22 节点编排 · 输入输出双闸门风控</p>

        <svg class="w-full max-w-5xl h-[380px]" viewBox="0 0 1000 400">
          <defs>
            <radialGradient id="nodeGrad1">
              <stop offset="0%" style="stop-color:#22d3ee;stop-opacity:1" />
              <stop offset="100%" style="stop-color:#0e7490;stop-opacity:1" />
            </radialGradient>
            <radialGradient id="nodeGrad2">
              <stop offset="0%" style="stop-color:#8b5cf6;stop-opacity:1" />
              <stop offset="100%" style="stop-color:#4c1d95;stop-opacity:1" />
            </radialGradient>
            <radialGradient id="nodeGrad3">
              <stop offset="0%" style="stop-color:#10b981;stop-opacity:1" />
              <stop offset="100%" style="stop-color:#065f46;stop-opacity:1" />
            </radialGradient>
          </defs>

          <g opacity="0.35">
            <line x1="100" y1="100" x2="300" y2="80" stroke="#22d3ee" stroke-width="1"/>
            <line x1="100" y1="100" x2="300" y2="160" stroke="#22d3ee" stroke-width="1"/>
            <line x1="100" y1="100" x2="300" y2="240" stroke="#22d3ee" stroke-width="1"/>
            <line x1="100" y1="100" x2="300" y2="320" stroke="#22d3ee" stroke-width="1"/>
            <line x1="100" y1="200" x2="300" y2="80" stroke="#22d3ee" stroke-width="1"/>
            <line x1="100" y1="200" x2="300" y2="160" stroke="#22d3ee" stroke-width="1"/>
            <line x1="100" y1="200" x2="300" y2="240" stroke="#22d3ee" stroke-width="1"/>
            <line x1="100" y1="200" x2="300" y2="320" stroke="#22d3ee" stroke-width="1"/>
            <line x1="100" y1="300" x2="300" y2="80" stroke="#22d3ee" stroke-width="1"/>
            <line x1="100" y1="300" x2="300" y2="160" stroke="#22d3ee" stroke-width="1"/>
            <line x1="100" y1="300" x2="300" y2="240" stroke="#22d3ee" stroke-width="1"/>
            <line x1="100" y1="300" x2="300" y2="320" stroke="#22d3ee" stroke-width="1"/>
            <line x1="300" y1="80" x2="500" y2="120" stroke="#8b5cf6" stroke-width="1"/>
            <line x1="300" y1="160" x2="500" y2="200" stroke="#8b5cf6" stroke-width="1"/>
            <line x1="300" y1="240" x2="500" y2="280" stroke="#8b5cf6" stroke-width="1"/>
            <line x1="500" y1="120" x2="700" y2="160" stroke="#10b981" stroke-width="1"/>
            <line x1="500" y1="200" x2="700" y2="240" stroke="#10b981" stroke-width="1"/>
            <line x1="700" y1="160" x2="900" y2="200" stroke="#f59e0b" stroke-width="2"/>
            <line x1="700" y1="240" x2="900" y2="200" stroke="#f59e0b" stroke-width="2"/>
          </g>

          <circle cx="100" cy="100" r="25" fill="url(#nodeGrad1)" stroke="#22d3ee" stroke-width="2"/>
          <text x="100" y="106" text-anchor="middle" fill="#fff" font-size="14" font-weight="bold">Web</text>
          <circle cx="100" cy="200" r="25" fill="url(#nodeGrad1)" stroke="#22d3ee" stroke-width="2"/>
          <text x="100" y="206" text-anchor="middle" fill="#fff" font-size="14" font-weight="bold">MP</text>
          <circle cx="100" cy="300" r="25" fill="url(#nodeGrad1)" stroke="#22d3ee" stroke-width="2"/>
          <text x="100" y="306" text-anchor="middle" fill="#fff" font-size="14" font-weight="bold">ADM</text>

          <circle cx="300" cy="80" r="20" fill="url(#nodeGrad2)" stroke="#8b5cf6" stroke-width="2"/>
          <circle cx="300" cy="160" r="20" fill="url(#nodeGrad2)" stroke="#8b5cf6" stroke-width="2"/>
          <circle cx="300" cy="240" r="20" fill="url(#nodeGrad2)" stroke="#8b5cf6" stroke-width="2"/>
          <circle cx="300" cy="320" r="20" fill="url(#nodeGrad2)" stroke="#8b5cf6" stroke-width="2"/>

          <circle cx="500" cy="120" r="20" fill="url(#nodeGrad2)" stroke="#8b5cf6" stroke-width="2"/>
          <circle cx="500" cy="200" r="20" fill="url(#nodeGrad2)" stroke="#8b5cf6" stroke-width="2"/>
          <circle cx="500" cy="280" r="20" fill="url(#nodeGrad2)" stroke="#8b5cf6" stroke-width="2"/>

          <circle cx="700" cy="160" r="20" fill="url(#nodeGrad3)" stroke="#10b981" stroke-width="2"/>
          <circle cx="700" cy="240" r="20" fill="url(#nodeGrad3)" stroke="#10b981" stroke-width="2"/>

          <circle cx="900" cy="200" r="28" fill="#f59e0b" stroke="#fbbf24" stroke-width="3"/>
          <text x="900" y="206" text-anchor="middle" fill="#111827" font-size="15" font-weight="bold">DB</text>

          <text x="100" y="42" text-anchor="middle" fill="#22d3ee" font-size="15">用户侧三端</text>
          <text x="300" y="368" text-anchor="middle" fill="#8b5cf6" font-size="15">接入层</text>
          <text x="500" y="368" text-anchor="middle" fill="#8b5cf6" font-size="15">应用层</text>
          <text x="700" y="368" text-anchor="middle" fill="#10b981" font-size="15">编排 · 风控</text>
          <text x="900" y="368" text-anchor="middle" fill="#f59e0b" font-size="15">数据层</text>

          <text x="100" y="63" text-anchor="middle" fill="#64748b" font-size="12">Web / 小程序 / 后台</text>
          <text x="300" y="388" text-anchor="middle" fill="#64748b" font-size="12">Nginx · 8005</text>
          <text x="500" y="388" text-anchor="middle" fill="#64748b" font-size="12">121 接口端点</text>
          <text x="700" y="388" text-anchor="middle" fill="#64748b" font-size="12">22 节点 · 双闸门</text>
          <text x="900" y="388" text-anchor="middle" fill="#64748b" font-size="12">PG16 · pgvector</text>
        </svg>

        <div class="mt-6 flex gap-16">
          <div class="text-center">
            <p class="text-[30px] font-bold text-cyan-400 mb-1 font-mono">3</p>
            <p class="text-gray-400 text-[15px]">交付端</p>
          </div>
          <div class="text-center">
            <p class="text-[30px] font-bold text-purple-400 mb-1 font-mono">121</p>
            <p class="text-gray-400 text-[15px]">接口端点</p>
          </div>
          <div class="text-center">
            <p class="text-[30px] font-bold text-emerald-400 mb-1 font-mono">22</p>
            <p class="text-gray-400 text-[15px]">编排节点</p>
          </div>
          <div class="text-center">
            <p class="text-[30px] font-bold text-amber-400 mb-1 font-mono">27</p>
            <p class="text-gray-400 text-[15px]">风控规则</p>
          </div>
        </div>
      </div>
    </div>
  </div>
`);window.slideDataMap.set(7,`
  <div class="w-[1440px] h-[810px] shadow-2xl relative overflow-hidden slide-bg">
    <svg class="absolute inset-0 w-full h-full opacity-20" viewBox="0 0 1280 720">
      <line x1="0" y1="100" x2="400" y2="100" stroke="#22d3ee" stroke-width="2"/>
      <line x1="500" y1="100" x2="800" y2="100" stroke="#22d3ee" stroke-width="2"/>
      <line x1="900" y1="100" x2="1280" y2="100" stroke="#22d3ee" stroke-width="2"/>
      <line x1="0" y1="300" x2="300" y2="300" stroke="#0ea5e9" stroke-width="2"/>
      <line x1="450" y1="300" x2="850" y2="300" stroke="#0ea5e9" stroke-width="2"/>
      <line x1="950" y1="300" x2="1280" y2="300" stroke="#0ea5e9" stroke-width="2"/>
      <line x1="0" y1="500" x2="500" y2="500" stroke="#22d3ee" stroke-width="2"/>
      <line x1="600" y1="500" x2="900" y2="500" stroke="#22d3ee" stroke-width="2"/>
      <line x1="1000" y1="500" x2="1280" y2="500" stroke="#22d3ee" stroke-width="2"/>
      <line x1="200" y1="0" x2="200" y2="250" stroke="#22d3ee" stroke-width="2"/>
      <line x1="200" y1="350" x2="200" y2="720" stroke="#22d3ee" stroke-width="2"/>
      <line x1="1080" y1="0" x2="1080" y2="350" stroke="#0ea5e9" stroke-width="2"/>
      <line x1="1080" y1="500" x2="1080" y2="720" stroke="#0ea5e9" stroke-width="2"/>
      <circle cx="200" cy="300" r="6" fill="#22d3ee"/>
      <circle cx="1080" cy="300" r="6" fill="#0ea5e9"/>
    </svg>

    <div class="w-full h-full flex items-center justify-center relative">
      <div class="w-[1350px] h-[720px] mx-auto p-10 flex items-center justify-center relative">
        <h2 class="absolute top-8 left-1/2 transform -translate-x-1/2 text-[40px] font-bold text-cyan-400 z-10">技术栈选型</h2>
        <p class="absolute top-[74px] left-1/2 transform -translate-x-1/2 text-[16px] text-gray-400 font-mono z-10">一个核心服务 + 四类技术支撑 · 外部能力全部 Provider 化</p>

        <div class="relative w-[980px] h-[470px] mt-10">
          <div class="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 w-[268px] h-[268px] border-4 border-cyan-400 bg-slate-900" style="box-shadow: 0 0 60px rgba(34,211,238,0.45);">
            <div class="absolute inset-4 border-2 border-cyan-500/50"></div>
            <div class="absolute inset-8 border border-cyan-500/30"></div>
            <div class="absolute inset-0 flex items-center justify-center">
              <div class="text-center">
                <div class="text-[30px] mb-2 text-cyan-400 font-mono">{ }</div>
                <p class="text-[28px] font-bold text-white tracking-wider">FASTAPI</p>
                <p class="text-cyan-400 text-[14px] mt-2">Python 3.11 · 121 接口</p>
                <p class="text-cyan-400/80 text-[13px] mt-1">SQLAlchemy · Pydantic</p>
              </div>
            </div>

            <div class="absolute left-0 top-0 bottom-0 flex flex-col justify-around -translate-x-full pr-2">
              <div class="w-8 h-2 bg-cyan-400"></div>
              <div class="w-8 h-2 bg-cyan-400"></div>
              <div class="w-8 h-2 bg-cyan-400"></div>
              <div class="w-8 h-2 bg-cyan-400"></div>
            </div>
            <div class="absolute right-0 top-0 bottom-0 flex flex-col justify-around translate-x-full pl-2">
              <div class="w-8 h-2 bg-cyan-400"></div>
              <div class="w-8 h-2 bg-cyan-400"></div>
              <div class="w-8 h-2 bg-cyan-400"></div>
              <div class="w-8 h-2 bg-cyan-400"></div>
            </div>
            <div class="absolute top-0 left-0 right-0 flex justify-around -translate-y-full pb-2">
              <div class="w-2 h-8 bg-cyan-400"></div>
              <div class="w-2 h-8 bg-cyan-400"></div>
              <div class="w-2 h-8 bg-cyan-400"></div>
              <div class="w-2 h-8 bg-cyan-400"></div>
            </div>
            <div class="absolute bottom-0 left-0 right-0 flex justify-around translate-y-full pt-2">
              <div class="w-2 h-8 bg-cyan-400"></div>
              <div class="w-2 h-8 bg-cyan-400"></div>
              <div class="w-2 h-8 bg-cyan-400"></div>
              <div class="w-2 h-8 bg-cyan-400"></div>
            </div>
          </div>

          <div class="absolute top-0 left-0 w-[190px] h-[130px] border-2 border-cyan-400 bg-slate-800/90 p-4 text-center">
            <p class="text-cyan-400 text-[20px] font-bold mb-1">前端三端</p>
            <p class="text-gray-300 text-[13px]">Vue 3 · uni-app</p>
            <div class="mt-2 text-[24px]">🖥️</div>
          </div>

          <div class="absolute top-0 right-0 w-[190px] h-[130px] border-2 border-purple-400 bg-slate-800/90 p-4 text-center">
            <p class="text-purple-400 text-[20px] font-bold mb-1">编排引擎</p>
            <p class="text-gray-300 text-[13px]">LangGraph 多智能体</p>
            <div class="mt-2 text-[24px]">🕸️</div>
          </div>

          <div class="absolute bottom-0 left-0 w-[190px] h-[130px] border-2 border-emerald-400 bg-slate-800/90 p-4 text-center">
            <p class="text-emerald-400 text-[20px] font-bold mb-1">数据存储</p>
            <p class="text-gray-300 text-[13px]">PG16 · pgvector</p>
            <div class="mt-2 text-[24px]">🗄️</div>
          </div>

          <div class="absolute bottom-0 right-0 w-[190px] h-[130px] border-2 border-amber-400 bg-slate-800/90 p-4 text-center">
            <p class="text-amber-400 text-[20px] font-bold mb-1">外部能力</p>
            <p class="text-gray-300 text-[13px]">LLM · VLM · ASR · TTS</p>
            <div class="mt-2 text-[24px]">🔌</div>
          </div>

          <svg class="absolute inset-0 w-full h-full pointer-events-none">
            <line x1="190" y1="65" x2="356" y2="205" stroke="#22d3ee" stroke-width="2" stroke-dasharray="5,5"/>
            <line x1="790" y1="65" x2="624" y2="205" stroke="#a78bfa" stroke-width="2" stroke-dasharray="5,5"/>
            <line x1="190" y1="405" x2="356" y2="265" stroke="#10b981" stroke-width="2" stroke-dasharray="5,5"/>
            <line x1="790" y1="405" x2="624" y2="265" stroke="#f59e0b" stroke-width="2" stroke-dasharray="5,5"/>
          </svg>
        </div>
      </div>
    </div>
  </div>
`);window.slideDataMap.set(8,`
  <div class="w-[1440px] h-[810px] shadow-2xl relative overflow-hidden slide-bg">
    <div class="w-[1350px] h-[720px] mx-auto my-[45px] relative">
      <div class="absolute inset-0 opacity-20" style="background-image: linear-gradient(rgba(34,211,238,0.1) 1px, transparent 1px), linear-gradient(90deg, rgba(34,211,238,0.1) 1px, transparent 1px); background-size: 40px 40px;"></div>
      <div class="absolute top-1/2 left-0 right-0 h-px bg-cyan-400/60"></div>
      <div class="absolute top-1/2 left-0 right-0 h-16 bg-cyan-500/10"></div>
      <div class="relative z-10 flex items-center justify-center h-full">
        <div class="text-center">
          <div class="text-[52px] font-bold text-cyan-500 mb-6 font-mono">
            <span class="inline-block border-2 border-cyan-500 px-8 py-3">&lt; 02 /&gt;</span>
          </div>
          <h1 class="text-[56px] font-bold text-white mb-4 tracking-[0.1em]">重点模块与精彩代码</h1>
          <p class="text-[22px] text-cyan-400 tracking-[0.12em]">3 个核心模块 + 2 段关键实现</p>
          <div class="flex items-center justify-center gap-2 mt-8">
            <div class="w-2 h-2 bg-cyan-400 rounded-full animate-pulse"></div>
            <div class="w-2 h-2 bg-cyan-400 rounded-full animate-pulse" style="animation-delay: 0.2s;"></div>
            <div class="w-2 h-2 bg-cyan-400 rounded-full animate-pulse" style="animation-delay: 0.4s;"></div>
          </div>
        </div>
      </div>
    </div>
  </div>
`);window.slideDataMap.set(9,`
  <div class="w-[1440px] h-[810px] shadow-2xl relative overflow-hidden slide-bg">
    <div class="absolute inset-0 opacity-10" style="background-image: repeating-linear-gradient(0deg, transparent, transparent 40px, #22d3ee 40px, #22d3ee 41px), repeating-linear-gradient(90deg, transparent, transparent 40px, #22d3ee 40px, #22d3ee 41px);"></div>
    <div class="w-full h-full flex items-center justify-center relative">
      <div class="w-[1350px] h-[720px] mx-auto p-10 flex items-center justify-center relative">
        <h2 class="absolute top-8 left-1/2 transform -translate-x-1/2 text-[40px] font-bold text-cyan-400 z-10">重点模块① 智能菜谱推荐</h2>
        <p class="absolute top-[74px] left-1/2 transform -translate-x-1/2 text-[16px] text-gray-400 font-mono z-10">LangGraph 推荐子图 5 节点 · 全程不调用大模型 · 确定性可审计</p>

        <div class="relative w-full max-w-6xl mt-12">
          <svg class="w-full h-[470px]" viewBox="0 0 1000 400">
            <defs>
              <linearGradient id="lineGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" style="stop-color:#22d3ee;stop-opacity:1" />
                <stop offset="100%" style="stop-color:#0ea5e9;stop-opacity:1" />
              </linearGradient>
              <marker id="arrowhead" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto">
                <polygon points="0 0, 10 3, 0 6" fill="#22d3ee" />
              </marker>
            </defs>

            <path d="M 150 210 L 215 210" stroke="url(#lineGrad)" stroke-width="3" marker-end="url(#arrowhead)"/>
            <path d="M 325 210 L 390 210" stroke="url(#lineGrad)" stroke-width="3" marker-end="url(#arrowhead)"/>
            <path d="M 500 210 L 565 210" stroke="url(#lineGrad)" stroke-width="3" marker-end="url(#arrowhead)"/>
            <path d="M 675 210 L 740 210" stroke="url(#lineGrad)" stroke-width="3" marker-end="url(#arrowhead)"/>

            <circle r="4" fill="#22d3ee">
              <animateMotion dur="4s" repeatCount="indefinite" path="M 150 210 L 225 210 L 325 210 L 400 210 L 500 210 L 575 210 L 675 210 L 800 210"/>
            </circle>

            <g>
              <rect x="50" y="160" width="100" height="100" rx="10" fill="#0f172a" stroke="#22d3ee" stroke-width="2"/>
              <text x="100" y="197" text-anchor="middle" fill="#22d3ee" font-size="17" font-weight="bold">上下文</text>
              <text x="100" y="219" text-anchor="middle" fill="#22d3ee" font-size="17" font-weight="bold">归一</text>
              <text x="100" y="243" text-anchor="middle" fill="#64748b" font-size="12">assemble</text>
            </g>

            <g>
              <rect x="225" y="160" width="100" height="100" rx="10" fill="#0f172a" stroke="#0ea5e9" stroke-width="2"/>
              <text x="275" y="197" text-anchor="middle" fill="#0ea5e9" font-size="17" font-weight="bold">三路</text>
              <text x="275" y="219" text-anchor="middle" fill="#0ea5e9" font-size="17" font-weight="bold">混合召回</text>
              <text x="275" y="243" text-anchor="middle" fill="#64748b" font-size="12">retrieve</text>
            </g>

            <g>
              <rect x="400" y="160" width="100" height="100" rx="10" fill="#0f172a" stroke="#8b5cf6" stroke-width="2"/>
              <text x="450" y="197" text-anchor="middle" fill="#8b5cf6" font-size="17" font-weight="bold">布尔</text>
              <text x="450" y="219" text-anchor="middle" fill="#8b5cf6" font-size="17" font-weight="bold">硬过滤</text>
              <text x="450" y="243" text-anchor="middle" fill="#64748b" font-size="12">hard_filter</text>
            </g>

            <g>
              <rect x="575" y="160" width="100" height="100" rx="10" fill="#0f172a" stroke="#10b981" stroke-width="2"/>
              <text x="625" y="197" text-anchor="middle" fill="#10b981" font-size="17" font-weight="bold">7 因子</text>
              <text x="625" y="219" text-anchor="middle" fill="#10b981" font-size="17" font-weight="bold">加权排序</text>
              <text x="625" y="243" text-anchor="middle" fill="#64748b" font-size="12">rank</text>
            </g>

            <g>
              <rect x="750" y="160" width="100" height="100" rx="10" fill="#0f172a" stroke="#f59e0b" stroke-width="2"/>
              <text x="800" y="197" text-anchor="middle" fill="#f59e0b" font-size="17" font-weight="bold">营养</text>
              <text x="800" y="219" text-anchor="middle" fill="#f59e0b" font-size="17" font-weight="bold">估算</text>
              <text x="800" y="243" text-anchor="middle" fill="#64748b" font-size="12">nutrition</text>
            </g>

            <g>
              <text x="100" y="126" text-anchor="middle" fill="#94a3b8" font-size="15">食材与文本</text>
              <text x="275" y="126" text-anchor="middle" fill="#94a3b8" font-size="15">覆盖率·文本·向量</text>
              <text x="450" y="126" text-anchor="middle" fill="#94a3b8" font-size="15">过敏原·忌口·难度·设备</text>
              <text x="625" y="126" text-anchor="middle" fill="#94a3b8" font-size="15">输出 rank_reasons</text>
              <text x="800" y="126" text-anchor="middle" fill="#94a3b8" font-size="15">与排序并行</text>
            </g>

            <g>
              <text x="100" y="300" text-anchor="middle" fill="#22d3ee" font-size="24" font-weight="bold">3 路</text>
              <text x="275" y="300" text-anchor="middle" fill="#0ea5e9" font-size="24" font-weight="bold">4 维</text>
              <text x="450" y="300" text-anchor="middle" fill="#8b5cf6" font-size="24" font-weight="bold">7 因子</text>
              <text x="625" y="300" text-anchor="middle" fill="#10b981" font-size="24" font-weight="bold">Top 8</text>
              <text x="800" y="300" text-anchor="middle" fill="#f59e0b" font-size="24" font-weight="bold">0 LLM</text>
            </g>

            <g>
              <text x="100" y="324" text-anchor="middle" fill="#475569" font-size="13">召回通道</text>
              <text x="275" y="324" text-anchor="middle" fill="#475569" font-size="13">过滤维度</text>
              <text x="450" y="324" text-anchor="middle" fill="#475569" font-size="13">排序因子</text>
              <text x="625" y="324" text-anchor="middle" fill="#475569" font-size="13">结果上限</text>
              <text x="800" y="324" text-anchor="middle" fill="#475569" font-size="13">大模型调用</text>
            </g>
          </svg>
        </div>

        <div class="absolute bottom-12 left-1/2 transform -translate-x-1/2 text-center">
          <p class="text-cyan-400 text-[18px] font-mono">DETERMINISTIC · EXPLAINABLE · AUDITABLE</p>
          <p class="text-gray-500 text-[15px] mt-1">匹配不足时如实说明不凑数 · 被过滤菜谱可逐条重放原因</p>
        </div>
      </div>
    </div>
  </div>
`);window.slideDataMap.set(10,`
  <div class="w-[1440px] h-[810px] shadow-2xl relative overflow-hidden slide-bg">
    <div class="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2">
      <svg class="w-[680px] h-[680px]" viewBox="0 0 600 600">
        <circle cx="300" cy="300" r="250" fill="none" stroke="#22d3ee" stroke-width="1" opacity="0.3"/>
        <circle cx="300" cy="300" r="200" fill="none" stroke="#22d3ee" stroke-width="1" opacity="0.4"/>
        <circle cx="300" cy="300" r="150" fill="none" stroke="#22d3ee" stroke-width="1" opacity="0.5"/>
        <circle cx="300" cy="300" r="100" fill="none" stroke="#22d3ee" stroke-width="1" opacity="0.6"/>
        <circle cx="300" cy="300" r="50" fill="none" stroke="#22d3ee" stroke-width="2" opacity="0.7"/>
        <line x1="50" y1="300" x2="550" y2="300" stroke="#22d3ee" stroke-width="1" opacity="0.3"/>
        <line x1="300" y1="50" x2="300" y2="550" stroke="#22d3ee" stroke-width="1" opacity="0.3"/>
        <line x1="121" y1="121" x2="479" y2="479" stroke="#22d3ee" stroke-width="1" opacity="0.2"/>
        <line x1="479" y1="121" x2="121" y2="479" stroke="#22d3ee" stroke-width="1" opacity="0.2"/>
        <defs>
          <linearGradient id="scanGradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" style="stop-color:#22d3ee;stop-opacity:0" />
            <stop offset="100%" style="stop-color:#22d3ee;stop-opacity:0.6" />
          </linearGradient>
        </defs>
        <g style="transform-origin: center; animation: rotate 4s linear infinite;">
          <path d="M 300 300 L 300 50 A 250 250 0 0 1 477 123 Z" fill="url(#scanGradient)" opacity="0.4"/>
        </g>
      </svg>
    </div>
    <style>
      @keyframes rotate { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
    </style>

    <div class="w-full h-full flex items-center justify-center relative">
      <div class="w-[1350px] h-[720px] mx-auto p-10 flex items-center justify-center relative">
        <h2 class="absolute top-8 left-1/2 transform -translate-x-1/2 text-[40px] font-bold text-cyan-400 z-10">重点模块② 食品安全与过敏原风控</h2>
        <p class="absolute top-[74px] left-1/2 transform -translate-x-1/2 text-[16px] text-gray-400 font-mono z-10">纯规则引擎 · 不调用大模型 · 一票否决 = 控制流短路</p>

        <div class="relative w-full max-w-5xl h-[430px] mt-8">
          <div class="absolute" style="top: 4%; left: 2%;">
            <div class="relative">
              <div class="w-4 h-4 bg-red-500 rounded-full animate-ping"></div>
              <div class="w-4 h-4 bg-red-500 rounded-full absolute top-0"></div>
              <div class="absolute top-6 left-6 bg-black/90 border border-red-500 p-3 rounded min-w-[220px]">
                <p class="text-red-400 font-bold text-[17px] mb-1">食品安全高风险 · 阻断</p>
                <p class="text-gray-300 text-[14px] font-mono">FS- 11 条规则</p>
                <p class="text-red-500 text-[14px] mt-1">发芽土豆 / 久泡木耳 / 未熟四季豆</p>
              </div>
            </div>
          </div>

          <div class="absolute" style="top: 0%; right: 2%;">
            <div class="relative">
              <div class="w-3 h-3 bg-yellow-500 rounded-full animate-pulse"></div>
              <div class="absolute top-6 right-0 bg-black/90 border border-yellow-500 p-3 rounded min-w-[220px]">
                <p class="text-yellow-400 font-bold text-[17px] mb-1">医疗拒答 · 阻断</p>
                <p class="text-gray-300 text-[14px] font-mono">MR- 4 条规则</p>
                <p class="text-yellow-500 text-[14px] mt-1">诊断 / 治疗类诉求一律拒答</p>
              </div>
            </div>
          </div>

          <div class="absolute" style="bottom: 4%; left: 2%;">
            <div class="relative">
              <div class="w-3 h-3 bg-green-500 rounded-full"></div>
              <div class="absolute bottom-6 left-0 bg-black/90 border border-green-500 p-3 rounded min-w-[220px]">
                <p class="text-green-400 font-bold text-[17px] mb-1">伪科学 / 相克 · 仅提示</p>
                <p class="text-gray-300 text-[14px] font-mono">PS- 2 条规则</p>
                <p class="text-green-500 text-[14px] mt-1">不阻断，只做风险提示</p>
              </div>
            </div>
          </div>

          <div class="absolute" style="bottom: 4%; right: 2%;">
            <div class="relative">
              <div class="w-3 h-3 bg-blue-500 rounded-full"></div>
              <div class="absolute bottom-6 right-0 bg-black/90 border border-blue-500 p-3 rounded min-w-[220px]">
                <p class="text-blue-400 font-bold text-[17px] mb-1">输出禁用表述 · 阻断</p>
                <p class="text-gray-300 text-[14px] font-mono">OB- 5 条规则</p>
                <p class="text-blue-500 text-[14px] mt-1">绝对化用语 / 安全承诺 / 违禁词</p>
              </div>
            </div>
          </div>
        </div>

        <div class="absolute bottom-8 left-1/2 transform -translate-x-1/2 w-full max-w-5xl">
          <div class="bg-slate-900/90 border border-cyan-500/30 rounded-lg p-5">
            <div class="flex justify-between items-center">
              <div class="flex items-center gap-3">
                <div class="w-3 h-3 bg-green-500 rounded-full animate-pulse"></div>
                <span class="text-green-400 font-mono text-[15px]">RULESET v1.0 · ACTIVE</span>
              </div>
              <div class="flex gap-10">
                <div class="text-center">
                  <p class="text-cyan-400 text-[22px] font-bold font-mono">27</p>
                  <p class="text-gray-400 text-[14px]">风控规则</p>
                </div>
                <div class="text-center">
                  <p class="text-green-400 text-[22px] font-bold font-mono">12</p>
                  <p class="text-gray-400 text-[14px]">安全红线全绿</p>
                </div>
                <div class="text-center">
                  <p class="text-purple-400 text-[22px] font-bold font-mono">2</p>
                  <p class="text-gray-400 text-[14px]">输入输出闸门</p>
                </div>
                <div class="text-center">
                  <p class="text-amber-400 text-[22px] font-bold font-mono">0</p>
                  <p class="text-gray-400 text-[14px]">大模型调用</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
`);window.slideDataMap.set(11,`
  <div class="w-[1440px] h-[810px] shadow-2xl relative overflow-hidden slide-bg">
    <div class="absolute inset-0" style="background-image: repeating-linear-gradient(0deg, transparent 0px, transparent 19px, rgba(34,211,238,0.05) 19px, rgba(34,211,238,0.05) 20px), repeating-linear-gradient(90deg, transparent 0px, transparent 19px, rgba(34,211,238,0.05) 19px, rgba(34,211,238,0.05) 20px);"></div>

    <div class="w-full h-full flex items-center justify-center relative">
      <div class="w-[1350px] h-[720px] mx-auto p-10 flex items-center justify-center relative">
        <h2 class="absolute top-8 left-1/2 transform -translate-x-1/2 text-[40px] font-bold text-cyan-400 z-10">重点模块③ 中枢调度</h2>
        <p class="absolute top-[74px] left-1/2 transform -translate-x-1/2 text-[16px] text-gray-400 font-mono z-10">22 节点 · 全图仅 1 个 LLM 节点 · 3 个终止出口</p>

        <div class="relative w-full max-w-6xl h-[470px] mt-6">
          <div class="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2">
            <div class="relative w-[190px] h-[190px]">
              <svg class="w-full h-full" viewBox="0 0 200 200" style="animation: spin-slow 20s linear infinite;">
                <circle cx="100" cy="100" r="90" fill="none" stroke="#22d3ee" stroke-width="2" opacity="0.6"/>
                <circle cx="100" cy="100" r="72" fill="none" stroke="#0ea5e9" stroke-width="1.5" opacity="0.5"/>
                <circle cx="100" cy="100" r="54" fill="none" stroke="#a78bfa" stroke-width="1.5" opacity="0.45"/>
                <ellipse cx="100" cy="100" rx="90" ry="30" fill="none" stroke="#22d3ee" stroke-width="1" opacity="0.3"/>
                <ellipse cx="100" cy="100" rx="90" ry="50" fill="none" stroke="#22d3ee" stroke-width="1" opacity="0.25"/>
                <ellipse cx="100" cy="100" rx="30" ry="90" fill="none" stroke="#0ea5e9" stroke-width="1" opacity="0.3"/>
                <ellipse cx="100" cy="100" rx="50" ry="90" fill="none" stroke="#0ea5e9" stroke-width="1" opacity="0.25"/>
                <circle cx="100" cy="100" r="14" fill="#22d3ee" opacity="0.85">
                  <animate attributeName="r" values="12;18;12" dur="2s" repeatCount="indefinite"/>
                  <animate attributeName="opacity" values="0.9;0.5;0.9" dur="2s" repeatCount="indefinite"/>
                </circle>
              </svg>
              <div class="absolute inset-0 flex items-center justify-center">
                <p class="text-white font-bold text-[17px] tracking-wide" style="text-shadow: 0 0 14px rgba(0,0,0,0.9);">supervisor</p>
              </div>
            </div>
            <p class="text-center text-cyan-400 text-[13px] font-mono mt-2">全图唯一 LLM 节点</p>
          </div>

          <div class="absolute top-0 left-0 w-[320px] h-[175px] bg-slate-900/85 border-2 border-cyan-400/60 rounded-lg p-4">
            <p class="text-cyan-400 text-[19px] font-bold mb-2">① 意图路由</p>
            <div class="space-y-2">
              <p class="text-gray-300 text-[14px] leading-snug">LLM <span class="text-cyan-300 font-bold">只做意图识别</span>，不做回答</p>
              <p class="text-gray-300 text-[14px] leading-snug">路由由 <span class="text-cyan-300 font-mono">INTENT_ROUTES</span> 字典决定</p>
              <p class="text-gray-300 text-[14px] leading-snug">LLM 不决定调用哪个工具 → 消除幻觉选工具</p>
            </div>
          </div>

          <div class="absolute top-0 right-0 w-[320px] h-[175px] bg-slate-900/85 border-2 border-purple-400/60 rounded-lg p-4">
            <p class="text-purple-400 text-[19px] font-bold mb-2">② 风控双闸门</p>
            <div class="space-y-2">
              <p class="text-gray-300 text-[14px] leading-snug">输入侧 <span class="text-purple-300 font-mono">intake_guard</span></p>
              <p class="text-gray-300 text-[14px] leading-snug">输出侧 <span class="text-purple-300 font-mono">output_guard</span></p>
              <p class="text-gray-300 text-[14px] leading-snug">各节点入口检查 <span class="text-purple-300 font-mono">overrides_all</span></p>
            </div>
          </div>

          <div class="absolute bottom-0 left-0 w-[320px] h-[175px] bg-slate-900/85 border-2 border-emerald-400/60 rounded-lg p-4">
            <p class="text-emerald-400 text-[19px] font-bold mb-2">③ 降级与出口</p>
            <div class="space-y-2">
              <p class="text-gray-300 text-[14px] leading-snug">LLM 报错 → 关键词兜底分类</p>
              <p class="text-gray-300 text-[14px] leading-snug">trace 标记 <span class="text-emerald-300 font-mono">degraded</span></p>
              <p class="text-gray-300 text-[14px] leading-snug">3 个终止出口（含 safe_mode 保守模式）</p>
            </div>
          </div>

          <div class="absolute bottom-0 right-0 w-[320px] h-[175px] bg-slate-900/85 border-2 border-amber-400/60 rounded-lg p-4">
            <p class="text-amber-400 text-[19px] font-bold mb-2">④ 全链路可观测</p>
            <div class="space-y-2">
              <p class="text-gray-300 text-[14px] leading-snug">记录节点 / 耗时 / 风控规则 ID</p>
              <p class="text-gray-300 text-[14px] leading-snug">记录未执行节点 <span class="text-amber-300 font-mono">skipped_by_veto</span></p>
              <p class="text-gray-300 text-[14px] leading-snug">记录 token 与成本，可回放</p>
            </div>
          </div>
        </div>

        <div class="absolute bottom-6 left-1/2 transform -translate-x-1/2 text-center">
          <p class="text-cyan-400 font-mono text-[16px]">AGENT_REGISTRY · DYNAMIC ASSEMBLY</p>
          <p class="text-gray-500 text-[14px] mt-1">节点按注册表动态装配 —— 新增 Agent 只需注册，不改装配逻辑</p>
        </div>
      </div>
    </div>
    <style>
      @keyframes spin-slow { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
    </style>
  </div>
`);window.slideDataMap.set(12,`
  <div class="w-[1440px] h-[810px] shadow-2xl relative overflow-hidden slide-bg">
    <div class="absolute inset-0 overflow-hidden opacity-10 font-mono text-green-400 text-[12px]">
      <div class="absolute left-[5%] top-0" style="animation: scroll 8s linear infinite;">01001010<br/>11010110<br/>00110101<br/>10101100<br/>01110011<br/>11001010<br/>00101101<br/>10110110</div>
      <div class="absolute left-[25%] top-0" style="animation: scroll 10s linear infinite;">SELECT *<br/>FROM db<br/>WHERE id<br/>JOIN ON<br/>GROUP BY<br/>ORDER BY<br/>LIMIT 8<br/>OFFSET 0</div>
      <div class="absolute left-[45%] top-0" style="animation: scroll 7s linear infinite;">0xFFA500<br/>0x22D3EE<br/>0xFF0000<br/>0x10B981<br/>0x0000FF<br/>0xA78BFA<br/>0xFF00FF<br/>0xFFFFFF</div>
      <div class="absolute left-[65%] top-0" style="animation: scroll 9s linear infinite;">async def<br/>await<br/>yield<br/>return<br/>raise<br/>assert<br/>lambda<br/>import</div>
      <div class="absolute left-[85%] top-0" style="animation: scroll 11s linear infinite;">routes<br/>nodes<br/>edges<br/>state<br/>graph<br/>compile<br/>stream<br/>invoke</div>
    </div>
    <style>
      @keyframes scroll { 0% { transform: translateY(-100%); } 100% { transform: translateY(100vh); } }
    </style>

    <div class="w-full h-full flex items-center justify-center relative">
      <div class="w-[1350px] h-[720px] mx-auto p-10 flex flex-col items-center justify-center relative">
        <h2 class="text-[36px] font-bold text-cyan-400 mb-2 relative z-10">精彩代码 · 推荐子图关键实现</h2>
        <p class="text-[16px] text-gray-400 font-mono mb-8 relative z-10">过敏原硬过滤为什么必须是布尔运算，而不是「降权」</p>

        <div class="relative w-full max-w-5xl bg-slate-900/95 rounded-lg overflow-hidden border border-cyan-500/40 shadow-2xl z-10">
          <div class="bg-slate-800 border-b border-cyan-500/30 px-6 py-3 flex items-center justify-between">
            <div class="flex items-center gap-3">
              <div class="flex gap-2">
                <div class="w-3 h-3 bg-red-500 rounded-full"></div>
                <div class="w-3 h-3 bg-yellow-500 rounded-full"></div>
                <div class="w-3 h-3 bg-green-500 rounded-full"></div>
              </div>
              <span class="text-cyan-400 font-mono text-[15px] ml-4">backend/app/graph/subgraphs/recommend.py</span>
            </div>
            <div class="text-cyan-400 font-mono text-[14px]">UTF-8 | Python 3.11</div>
          </div>

          <div class="p-6 font-mono text-[15px] leading-[1.75]">
            <div class="flex">
              <div class="text-gray-600 pr-5 select-none text-right">
                <div>1</div><div>2</div><div>3</div><div>4</div><div>5</div><div>6</div><div>7</div><div>8</div><div>9</div><div>10</div><div>11</div>
              </div>
              <div class="flex-1">
                <div><span class="text-gray-500"># 1) 三路混合召回：覆盖率恒生效，向量召回需 query_text 非空</span></div>
                <div><span class="text-cyan-300">candidates</span> <span class="text-gray-400">=</span> <span class="text-yellow-300">coverage_recall</span><span class="text-gray-400">(ctx)</span> <span class="text-purple-400">|</span> <span class="text-yellow-300">text_recall</span><span class="text-gray-400">(ctx)</span></div>
                <div><span class="text-purple-400">if</span> <span class="text-cyan-300">use_vector</span> <span class="text-purple-400">and</span> <span class="text-cyan-300">query_text</span><span class="text-gray-400">:</span></div>
                <div>&nbsp;&nbsp;&nbsp;&nbsp;<span class="text-cyan-300">candidates</span> <span class="text-purple-400">|=</span> <span class="text-yellow-300">vector_recall</span><span class="text-gray-400">(query_text, top_k=</span><span class="text-orange-300">20</span><span class="text-gray-400">)</span></div>
                <div>&nbsp;</div>
                <div><span class="text-gray-500"># 2) 四维布尔硬过滤：过敏原走 SQL 布尔，绝不降权</span></div>
                <div><span class="text-cyan-300">sql</span> <span class="text-gray-400">=</span> <span class="text-green-300">"WHERE NOT (allergen_codes &amp;&amp; %s::text[])"</span></div>
                <div><span class="text-cyan-300">rows</span> <span class="text-gray-400">=</span> <span class="text-yellow-300">session.execute</span><span class="text-gray-400">(sql, (user_allergens,))</span></div>
                <div>&nbsp;</div>
                <div><span class="text-purple-400">def</span> <span class="text-yellow-300">weighted_rank</span><span class="text-gray-400">(candidates):</span> <span class="text-gray-500"># 输入只能是 hard_filter 输出集</span></div>
                <div>&nbsp;&nbsp;&nbsp;&nbsp;<span class="text-purple-400">return</span> <span class="text-yellow-300">score</span><span class="text-gray-400">(candidates)</span> <span class="text-gray-500"># 结构上杜绝「打分后放回」</span></div>
              </div>
            </div>
          </div>

          <div class="bg-slate-800 border-t border-cyan-500/30 px-6 py-2 flex items-center justify-between text-[13px]">
            <div class="flex items-center gap-6 text-gray-400">
              <span>Ln 7, Col 12</span>
              <span class="text-cyan-400">● 硬过滤 · 不降权</span>
            </div>
            <div class="flex items-center gap-5 text-gray-400">
              <span>dislike 走降权 −0.5</span>
              <span class="text-green-400">✓ 12 条红线全绿</span>
            </div>
          </div>
        </div>

        <div class="mt-8 flex gap-4 relative z-10">
          <div class="px-5 py-2 bg-cyan-500/15 border border-cyan-500/50 rounded-full"><span class="text-cyan-400 font-mono text-[15px]">Python 3.11</span></div>
          <div class="px-5 py-2 bg-blue-500/15 border border-blue-500/50 rounded-full"><span class="text-blue-400 font-mono text-[15px]">PostgreSQL 16</span></div>
          <div class="px-5 py-2 bg-purple-500/15 border border-purple-500/50 rounded-full"><span class="text-purple-400 font-mono text-[15px]">pgvector</span></div>
          <div class="px-5 py-2 bg-emerald-500/15 border border-emerald-500/50 rounded-full"><span class="text-emerald-400 font-mono text-[15px]">LangGraph</span></div>
          <div class="px-5 py-2 bg-amber-500/15 border border-amber-500/50 rounded-full"><span class="text-amber-400 font-mono text-[15px]">布尔硬过滤</span></div>
        </div>
      </div>
    </div>
  </div>
`);window.slideDataMap.set(13,`
  <div class="w-[1440px] h-[810px] shadow-2xl relative overflow-hidden slide-bg">
    <div class="absolute inset-0 opacity-20">
      <div class="absolute top-1/4 left-1/4 w-px h-full bg-cyan-500/50"></div>
      <div class="absolute top-1/4 left-2/4 w-px h-full bg-blue-500/50"></div>
      <div class="absolute top-1/4 left-3/4 w-px h-full bg-purple-500/50"></div>
    </div>

    <div class="w-full h-full flex items-center justify-center relative">
      <div class="w-[1350px] h-[720px] mx-auto p-8 flex flex-col justify-center gap-5 relative z-10">
        <div class="text-center">
          <div class="inline-flex items-center gap-2 bg-cyan-500/15 px-5 py-1.5 rounded-full mb-3">
            <div class="w-2 h-2 bg-cyan-400 rounded-full animate-pulse"></div>
            <span class="text-cyan-400 font-mono text-[13px] tracking-wider">GUARDRAILS · SHORT-CIRCUIT · DEGRADATION</span>
          </div>
          <h2 class="text-[38px] font-bold text-cyan-300 mb-2">精彩代码 · 风控与编排关键设计</h2>
          <p class="text-gray-400 text-[16px]">一票否决 = 控制流短路，不是「标记后丢弃」</p>
        </div>

        <div class="max-w-5xl mx-auto w-full">
          <div class="bg-slate-900/85 border border-cyan-500/30 p-5 rounded-lg">
            <p class="text-gray-200 text-[16px] leading-relaxed mb-2">
              风控引擎是<span class="text-cyan-300 font-bold">纯规则实现，不调用大模型</span>：确定性、可审计、毫秒级、零 token 成本，且<span class="text-cyan-300 font-bold">没有 Prompt 注入面</span>。
            </p>
            <p class="text-gray-300 text-[15px] leading-relaxed">
              命中高风险后不进入任何业务节点，而是经<span class="text-purple-300 font-mono">条件边</span>直达终止节点 <span class="text-purple-300 font-mono">emit_safety_response</span>，返回体不含任何业务字段。
            </p>
          </div>
        </div>

        <div class="grid grid-cols-3 gap-5">
          <div class="bg-cyan-500/10 border border-cyan-500/30 rounded-lg p-5">
            <div class="flex items-center gap-2 mb-2">
              <div class="w-8 h-8 bg-cyan-500 text-white flex items-center justify-center font-mono text-[14px] rounded">01</div>
              <h4 class="text-[19px] font-bold text-cyan-300">一票否决短路</h4>
            </div>
            <p class="text-gray-300 text-[14px] leading-snug">命中即短路直达终止节点，业务节点一个都不执行</p>
          </div>
          <div class="bg-purple-500/10 border border-purple-500/30 rounded-lg p-5">
            <div class="flex items-center gap-2 mb-2">
              <div class="w-8 h-8 bg-purple-500 text-white flex items-center justify-center font-mono text-[14px] rounded">02</div>
              <h4 class="text-[19px] font-bold text-purple-300">双重风控</h4>
            </div>
            <p class="text-gray-300 text-[14px] leading-snug">输入侧 intake_guard 与输出侧 output_guard 都不可省</p>
          </div>
          <div class="bg-emerald-500/10 border border-emerald-500/30 rounded-lg p-5">
            <div class="flex items-center gap-2 mb-2">
              <div class="w-8 h-8 bg-emerald-500 text-white flex items-center justify-center font-mono text-[14px] rounded">03</div>
              <h4 class="text-[19px] font-bold text-emerald-300">降级保守</h4>
            </div>
            <p class="text-gray-300 text-[14px] leading-snug">异常/超时进入 safe_mode_handler，绝不直连模型</p>
          </div>
        </div>

        <div class="grid grid-cols-2 gap-5">
          <div class="bg-black/70 border-2 border-cyan-500 rounded-lg p-5">
            <p class="text-cyan-300 text-[15px] leading-relaxed mb-1 font-mono">
              <span class="text-cyan-500 font-bold">// 动态装配：</span>nodes 按 AGENT_REGISTRY 注册
            </p>
            <p class="text-gray-400 text-[14px] font-mono">新增 Agent 只需注册，不改装配逻辑</p>
          </div>
          <div class="bg-slate-900/70 border border-purple-500/40 rounded-lg p-5">
            <p class="text-purple-300 text-[15px] leading-relaxed mb-1 font-mono">
              <span class="text-purple-400 font-bold">// 可追溯：</span>trace 记录命中规则与版本
            </p>
            <p class="text-gray-400 text-[14px] font-mono">如 FS-003@rules-v1.0，可逐次回放</p>
          </div>
        </div>
      </div>
    </div>
  </div>
`);window.slideDataMap.set(14,`
  <div class="w-[1440px] h-[810px] shadow-2xl relative overflow-hidden slide-bg">
    <div class="absolute inset-0" style="background-image: repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(34,211,238,0.04) 2px, rgba(34,211,238,0.04) 4px), repeating-linear-gradient(90deg, transparent, transparent 2px, rgba(34,211,238,0.04) 2px, rgba(34,211,238,0.04) 4px);"></div>

    <div class="w-[1350px] h-[720px] mx-auto my-[45px] p-10 relative z-10 flex flex-col">
      <div class="flex items-end justify-between mb-5">
        <div>
          <h2 class="text-[34px] font-bold text-cyan-400 mb-1">功能演示 · 真实界面</h2>
          <p class="text-[15px] text-gray-400 font-mono">浏览器自动化实测 · 真实导航 + 交互操作 + 截图取证</p>
        </div>
        <div class="flex gap-8">
          <div class="text-center">
            <p class="text-[24px] font-bold text-cyan-400 font-mono leading-none mb-1">16/16</p>
            <p class="text-gray-400 text-[13px]">页面可达</p>
          </div>
          <div class="text-center">
            <p class="text-[24px] font-bold text-emerald-400 font-mono leading-none mb-1">0</p>
            <p class="text-gray-400 text-[13px]">控制台 Error</p>
          </div>
          <div class="text-center">
            <p class="text-[24px] font-bold text-purple-400 font-mono leading-none mb-1">19</p>
            <p class="text-gray-400 text-[13px]">截图存证</p>
          </div>
        </div>
      </div>

      <div class="grid grid-cols-2 gap-4 flex-1">
        <div class="bg-slate-900/85 border border-cyan-500/30 rounded-lg overflow-hidden flex flex-col">
          <img src="/assets/images/03-recommend.png" class="w-full h-[200px] object-cover object-top"/>
          <div class="px-4 py-3 border-t border-cyan-500/20">
            <p class="text-cyan-300 text-[16px] font-bold mb-1">推荐结果页</p>
            <p class="text-gray-400 text-[13px] leading-snug">三档分组 · 覆盖率与缺失食材 · 「为什么推荐给你」· 被过滤明细可重放</p>
          </div>
        </div>

        <div class="bg-slate-900/85 border border-emerald-500/30 rounded-lg overflow-hidden flex flex-col">
          <img src="/assets/images/06-recipe-detail.png" class="w-full h-[200px] object-cover object-top"/>
          <div class="px-4 py-3 border-t border-emerald-500/20">
            <p class="text-emerald-300 text-[16px] font-bold mb-1">菜谱详情页</p>
            <p class="text-gray-400 text-[13px] leading-snug">顶部致敏原警示条 · 逐行致敏原标注 · 份数缩放 · 用量量化</p>
          </div>
        </div>

        <div class="bg-slate-900/85 border border-purple-500/30 rounded-lg overflow-hidden flex flex-col">
          <img src="/assets/images/07-cook-guide.png" class="w-full h-[200px] object-cover object-top"/>
          <div class="px-4 py-3 border-t border-purple-500/20">
            <p class="text-purple-300 text-[16px] font-bold mb-1">分步烹饪引导</p>
            <p class="text-gray-400 text-[13px] leading-snug">大字单步 · 进度条 · 并行计时器 · 断点续做与退出二次确认</p>
          </div>
        </div>

        <div class="bg-slate-900/85 border border-red-500/30 rounded-lg overflow-hidden flex flex-col">
          <img src="/assets/images/08-blocked.png" class="w-full h-[200px] object-cover object-top"/>
          <div class="px-4 py-3 border-t border-red-500/20">
            <p class="text-red-300 text-[16px] font-bold mb-1">风控拦截页</p>
            <p class="text-gray-400 text-[13px] leading-snug">FS-003 真实触发 · 风险说明 / 正确做法 / 就医引导三段式</p>
          </div>
        </div>
      </div>
    </div>
  </div>
`);window.slideDataMap.set(15,`
  <div class="w-[1440px] h-[810px] shadow-2xl relative overflow-hidden slide-bg">
    <div class="w-[1350px] h-[720px] mx-auto my-[45px] relative">
      <div class="absolute inset-0 opacity-20" style="background-image: linear-gradient(rgba(34,211,238,0.1) 1px, transparent 1px), linear-gradient(90deg, rgba(34,211,238,0.1) 1px, transparent 1px); background-size: 40px 40px;"></div>
      <div class="absolute top-1/2 left-0 right-0 h-px bg-cyan-400/60"></div>
      <div class="absolute top-1/2 left-0 right-0 h-16 bg-cyan-500/10"></div>
      <div class="relative z-10 flex items-center justify-center h-full">
        <div class="text-center">
          <div class="text-[52px] font-bold text-cyan-500 mb-6 font-mono">
            <span class="inline-block border-2 border-cyan-500 px-8 py-3">&lt; 03 /&gt;</span>
          </div>
          <h1 class="text-[56px] font-bold text-white mb-4 tracking-[0.1em]">问题与解决方案</h1>
          <p class="text-[22px] text-cyan-400 tracking-[0.12em]">4 类问题总览 + 4 个典型案例深剖</p>
          <div class="flex items-center justify-center gap-2 mt-8">
            <div class="w-2 h-2 bg-cyan-400 rounded-full animate-pulse"></div>
            <div class="w-2 h-2 bg-cyan-400 rounded-full animate-pulse" style="animation-delay: 0.2s;"></div>
            <div class="w-2 h-2 bg-cyan-400 rounded-full animate-pulse" style="animation-delay: 0.4s;"></div>
          </div>
        </div>
      </div>
    </div>
  </div>
`);window.slideDataMap.set(16,`
  <div class="w-[1440px] h-[810px] shadow-2xl relative overflow-hidden slide-bg">
    <div class="absolute inset-0 bg-blue-950/20"></div>
    <div class="w-[1350px] h-[720px] mx-auto my-[45px] relative">
      <h2 class="text-[36px] font-bold text-cyan-400 mb-2">问题与解决方案总览</h2>
      <p class="text-[16px] text-gray-400 font-mono mb-8">问题 → 方案 → 结果：每一个问题都有落地动作与验证结论</p>

      <div class="flex gap-8 items-start justify-center">
        <div class="w-[350px]">
          <div class="h-11 bg-slate-800 border-b border-red-500/40 flex items-center justify-center rounded-t">
            <span class="text-red-400 font-mono text-[15px] font-bold tracking-wider">01 · 遇到的问题</span>
          </div>
          <div class="h-[420px] bg-slate-900/80 border-2 border-red-500/40 border-t-0 rounded-b p-3 space-y-[6px]">
            <div class="min-h-[54px] bg-slate-700/70 border border-red-500/40 rounded flex items-center px-3 py-2"><span class="text-red-200 text-[15px] leading-snug">纯手选食材路径不走向量召回</span></div>
            <div class="min-h-[54px] bg-slate-700/70 border border-red-500/40 rounded flex items-center px-3 py-2"><span class="text-red-200 text-[15px] leading-snug">默认嵌入是哈希伪向量，非语义</span></div>
            <div class="min-h-[54px] bg-slate-700/70 border border-red-500/40 rounded flex items-center px-3 py-2"><span class="text-red-200 text-[15px] leading-snug">过敏原要与口味偏好区分语义</span></div>
            <div class="min-h-[54px] bg-slate-700/70 border border-red-500/40 rounded flex items-center px-3 py-2"><span class="text-red-200 text-[15px] leading-snug">2C2G 服务器构建前端必然 OOM</span></div>
            <div class="min-h-[54px] bg-slate-700/70 border border-red-500/40 rounded flex items-center px-3 py-2"><span class="text-red-200 text-[15px] leading-snug">镜像加速对写死 registry 前缀无效</span></div>
            <div class="min-h-[54px] bg-slate-700/70 border border-red-500/40 rounded flex items-center px-3 py-2"><span class="text-red-200 text-[15px] leading-snug">http + 公网 IP 下麦克风静默失效</span></div>
          </div>
        </div>

        <div class="w-[350px]">
          <div class="h-11 bg-slate-800 border-b border-amber-500/40 flex items-center justify-center rounded-t">
            <span class="text-amber-400 font-mono text-[15px] font-bold tracking-wider">02 · 解决方案</span>
          </div>
          <div class="h-[420px] bg-slate-900/80 border-2 border-amber-500/40 border-t-0 rounded-b p-3 space-y-[6px]">
            <div class="min-h-[54px] bg-slate-700/70 border border-amber-500/40 rounded flex items-center px-3 py-2"><span class="text-amber-200 text-[15px] leading-snug">补齐覆盖率 / 文本 / 向量三路召回</span></div>
            <div class="min-h-[54px] bg-slate-700/70 border border-amber-500/40 rounded flex items-center px-3 py-2"><span class="text-amber-200 text-[15px] leading-snug">修复向量升级三缺口并留痕</span></div>
            <div class="min-h-[54px] bg-slate-700/70 border border-amber-500/40 rounded flex items-center px-3 py-2"><span class="text-amber-200 text-[15px] leading-snug">过敏原硬过滤 ＋ dislike 降权 −0.5</span></div>
            <div class="min-h-[54px] bg-slate-700/70 border border-amber-500/40 rounded flex items-center px-3 py-2"><span class="text-amber-200 text-[15px] leading-snug">本地 build → save → scp → load</span></div>
            <div class="min-h-[54px] bg-slate-700/70 border border-amber-500/40 rounded flex items-center px-3 py-2"><span class="text-amber-200 text-[15px] leading-snug">先加速拉官方镜像，再 docker tag</span></div>
            <div class="min-h-[54px] bg-slate-700/70 border border-amber-500/40 rounded flex items-center px-3 py-2"><span class="text-amber-200 text-[15px] leading-snug">上 HTTPS / 自签证书（语音硬前提）</span></div>
          </div>
        </div>

        <div class="w-[350px]">
          <div class="h-11 bg-slate-800 border-b border-emerald-500/40 flex items-center justify-center rounded-t">
            <span class="text-emerald-400 font-mono text-[15px] font-bold tracking-wider">03 · 验证结果</span>
          </div>
          <div class="h-[420px] bg-slate-900/80 border-2 border-emerald-500/40 border-t-0 rounded-b p-3 space-y-[6px]">
            <div class="min-h-[54px] bg-slate-700/70 border border-emerald-500/40 rounded flex items-center px-3 py-2"><span class="text-emerald-200 text-[15px] leading-snug">三缺口已闭环，口径对齐（R-27）</span></div>
            <div class="min-h-[54px] bg-slate-700/70 border border-emerald-500/40 rounded flex items-center px-3 py-2"><span class="text-emerald-200 text-[15px] leading-snug">12 条安全红线全绿</span></div>
            <div class="min-h-[54px] bg-slate-700/70 border border-emerald-500/40 rounded flex items-center px-3 py-2"><span class="text-emerald-200 text-[15px] leading-snug">被过滤菜谱可逐条重放原因</span></div>
            <div class="min-h-[54px] bg-slate-700/70 border border-emerald-500/40 rounded flex items-center px-3 py-2"><span class="text-emerald-200 text-[15px] leading-snug">生产 8005 全端点 200，DB up</span></div>
            <div class="min-h-[54px] bg-slate-700/70 border border-emerald-500/40 rounded flex items-center px-3 py-2"><span class="text-emerald-200 text-[15px] leading-snug">部署脚本固化 8 步，可重复执行</span></div>
            <div class="min-h-[54px] bg-slate-700/70 border border-emerald-500/40 rounded flex items-center px-3 py-2"><span class="text-emerald-200 text-[15px] leading-snug">未闭环项登记为 R-31 / R-33</span></div>
          </div>
        </div>
      </div>
    </div>
  </div>
`);window.slideDataMap.set(17,`
  <div class="w-[1440px] h-[810px] shadow-2xl relative overflow-hidden slide-bg">
    <div class="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2">
      <svg class="w-[660px] h-[660px]" viewBox="0 0 600 600">
        <circle cx="300" cy="300" r="250" fill="none" stroke="#22d3ee" stroke-width="1" opacity="0.3"/>
        <circle cx="300" cy="300" r="200" fill="none" stroke="#22d3ee" stroke-width="1" opacity="0.4"/>
        <circle cx="300" cy="300" r="150" fill="none" stroke="#22d3ee" stroke-width="1" opacity="0.5"/>
        <circle cx="300" cy="300" r="100" fill="none" stroke="#22d3ee" stroke-width="1" opacity="0.6"/>
        <circle cx="300" cy="300" r="50" fill="none" stroke="#22d3ee" stroke-width="2" opacity="0.7"/>
        <line x1="50" y1="300" x2="550" y2="300" stroke="#22d3ee" stroke-width="1" opacity="0.3"/>
        <line x1="300" y1="50" x2="300" y2="550" stroke="#22d3ee" stroke-width="1" opacity="0.3"/>
        <defs>
          <linearGradient id="scanGradient2" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" style="stop-color:#22d3ee;stop-opacity:0" />
            <stop offset="100%" style="stop-color:#22d3ee;stop-opacity:0.55" />
          </linearGradient>
        </defs>
        <g style="transform-origin: center; animation: rotate2 5s linear infinite;">
          <path d="M 300 300 L 300 50 A 250 250 0 0 1 477 123 Z" fill="url(#scanGradient2)" opacity="0.4"/>
        </g>
      </svg>
    </div>
    <style>
      @keyframes rotate2 { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
    </style>

    <div class="w-full h-full flex items-center justify-center relative">
      <div class="w-[1350px] h-[720px] mx-auto p-10 flex items-center justify-center relative">
        <h2 class="absolute top-8 left-1/2 transform -translate-x-1/2 text-[40px] font-bold text-cyan-400 z-10">关键问题深剖</h2>
        <p class="absolute top-[74px] left-1/2 transform -translate-x-1/2 text-[16px] text-gray-400 font-mono z-10">4 个最值得讲的坑：现象 → 根因 → 解法 → 结论</p>

        <div class="relative w-full max-w-5xl h-[420px] mt-8">
          <div class="absolute" style="top: 2%; left: 0%;">
            <div class="relative">
              <div class="w-4 h-4 bg-red-500 rounded-full animate-ping"></div>
              <div class="w-4 h-4 bg-red-500 rounded-full absolute top-0"></div>
              <div class="absolute top-6 left-6 bg-black/90 border border-red-500 p-3 rounded min-w-[250px]">
                <p class="text-red-400 font-bold text-[17px] mb-1">案例 1 · 检索缺口</p>
                <p class="text-gray-300 text-[14px]">纯手选食材不走向量召回</p>
                <p class="text-red-500 text-[14px] mt-1">补齐三路缺口，登记改进项</p>
              </div>
            </div>
          </div>

          <div class="absolute" style="top: 0%; right: 0%;">
            <div class="relative">
              <div class="w-3 h-3 bg-yellow-500 rounded-full animate-pulse"></div>
              <div class="absolute top-6 right-0 bg-black/90 border border-yellow-500 p-3 rounded min-w-[250px]">
                <p class="text-yellow-400 font-bold text-[17px] mb-1">案例 2 · 构建 OOM</p>
                <p class="text-gray-300 text-[14px]">2C2G 上构建峰值 &gt; 1.5GB</p>
                <p class="text-yellow-500 text-[14px] mt-1">本地构建后 save → scp → load</p>
              </div>
            </div>
          </div>

          <div class="absolute" style="bottom: 2%; left: 0%;">
            <div class="relative">
              <div class="w-3 h-3 bg-green-500 rounded-full"></div>
              <div class="absolute bottom-6 left-0 bg-black/90 border border-green-500 p-3 rounded min-w-[250px]">
                <p class="text-green-400 font-bold text-[17px] mb-1">案例 3 · 镜像加速失效</p>
                <p class="text-gray-300 text-[14px]">写死 registry 前缀时不生效</p>
                <p class="text-green-500 text-[14px] mt-1">先加速拉再 docker tag 打别名</p>
              </div>
            </div>
          </div>

          <div class="absolute" style="bottom: 2%; right: 0%;">
            <div class="relative">
              <div class="w-3 h-3 bg-blue-500 rounded-full"></div>
              <div class="absolute bottom-6 right-0 bg-black/90 border border-blue-500 p-3 rounded min-w-[250px]">
                <p class="text-blue-400 font-bold text-[17px] mb-1">案例 4 · 语音静默失效</p>
                <p class="text-gray-300 text-[14px]">getUserMedia 仅安全上下文可用</p>
                <p class="text-blue-500 text-[14px] mt-1">上 HTTPS，风险登记 R-31</p>
              </div>
            </div>
          </div>
        </div>

        <div class="absolute bottom-8 left-1/2 transform -translate-x-1/2 w-full max-w-5xl">
          <div class="bg-slate-900/90 border border-cyan-500/30 rounded-lg p-5">
            <div class="flex justify-between items-center">
              <div class="flex items-center gap-3">
                <div class="w-3 h-3 bg-green-500 rounded-full animate-pulse"></div>
                <span class="text-green-400 font-mono text-[15px]">ISSUE LOG · TRACKED</span>
              </div>
              <div class="flex gap-12">
                <div class="text-center">
                  <p class="text-cyan-400 text-[22px] font-bold font-mono">4</p>
                  <p class="text-gray-400 text-[14px]">典型案例</p>
                </div>
                <div class="text-center">
                  <p class="text-green-400 text-[22px] font-bold font-mono">3</p>
                  <p class="text-gray-400 text-[14px]">已闭环</p>
                </div>
                <div class="text-center">
                  <p class="text-amber-400 text-[22px] font-bold font-mono">1</p>
                  <p class="text-gray-400 text-[14px]">已登记待办</p>
                </div>
                <div class="text-center">
                  <p class="text-purple-400 text-[22px] font-bold font-mono">12</p>
                  <p class="text-gray-400 text-[14px]">红线全绿</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
`);window.slideDataMap.set(18,`
  <div class="w-[1440px] h-[810px] shadow-2xl relative overflow-hidden slide-bg">
    <div class="w-[1350px] h-[720px] mx-auto my-[45px] relative">
      <div class="absolute inset-0 opacity-20" style="background-image: linear-gradient(rgba(34,211,238,0.1) 1px, transparent 1px), linear-gradient(90deg, rgba(34,211,238,0.1) 1px, transparent 1px); background-size: 40px 40px;"></div>
      <div class="absolute top-1/2 left-0 right-0 h-px bg-cyan-400/60"></div>
      <div class="absolute top-1/2 left-0 right-0 h-16 bg-cyan-500/10"></div>
      <div class="relative z-10 flex items-center justify-center h-full">
        <div class="text-center">
          <div class="text-[52px] font-bold text-cyan-500 mb-6 font-mono">
            <span class="inline-block border-2 border-cyan-500 px-8 py-3">&lt; 04 /&gt;</span>
          </div>
          <h1 class="text-[56px] font-bold text-white mb-4 tracking-[0.1em]">项目完成后的收获</h1>
          <p class="text-[22px] text-cyan-400 tracking-[0.12em]">技术深度 · 工程能力 · 产品思维 · 协作与风险意识</p>
          <div class="flex items-center justify-center gap-2 mt-8">
            <div class="w-2 h-2 bg-cyan-400 rounded-full animate-pulse"></div>
            <div class="w-2 h-2 bg-cyan-400 rounded-full animate-pulse" style="animation-delay: 0.2s;"></div>
            <div class="w-2 h-2 bg-cyan-400 rounded-full animate-pulse" style="animation-delay: 0.4s;"></div>
          </div>
        </div>
      </div>
    </div>
  </div>
`);window.slideDataMap.set(19,`
  <div class="w-[1440px] h-[810px] shadow-2xl relative overflow-hidden slide-bg">
    <div class="absolute inset-0 opacity-20">
      <div class="absolute top-1/4 left-1/4 w-px h-full bg-cyan-500/50"></div>
      <div class="absolute top-1/4 left-2/4 w-px h-full bg-blue-500/50"></div>
      <div class="absolute top-1/4 left-3/4 w-px h-full bg-purple-500/50"></div>
    </div>

    <div class="w-full h-full flex items-center justify-center relative">
      <div class="w-[1350px] h-[720px] mx-auto p-8 flex flex-col justify-center gap-5 relative z-10">
        <div class="text-center">
          <h2 class="text-[38px] font-bold text-cyan-300 mb-2">项目完成后的收获</h2>
          <p class="text-gray-400 text-[16px]">从「能跑」到「敢上线」的五项成长</p>
        </div>

        <div class="max-w-5xl mx-auto w-full">
          <div class="bg-slate-900/85 border border-cyan-500/30 p-5 rounded-lg">
            <p class="text-gray-200 text-[16px] leading-relaxed mb-2">
              项目从 0 走到生产上线：三端 <span class="text-cyan-300 font-bold">74 页</span>、前端 <span class="text-cyan-300 font-bold">47,736 行</span>、后端 <span class="text-cyan-300 font-bold">121 个接口端点</span>。
            </p>
            <p class="text-gray-300 text-[15px] leading-relaxed">
              最大的收获不是「把功能写完」，而是学会用<span class="text-cyan-300 font-bold">结构与规则</span>替代<span class="text-amber-300 font-bold">人的记忆与自觉</span> —— 安全不靠人记得过滤，而靠代码结构保证一定过滤。
            </p>
          </div>
        </div>

        <div class="grid grid-cols-3 gap-5">
          <div class="bg-cyan-500/10 border border-cyan-500/30 rounded-lg p-5">
            <div class="flex items-center gap-2 mb-2">
              <div class="w-8 h-8 bg-cyan-500 text-white flex items-center justify-center font-mono text-[14px] rounded">01</div>
              <h4 class="text-[19px] font-bold text-cyan-300">技术深度</h4>
            </div>
            <p class="text-gray-300 text-[14px] leading-snug">吃透 LangGraph 多智能体编排：22 节点、动态注册装配、并行分支与条件边短路</p>
          </div>
          <div class="bg-purple-500/10 border border-purple-500/30 rounded-lg p-5">
            <div class="flex items-center gap-2 mb-2">
              <div class="w-8 h-8 bg-purple-500 text-white flex items-center justify-center font-mono text-[14px] rounded">02</div>
              <h4 class="text-[19px] font-bold text-purple-300">工程能力</h4>
            </div>
            <p class="text-gray-300 text-[14px] leading-snug">建立质量基线与可复现意识：319 后端单测 / 236 Web 单测 / 43 条 E2E 全闭环</p>
          </div>
          <div class="bg-emerald-500/10 border border-emerald-500/30 rounded-lg p-5">
            <div class="flex items-center gap-2 mb-2">
              <div class="w-8 h-8 bg-emerald-500 text-white flex items-center justify-center font-mono text-[14px] rounded">03</div>
              <h4 class="text-[19px] font-bold text-emerald-300">产品思维</h4>
            </div>
            <p class="text-gray-300 text-[14px] leading-snug">从「做过什么」转向「用户敢不敢用」：不凑数、可重放、缺失营养不按 0 计</p>
          </div>
        </div>

        <div class="grid grid-cols-2 gap-5">
          <div class="bg-black/70 border-2 border-cyan-500 rounded-lg p-5">
            <p class="text-cyan-300 text-[15px] leading-relaxed mb-1 font-mono">
              <span class="text-cyan-500 font-bold">// 协作规范：</span>变更一律走 CR 变更单
            </p>
            <p class="text-gray-400 text-[14px] font-mono">口头变更无效 · 文档冲突以需求文档为准</p>
          </div>
          <div class="bg-slate-900/70 border border-amber-500/40 rounded-lg p-5">
            <p class="text-amber-300 text-[15px] leading-relaxed mb-1 font-mono">
              <span class="text-amber-400 font-bold">// 风险意识：</span>未闭环项主动登记成风险
            </p>
            <p class="text-gray-400 text-[14px] font-mono">R-23 ~ R-33 共 11 项，而不是藏起来</p>
          </div>
        </div>
      </div>
    </div>
  </div>
`);window.slideDataMap.set(20,`
  <div class="w-[1440px] h-[810px] relative overflow-hidden slide-bg">
    <div class="w-[1350px] h-[720px] mx-auto my-[45px] relative">
      <svg style="position: absolute; width: 100%; height: 100%; opacity: 0.3;">
        <defs>
          <linearGradient id="data-flow-1" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" style="stop-color:#22d3ee;stop-opacity:0"/>
            <stop offset="50%" style="stop-color:#22d3ee;stop-opacity:1"/>
            <stop offset="100%" style="stop-color:#22d3ee;stop-opacity:0"/>
          </linearGradient>
        </defs>
        <rect x="0" y="20%" width="100%" height="2" fill="url(#data-flow-1)">
          <animate attributeName="y" values="0%;100%" dur="4s" repeatCount="indefinite"/>
        </rect>
        <rect x="0" y="40%" width="100%" height="2" fill="url(#data-flow-1)">
          <animate attributeName="y" values="0%;100%" dur="5s" repeatCount="indefinite"/>
        </rect>
        <rect x="0" y="60%" width="100%" height="2" fill="url(#data-flow-1)">
          <animate attributeName="y" values="0%;100%" dur="4.5s" repeatCount="indefinite"/>
        </rect>
      </svg>

      <div class="absolute inset-0 flex flex-col items-center justify-center z-[2]">
        <div style="position: relative; padding: 50px 90px; background: rgba(8, 12, 20, 0.9); border: 2px solid #22d3ee; box-shadow: 0 0 50px rgba(34, 211, 238, 0.35);">
          <div class="text-[64px] font-bold text-cyan-400 mb-8 text-center" style="letter-spacing: 8px; text-shadow: 0 0 30px rgba(34,211,238,0.55);">
            谢谢
          </div>
          <div class="text-[26px] text-cyan-300 text-center mb-6" style="letter-spacing: 3px; font-family: 'Courier New', monospace;">
            感谢您的耐心聆听 · 请老师指正
          </div>
          <div class="w-full h-px bg-cyan-500/40 mb-6"></div>
          <div class="flex items-center justify-center gap-10 text-cyan-200">
            <div class="text-center">
              <p class="text-[12px] text-cyan-600 font-mono tracking-[0.25em] mb-1">PRESENTED BY</p>
              <p class="text-[20px] font-bold tracking-[0.18em]">肖裔雄</p>
            </div>
            <div class="w-px h-10 bg-cyan-500/40"></div>
            <div class="text-center">
              <p class="text-[12px] text-cyan-600 font-mono tracking-[0.25em] mb-1">PROJECT</p>
              <p class="text-[20px] font-bold">AI 厨娘 · 智能烹饪助手</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
`);
