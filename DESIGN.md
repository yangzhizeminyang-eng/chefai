---
name: AI 厨娘
description: 面向家庭日常烹饪的食材与菜谱助手
colors:
  forest: "#24483A"
  sidebar: "#FBF9F4"
  paper: "#F7F6F0"
  surface: "#FFFEFA"
  ink: "#26362E"
  muted: "#718078"
  apricot: "#D4A17B"
  line: "#D9DDD4"
typography:
  display:
    fontFamily: "Noto Serif SC, Songti SC, Georgia, serif"
    fontSize: "50px"
    fontWeight: 600
    lineHeight: 1.28
    letterSpacing: "normal"
  body:
    fontFamily: "Segoe UI Variable, Microsoft YaHei UI, Microsoft YaHei, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "normal"
rounded:
  sm: "6px"
  md: "8px"
spacing:
  sm: "8px"
  md: "16px"
  lg: "28px"
components:
  button-primary:
    backgroundColor: "{colors.forest}"
    textColor: "{colors.surface}"
    rounded: "{rounded.sm}"
    height: "40px"
    padding: "0 15px"
  ingredient-chip:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    height: "38px"
    padding: "0 14px"
---

# Design System: AI 厨娘

## Overview

**Creative North Star: "The Working Kitchen"**

AI 厨娘的界面应像一间有人日常使用的家庭厨房：安静、清楚、带有真实食物的温度。颜色来自用户选定的首页参考，信息结构则围绕现有食材、家庭安全条件和下一步烹饪动作展开。

自然食物摄影负责呈现菜谱本身，控件保持克制。导航承担稳定的空间定位，食材标签是可见的工作状态，推荐主图是首页最有分量的内容。桌面使用常驻侧栏；窄屏将其收敛为可横向浏览的顶部导航。

**Key Characteristics:**
- 暖白内容面与深绿导航
- 实际菜谱照片优先于装饰性插画
- 家常中文标题与易读的系统无衬线正文
- 食材、菜谱与安全提示共享一个清晰的操作层级

## Colors

暖白和森林绿承载主要界面，杏色只用于少量选中与提示状态。

### Primary
- **森林绿** (#24483A): 主要操作、推荐动作和品牌强调。
- **深林导航** (#18372C): 桌面常驻导航底色。

### Secondary
- **杏木色** (#D4A17B): 导航激活、轻量强调和选中状态。

### Neutral
- **厨房纸白** (#F7F6F0): 全局页面背景。
- **搪瓷白** (#FFFEFA): 内容面与表单表面。
- **炭绿墨色** (#26362E): 正文与主要标题。
- **叶影灰绿** (#718078): 辅助文案。
- **石灰线** (#D9DDD4): 分隔与轻描边。

**The Food First Rule.** 菜谱照片展示真实菜品；颜色和形状不得替代菜品内容。

## Typography

**Display Font:** Noto Serif SC (fallback: Songti SC, Georgia, serif)
**Body Font:** Segoe UI Variable (fallback: Microsoft YaHei UI, Microsoft YaHei, sans-serif)
**Label/Mono Font:** System UI

**Character:** 中文衬线标题带出家常食谱的编辑感；中性无衬线正文保持表单、状态和多页流程的清晰度。

### Hierarchy
- **Display** (600, 34–50px, 1.28): 首页主标题。
- **Title** (600, 21–25px, 1.35): 区块与菜谱标题。
- **Body** (400, 14–16px, 1.5): 说明、问答和页面内容。
- **Label** (600–700, 11–13px, 1.4): 状态、元信息和导航分组。

## Layout

桌面以 208px 暖白侧栏和弹性内容区组成应用壳，侧栏与主内容共享一致的盒模型。首页对照用户选定的参考：左侧承载食材、推荐菜谱，右侧以实景厨房摄影形成主视觉；900px 以下切换为品牌行与可滚动导航，浅色模式继续使用图2的暖白导航，深色模式则由全站主题令牌同步切换；760px 以下首页内容收为单列并延续相同的图文顺序。账户、语音、主题、反馈和退出登录归入侧栏账户抽屉；移动窄屏抽屉从底部展开。

## Elevation & Depth

内容层级主要由留白、细分隔线和照片承担。卡片仅用于菜谱内容和需要强调的交互区域，静止界面不依赖大面积阴影。

## Shapes

输入、食材标签和操作面使用克制的小圆角（6–8px）。侧栏当前态采用实色而不是漂浮的圆角胶囊。菜谱照片使用稳定比例并裁切填充。

## Components

### Buttons
- **Primary:** 森林绿底、白字、小圆角（6px）；触屏高度至少 40px。
- **Secondary / Text:** 用于不抢主操作的导航、次要入口和重试。
- **Focus:** 键盘焦点必须可见，并与杏木色强调系统保持一致。

### Chips
- 食材标签使用轻底色、细边框和紧凑文字；每个标签来自用户当前选择，不预置演示食材。
- 「添加」使用图标按钮，必须有可访问名称。

### Cards / Containers
- 菜谱卡承载真实封面、名称、耗时、难度和进入详情的操作。
- 提醒、安全说明与普通内容以全宽分段或轻分隔呈现，不嵌套卡片。

### Inputs / Fields
- 输入表面使用搪瓷白和细描边；焦点态明显，不使用装饰性光晕。

### Navigation
- 桌面为暖白垂直侧栏，移动导航在浅色模式下复用图2的暖白表面；当前路由使用杏木色背景并保持清晰文字对比，深色模式下所有导航表面统一随全站主题切换。
- 移动端为品牌行加横向导航，不能挤压主内容宽度。

## Do's and Don'ts

### Do:
- **Do** 使用菜谱服务返回的真实封面和推荐文字。
- **Do** 为加载、异常、无结果、键盘焦点和窄屏保留可理解的状态。
- **Do** 让风控和免责声明在首页视觉升级后仍然可见。

### Don't:
- **Don't** 写死演示菜名、食材或推荐数据。
- **Don't** 让视觉样式绕开过敏原拦截、登录或推荐开关。
- **Don't** 将临期提醒表现为可食用性判断。
