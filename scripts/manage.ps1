# =====================================================================
# 文件名: scripts/manage.ps1
# 用途:   「AI 厨娘·智能烹饪助手」阶段一前后端一键管理脚本
#         - 双击 scripts\start.bat 可启动前后端；失败时窗口保留并等待确认
#         - setup : 初始化环境（创建 Python venv、安装后端依赖、npm install）
#         - start : 检查 PostgreSQL → 环境不完整时自动补跑 setup（PRD §5.1 一条命令启动）
#                   → (可选 -InitDb 初始化数据库) → 启动后端(默认 8000) → 启动前端(默认 5173)；
#                   后端/前端分别在独立弹出的 PowerShell 终端窗口中前台运行，
#                   实时运行日志直接显示在各自窗口（替代隐藏窗口 + 日志文件重定向）；
#                   端口被其他程序占用时自动顺延至下一个空闲端口（端口漂移，各服务独立决策），
#                   实际端口写入 logs\backend.port / frontend.port 供 stop/status/smoke 复用；
#                   前端启动时经环境变量 AICOOK_BACKEND_PORT 注入后端实际端口，
#                   vite.config.ts 据此切换代理目标，保证端口漂移后前后端数据仍然联通
#         - stop  : 按 PID 文件终止进程树；PID 文件缺失或进程已死时按端口兜底清理
#         - status: 查看 PostgreSQL / 后端 / 前端 运行状态
#         - test  : 运行后端 pytest 与前端 vitest 并汇总退出码
#         - smoke : 对运行中的服务执行阶段一冒烟断言（对齐 04-V1.1 §5.7 smoke-test.sh）：
#                   ① GET /v1/healthz 返回 200 且 status=ok；
#                   ② 一票否决短路纯净：POST /v1/ask 高危文本 blocked=true，响应体
#                     不含 results/candidates/nutrition 业务字段，risk.rule_code 非空；
#                   ③ 高危样本集（≥11 类）拦截率 100%（medical 类拒答亦计为拦截）；
#                   ④ 医疗提问拒答（blocked=true）；
#                   ⑤ 幂等重放：同 request_id 两次 POST /v1/recommend 响应体一致。
#                   任一断言失败以退出码 1 结束。
#         （Task 13 扩展为 15 模块全量剧本；①~⑤ 为阶段一口径不变）
#                   ⑥ 档案过敏原过滤：consent → 建档 → peanut 成员 → 推荐结果无花生菜谱；
#                   ⑦ 库存闭环：POST /v1/inventory → GET → PATCH 状态推进 active→used；
#                   ⑧ 会员支付：下单 → mock-pay paid → /v1/member/me is_member=true；
#                   ⑨ 创新链：precheck(鸡蛋+西红柿) ok → generate 201 status=generated+disclaimer；
#                   ⑩ 首页聚合：GET /v1/home 200 且 entries 字段存在；
#                   ⑪ 后台链路：/admin/v1/auth/login(admin) → dashboard/cost 200；
#                   ⑫ P95 采样：recommend×5 P95≤6s / 菜谱详情≤2s / healthz≤500ms。
#         （T7 收尾增补至 14 组断言，T8 再增补至 15 组断言）
#                   ⑬ 创新生成降级来源：generate(土豆+青椒, 90s) → 200/201 且
#                     recipe.basis.generated_by ∈ {"llm","template"}（25s 硬超时降级口径）；
#                   ⑭ 求助关键词库：创建烹饪会话 → help「盐放多了怎么办」→ blocked=false
#                     且 answers 非空且不含回退前缀「以下是本步要点」（关键词库优先命中）。
#                   ⑮ 视觉确认与深链直连（T8 增补，接口级不花 VLM 费用）：confirm 混合名单
#                     added=2 且伪食材进 skipped；recognize 缺 file 字段 → 422；
#                     profile 深链直连 200（/v1/profile 根路径 404，实际子深链 /v1/profile/skill）。
#         - docker: 转调 docker compose（-DockerCmd up|down|build|logs|ps）；
#                   docker 不可用时明确报错提示安装 Docker Desktop；up 后轮询 /v1/healthz
#                   就绪（最多 60 秒）再输出访问地址。
# 参数:   -Action      string  动作类型 setup|start|stop|status|test|smoke|docker，默认 status
#         -DockerCmd   string  docker 动作子命令 up|down|build|logs|ps，默认 ps（仅 -Action docker 生效）
#         -InitDb      switch  start 动作可选：先在 backend 目录执行 python -m app.seed
#         -OpenBrowser switch  start 动作可选：启动成功后打开浏览器访问 http://localhost:5173
# 示例:   powershell -ExecutionPolicy Bypass -File scripts\manage.ps1 -Action start
#         powershell -ExecutionPolicy Bypass -File scripts\manage.ps1 -Action start -InitDb -OpenBrowser
#         powershell -ExecutionPolicy Bypass -File scripts\manage.ps1 -Action stop
#         powershell -ExecutionPolicy Bypass -File scripts\manage.ps1 -Action status
#         powershell -ExecutionPolicy Bypass -File scripts\manage.ps1 -Action test
#         powershell -ExecutionPolicy Bypass -File scripts\manage.ps1 -Action smoke
# 健康口径: 后端健康探测统一走 GET /v1/healthz（05-V1.1 §9.5/§12.3 标准口径；
#           与根级 /healthz、兼容端点 /api/health 同一 handler，200 含 {status,database,version}）。
#           前端固定监听 5173（05-V1.1 §3.2 + vite.config.ts strictPort），启动命令显式
#           附加 --port 5173 --strictPort 防止端口冲突时自增漂移。
# 兼容:   Windows PowerShell 5.1 及以上（未使用 PS7 专属语法）；本文件须以 UTF-8 BOM 保存
# =====================================================================

[CmdletBinding()]
param(
    # 动作类型：setup|start|stop|status|test|smoke|docker（影响脚本执行的主流程）
    [ValidateSet('setup', 'start', 'stop', 'status', 'test', 'smoke', 'docker')]
    [string]$Action = 'status',

    # docker 动作子命令：up（后台拉起并等健康）|down|build|logs|ps（仅 -Action docker 生效）
    [ValidateSet('up', 'down', 'build', 'logs', 'ps')]
    [string]$DockerCmd = 'ps',

    # start 动作可选开关：为真时先执行数据库种子脚本 python -m app.seed（幂等）
    [switch]$InitDb,

    # start 动作可选开关：为真时在服务就绪后打开浏览器访问前端页面
    [switch]$OpenBrowser
)

# ---------- 全局环境设置 ----------
# 中文输出防乱码：控制台输入输出统一 UTF-8（PowerShell 5.1 兼容写法）
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'

# ---------- 路径与端口常量 ----------
# 项目根目录 = 本脚本所在 scripts 目录的上一级
$RootDir    = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $RootDir 'backend'
$WebDir     = Join-Path $RootDir 'web-stage1'
$LogsDir    = Join-Path $RootDir 'logs'
$VenvPython = Join-Path $BackendDir '.venv\Scripts\python.exe'
$PgPort     = 5432   # PostgreSQL 端口
$BePort     = 8000   # 后端 Uvicorn 端口
$FePort     = 5173   # 前端 Vite 端口
# 健康检查口径：05-V1.1 §9.5/§12.3 标准端点 /v1/healthz（start 就绪探测与 status 输出共用；
#           端口漂移时按 logs\backend.port 记录的实际端口动态构造探测地址）
$BeHealth   = 'http://127.0.0.1:8000/v1/healthz'

# ---------- 工具函数 ----------

function Write-Info {
    # 输出步骤提示信息（青色）
    # 参数 $Message - 提示文本
    # 返回值：无
    # 异常：无
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Cyan
}

function Write-Ok {
    # 输出成功信息（绿色）
    # 参数 $Message - 提示文本
    # 返回值：无
    # 异常：无
    param([string]$Message)
    Write-Host "[ OK ] $Message" -ForegroundColor Green
}

function Write-Warn {
    # 输出警告信息（黄色）
    # 参数 $Message - 提示文本
    # 返回值：无
    # 异常：无
    param([string]$Message)
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Write-Fail {
    # 输出错误信息（红色）
    # 参数 $Message - 提示文本
    # 返回值：无
    # 异常：无
    param([string]$Message)
    Write-Host "[FAIL] $Message" -ForegroundColor Red
}

function Test-PortOpen {
    # 检测目标主机端口是否可建立 TCP 连接（TcpClient 异步等待，兼容 PS5.1）
    # 参数 $TargetHost - 目标主机名，默认 127.0.0.1；前端 localhost 可能解析为 IPv6
    # 参数 $Port - 目标端口号
    # 参数 $TimeoutMs - 连接超时毫秒数，默认 2000
    # 返回值：$true 端口可达 / $false 不可达
    # 异常：连接被拒、超时等网络异常一律捕获并返回 $false
    param(
        [string]$TargetHost = '127.0.0.1',
        [int]$Port,
        [int]$TimeoutMs = 2000
    )
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $iar = $client.BeginConnect($TargetHost, $Port, $null, $null)
        if ($iar.AsyncWaitHandle.WaitOne($TimeoutMs) -and $client.Connected) { return $true }
        return $false
    }
    catch {
        return $false
    }
    finally {
        $client.Close()
    }
}

function Get-ListenPid {
    # 查询指定端口当前处于 Listen 状态的进程 PID
    # 参数 $Port - 本地监听端口号
    # 返回值：监听进程 PID（int）；无监听时返回 $null
    # 异常：Get-NetTCPConnection 不可用或无匹配时，使用 netstat 兜底；仍无匹配则返回 $null
    param([int]$Port)
    try {
        $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        if ($conns) { return [int]($conns | Select-Object -First 1).OwningProcess }
    }
    catch { }

    # 某些 Windows 环境下 Get-NetTCPConnection 由于权限/网络栈差异返回空，
    # 但 netstat 仍能准确报告监听 PID；启动前必须避免因此重复拉起服务。
    try {
        # 不附加 -p tcp：部分 Windows 版本会因此漏掉 [::1] 的 IPv6 监听。
        $lines = @(netstat.exe -ano 2>$null)
        foreach ($line in $lines) {
            $parts = $line.ToString().Trim() -split '\s+'
            if (
                $parts.Count -ge 5 -and
                $parts[0] -eq 'TCP' -and
                $parts[3] -eq 'LISTENING' -and
                $parts[1] -match (':{0}$' -f [regex]::Escape([string]$Port)) -and
                $parts[4] -match '^\d+$'
            ) {
                return [int]$parts[4]
            }
        }
    }
    catch { }
    return $null
}

function Get-HttpStatusCode {
    # 发起 GET 请求并返回 HTTP 状态码（HttpWebRequest 实现，兼容 PS5.1）
    # 参数 $Url - 目标 URL
    # 参数 $TimeoutSec - 请求超时秒数，默认 2
    # 返回值：HTTP 状态码（int）；网络不通/超时/连接失败时返回 $null
    # 异常：WebException 携带 Response 时取其状态码（如 503），否则返回 $null
    param(
        [string]$Url,
        [int]$TimeoutSec = 2
    )
    try {
        $req = [System.Net.HttpWebRequest]::Create($Url)
        $req.Method = 'GET'
        $req.Timeout = $TimeoutSec * 1000
        $req.ReadWriteTimeout = $TimeoutSec * 1000
        # 健康检查必须直连本机服务，不能被系统代理返回的响应伪装成就绪。
        $req.Proxy = [System.Net.GlobalProxySelection]::GetEmptyWebProxy()
        $resp = $req.GetResponse()
        $code = [int]$resp.StatusCode
        $resp.Close()
        return $code
    }
    catch [System.Net.WebException] {
        if ($_.Exception.Response) { return [int]$_.Exception.Response.StatusCode }
        return $null
    }
    catch {
        return $null
    }
}

function Wait-HttpReady {
    # 轮询等待 HTTP 端点就绪（支持多个候选 URL，任一就绪即通过；
    # 前端需同时探测 127.0.0.1 与 localhost，因 vite 默认仅绑定 localhost，
    # 在 Windows/Node 17+ 下可能只监听 IPv6 ::1，导致 127.0.0.1 永远连不上）
    # 参数 $Url - 目标 URL 数组
    # 参数 $TimeoutSec - 最长等待秒数
    # 参数 $Require200 - 为 $true 时仅 200 视为就绪；为 $false 时任意 <500 的响应均视为就绪
    # 返回值：$true 已就绪 / $false 超时未就绪
    # 异常：网络异常由 Get-HttpStatusCode 内部捕获，本函数不抛出
    param(
        [string[]]$Url,
        [int]$TimeoutSec = 30,
        [bool]$Require200 = $true
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        foreach ($u in $Url) {
            $code = Get-HttpStatusCode -Url $u -TimeoutSec 2
            if ($null -ne $code) {
                if ($Require200 -and $code -eq 200) { return $true }
                if (-not $Require200 -and $code -lt 500) { return $true }
            }
        }
        Start-Sleep -Milliseconds 800
    }
    return $false
}

function Get-FrontendHttpCode {
    # 探测前端 Vite 服务 HTTP 状态码（双栈兼容：优先 127.0.0.1，失败再试 localhost）
    # 参数 $Port - 前端端口号，默认 5173（端口漂移时传入实际端口）
    # 参数 $TimeoutSec - 单次请求超时秒数，默认 2
    # 返回值：首个探测成功的 HTTP 状态码；两者均失败返回 $null
    # 异常：网络异常由 Get-HttpStatusCode 内部捕获，本函数不抛出
    param(
        [int]$Port = 5173,
        [int]$TimeoutSec = 2
    )
    $c1 = Get-HttpStatusCode -Url ("http://127.0.0.1:{0}" -f $Port) -TimeoutSec $TimeoutSec
    if ($null -ne $c1) { return $c1 }
    return Get-HttpStatusCode -Url ("http://localhost:{0}" -f $Port) -TimeoutSec $TimeoutSec
}

function Test-ViteAlive {
    # 判断目标端口上运行的是否为本项目的 Vite dev server（端口漂移复用判定用）
    # 原理：探测 Vite 开发模式独有的特征端点 /@vite/client（返回 200 即为 Vite dev server），
    #       区分「本项目前端在跑（复用）」与「其他程序占用端口（端口漂移切换）」
    # 参数 $Port - 待探测的前端端口号
    # 返回值：$true 该端口运行着 Vite dev server / $false 其他程序占用或无服务
    # 异常：网络异常由 Get-HttpStatusCode 内部捕获，本函数不抛出
    param([int]$Port)
    $code = Get-HttpStatusCode -Url ("http://127.0.0.1:{0}/@vite/client" -f $Port) -TimeoutSec 2
    if ($code -eq 200) { return $true }
    # 兜底探测 localhost（vite 可能仅绑定 IPv6 ::1）
    $code = Get-HttpStatusCode -Url ("http://localhost:{0}/@vite/client" -f $Port) -TimeoutSec 2
    return ($code -eq 200)
}

function Find-FreePort {
    # 从起始端口开始顺延查找未被监听的空闲 TCP 端口（端口漂移自动切换用）
    # 参数 $StartPort - 起始端口号（从该端口开始逐个 +1 检测）
    # 参数 $MaxTries - 最多尝试的端口个数，默认 20
    # 返回值：首个空闲端口号（int）；连续 MaxTries 个端口均被占用时返回 $null
    # 异常：Get-ListenPid/Test-PortOpen 内部已做 netstat 兜底与异常捕获，本函数不抛出
    param(
        [int]$StartPort,
        [int]$MaxTries = 20
    )
    for ($i = 0; $i -lt $MaxTries; $i++) {
        $candidate = $StartPort + $i
        # 双重检测：监听 PID 查询 + localhost 连通探测（覆盖仅绑定 IPv6 ::1 的进程）
        if ($null -eq (Get-ListenPid -Port $candidate) -and
            -not (Test-PortOpen -TargetHost 'localhost' -Port $candidate -TimeoutMs 500)) {
            return $candidate
        }
    }
    return $null
}

function Get-RecordedPort {
    # 读取服务端口记录文件（logs\<Name>.port）中的端口号
    # （start 动作启动/复用服务时写入实际端口，供 stop/status/smoke 在端口漂移后定位服务）
    # 参数 $Name - 服务记录名（'backend' 或 'frontend'）
    # 返回值：记录的端口号（int）；文件缺失或内容无效时返回 $null
    # 异常：文件读取异常静默处理并返回 $null
    param([string]$Name)
    $file = Join-Path $LogsDir ('{0}.port' -f $Name)
    if (-not (Test-Path $file)) { return $null }
    try {
        $raw = (Get-Content $file -TotalCount 1 -ErrorAction SilentlyContinue)
        if ($raw) { $raw = ($raw | Select-Object -First 1).ToString().Trim() }
        if ($raw -match '^\d+$') { return [int]$raw }
    }
    catch { }
    return $null
}

function Stop-Target {
    # 停止单个服务：优先按 PID 文件终止进程树（taskkill /T /F）；
    # PID 文件缺失、内容无效或进程已退出时，按候选端口列表逐个兜底清理
    # 参数 $Name - 服务显示名（用于日志输出）
    # 参数 $PidFile - PID 文件路径
    # 参数 $Ports - 候选端口号数组（端口漂移时为「记录端口 + 默认端口」去重列表，兜底清理用）
    # 返回值：$true 执行了终止动作 / $false 无需终止（服务本就未运行）
    # 异常：taskkill 失败仅告警不中断；文件读写异常静默处理
    param(
        [string]$Name,
        [string]$PidFile,
        [int[]]$Ports
    )
    $didKill = $false
    if (Test-Path $PidFile) {
        $raw = Get-Content $PidFile -TotalCount 1 -ErrorAction SilentlyContinue
        if ($raw) { $raw = ($raw | Select-Object -First 1).ToString().Trim() }
        if ($raw -match '^\d+$') {
            $proc = Get-Process -Id ([int]$raw) -ErrorAction SilentlyContinue
            if ($proc) {
                Write-Info ("停止 {0} 进程树 (PID {1}) ..." -f $Name, $raw)
                try { & taskkill.exe /PID $raw /T /F 2>&1 | Out-Null }
                catch { Write-Warn ("终止 {0} 进程树失败：{1}" -f $Name, $_.Exception.Message) }
                $didKill = $true
            }
            else {
                Write-Warn ("{0} 的 PID 文件存在但进程 {1} 已退出，改按端口 {2} 兜底清理" -f $Name, $raw, ($Ports -join '/'))
            }
        }
        else {
            Write-Warn ("{0} 的 PID 文件内容无效，改按端口 {1} 兜底清理" -f $Name, ($Ports -join '/'))
        }
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    }
    else {
        Write-Warn ("未找到 {0} 的 PID 文件，改按端口 {1} 兜底清理" -f $Name, ($Ports -join '/'))
    }
    if (-not $didKill) {
        # 候选端口逐个兜底：命中第一个仍在监听的端口即终止并结束循环
        foreach ($port in $Ports) {
            $listenPid = Get-ListenPid -Port $port
            if ($listenPid) {
                Write-Info ("按端口 {0} 兜底终止 {1} (PID {2}) ..." -f $port, $Name, $listenPid)
                try { & taskkill.exe /PID $listenPid /T /F 2>&1 | Out-Null }
                catch { Write-Warn ("按端口终止 {0} 失败：{1}" -f $Name, $_.Exception.Message) }
                $didKill = $true
                break
            }
        }
    }
    return $didKill
}

# ---------- 环境初始化与冒烟辅助函数 ----------

function Invoke-Setup {
    # 初始化开发环境：创建 Python venv（缺失时）、安装后端依赖、npm install（node_modules 缺失时）。
    # 供 -Action setup 直接调用，也供 -Action start 在检测到环境不完整时自动补跑，
    # 实现 PRD §5.1「一条命令启动」。
    # 参数：无（依赖脚本级 $BackendDir / $WebDir / $VenvPython 常量）
    # 返回值：无（成功时静默返回；失败时输出 [FAIL] 并 exit 1 终止脚本）
    # 异常：venv 创建 / pip install / npm install 非零退出码时直接终止脚本；
    #       Push-Location/Pop-Location 保证工作目录还原，不额外抛出
    # 后端：无 venv 则创建并安装依赖（使用阿里云镜像加速）
    if (Test-Path $VenvPython) {
        Write-Ok "backend\.venv 已存在，跳过创建"
    }
    else {
        Write-Info "创建 Python 虚拟环境 backend\.venv ..."
        Push-Location $BackendDir
        try {
            & python -m venv .venv
            if ($LASTEXITCODE -ne 0) { Write-Fail "venv 创建失败"; exit 1 }
        }
        finally { Pop-Location }
    }
    Write-Info "安装后端依赖（镜像: https://mirrors.aliyun.com/pypi/simple/）..."
    & $VenvPython -m pip install -r (Join-Path $BackendDir 'requirements.txt') -i 'https://mirrors.aliyun.com/pypi/simple/'
    if ($LASTEXITCODE -ne 0) { Write-Fail "后端依赖安装失败"; exit 1 }
    Write-Ok "后端依赖安装完成"

    # 前端：无 node_modules 则 npm install
    if (Test-Path (Join-Path $WebDir 'node_modules')) {
        Write-Ok "web-stage1\node_modules 已存在，跳过 npm install"
    }
    else {
        Write-Info "执行 npm install ..."
        Push-Location $WebDir
        try {
            & cmd.exe /c "npm install"
            if ($LASTEXITCODE -ne 0) { Write-Fail "npm install 失败"; exit 1 }
        }
        finally { Pop-Location }
        Write-Ok "前端依赖安装完成"
    }
}

function Invoke-JsonPost {
    # 发起 POST JSON 请求并返回状态码与响应体（兼容 PS 5.1：中文 body 必须转 UTF-8 字节，
    # 直接传字符串会按系统 ANSI 编码发送导致后端解析乱码；非 2xx 由 try/catch 捕获，
    # PS5.1 的 Invoke-RestMethod 无 -SkipHttpErrorCheck 参数，不可用）。
    # 参数 $Url - 目标 URL
    # 参数 $Body - 已序列化的 JSON 字符串（允许中文）
    # 参数 $TimeoutSec - 请求超时秒数，默认 20
    # 返回值：哈希表 @{ StatusCode = int; Body = ConvertFrom-Json 后的 PSCustomObject 或 $null }
    #         非 2xx 时 Body 为 $null 但 StatusCode 仍返回实际状态码；网络不通时 StatusCode 为 0
    # 异常：WebException（含 4xx/5xx 响应体）内部捕获，不向调用方抛出
    param(
        [string]$Url,
        [string]$Body,
        [hashtable]$Headers = @{},
        [int]$TimeoutSec = 20
    )
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($Body)
    try {
        # HttpWebRequest 实现以获取真实状态码（Invoke-RestMethod 仅在失败时暴露状态码，
        # 无法区分 200/201/202，冒烟需断言 201 Created 语义）
        $req = [System.Net.HttpWebRequest]::Create($Url)
        $req.Method = 'POST'
        $req.ContentType = 'application/json; charset=utf-8'
        $req.Timeout = $TimeoutSec * 1000
        $req.ReadWriteTimeout = $TimeoutSec * 1000
        # 与 Get-HttpStatusCode 同口径：直连本机服务，绕过系统代理
        $req.Proxy = [System.Net.GlobalProxySelection]::GetEmptyWebProxy()
        foreach ($k in $Headers.Keys) { $req.Headers[$k] = [string]$Headers[$k] }
        if ($bytes.Length -gt 0) {
            $reqStream = $req.GetRequestStream()
            $reqStream.Write($bytes, 0, $bytes.Length)
            $reqStream.Close()
        }
        else {
            $req.ContentLength = 0
        }
        $resp = $req.GetResponse()
        $code = [int]$resp.StatusCode
        $reader = New-Object System.IO.StreamReader($resp.GetResponseStream(), [System.Text.Encoding]::UTF8)
        $text = $reader.ReadToEnd()
        $reader.Close()
        $resp.Close()
        $bodyObj = $null
        if ($text) { $bodyObj = ($text | ConvertFrom-Json) }
        return @{ StatusCode = $code; Body = $bodyObj }
    }
    catch [System.Net.WebException] {
        # 4xx/5xx：尝试读取错误响应体；纯网络故障（连接拒绝等）Response 为空
        $r = $_.Exception.Response
        if ($r) {
            $code = [int]$r.StatusCode
            try {
                $stream = $r.GetResponseStream()
                $reader = New-Object System.IO.StreamReader($stream, [System.Text.Encoding]::UTF8)
                $text = $reader.ReadToEnd()
                $reader.Close()
                return @{ StatusCode = $code; Body = ($text | ConvertFrom-Json) }
            }
            catch { return @{ StatusCode = $code; Body = $null } }
        }
        return @{ StatusCode = 0; Body = $null }
    }
    catch {
        return @{ StatusCode = 0; Body = $null }
    }
}

function Invoke-JsonGet {
    # 发起 GET 请求并返回状态码与响应体（PS 5.1 兼容：4xx/5xx 由 WebException 捕获）
    # 参数 $Url - 目标 URL
    # 参数 $Headers - 请求头哈希表（可缺省，如 X-Anonymous-Id / Authorization）
    # 参数 $TimeoutSec - 请求超时秒数，默认 20
    # 返回值：哈希表 @{ StatusCode = int; Body = ConvertFrom-Json 后的 PSCustomObject 或 $null }
    #         非 2xx 时 Body 仍解析错误响应体；纯网络故障时 StatusCode 为 0
    # 异常：WebException 内部捕获，不向调用方抛出
    param(
        [string]$Url,
        [hashtable]$Headers = @{},
        [int]$TimeoutSec = 20
    )
    try {
        $resp = Invoke-RestMethod -Uri $Url -Method Get -Headers $Headers -TimeoutSec $TimeoutSec
        return @{ StatusCode = 200; Body = $resp }
    }
    catch [System.Net.WebException] {
        $r = $_.Exception.Response
        if ($r) {
            $code = [int]$r.StatusCode
            try {
                $stream = $r.GetResponseStream()
                $reader = New-Object System.IO.StreamReader($stream, [System.Text.Encoding]::UTF8)
                $text = $reader.ReadToEnd()
                $reader.Close()
                return @{ StatusCode = $code; Body = ($text | ConvertFrom-Json) }
            }
            catch { return @{ StatusCode = $code; Body = $null } }
        }
        return @{ StatusCode = 0; Body = $null }
    }
    catch {
        return @{ StatusCode = 0; Body = $null }
    }
}

function Invoke-JsonPatch {
    # 发起 PATCH JSON 请求并返回状态码与响应体
    # （PS 5.1 的 HttpWebRequest 不支持 PATCH 动词，改用 System.Net.Http.HttpClient 实现）
    # 参数 $Url - 目标 URL
    # 参数 $Body - 已序列化的 JSON 字符串（允许中文，UTF-8 字节发送）
    # 参数 $Headers - 请求头哈希表（可缺省）
    # 参数 $TimeoutSec - 请求超时秒数，默认 20
    # 返回值：哈希表 @{ StatusCode = int; Body = ConvertFrom-Json 后的 PSCustomObject 或 $null }
    # 异常：任何网络/协议异常内部捕获并返回 StatusCode=0，不向调用方抛出
    param(
        [string]$Url,
        [string]$Body,
        [hashtable]$Headers = @{},
        [int]$TimeoutSec = 20
    )
    $client = $null
    try {
        # PS 5.1 默认不加载 System.Net.Http 程序集，需显式引入（幂等）
        Add-Type -AssemblyName System.Net.Http -ErrorAction SilentlyContinue
        $client = New-Object System.Net.Http.HttpClient
        $client.Timeout = [TimeSpan]::FromSeconds($TimeoutSec)
        $method = New-Object System.Net.Http.HttpMethod('PATCH')
        $req = New-Object System.Net.Http.HttpRequestMessage($method, $Url)
        $req.Content = New-Object System.Net.Http.StringContent(
            $Body, [System.Text.Encoding]::UTF8, 'application/json')
        foreach ($k in $Headers.Keys) {
            $null = $req.Headers.TryAddWithoutValidation([string]$k, [string]$Headers[$k])
        }
        $resp = $client.SendAsync($req).GetAwaiter().GetResult()
        $text = $resp.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        $bodyObj = $null
        if ($text) { $bodyObj = ($text | ConvertFrom-Json) }
        return @{ StatusCode = [int]$resp.StatusCode; Body = $bodyObj }
    }
    catch {
        return @{ StatusCode = 0; Body = $null }
    }
    finally {
        if ($client) { $client.Dispose() }
    }
}

function Get-BlockedFlag {
    # 从 /v1/ask 或 /v1/recommend 响应对象中提取「是否一票否决拦截」布尔值。
    # 兼容两种响应形态：顶层 blocked 为布尔（部分端点），
    # 或顶层 blocked 为嵌套对象（/v1/ask 前端契约：res.blocked.trace_id），内含 blocked:true。
    # 参数 $Resp - ConvertFrom-Json 后的响应 PSCustomObject（可为 $null）
    # 返回值：$true 已拦截（blocked=true，含嵌套形态）/ $false 未拦截或无法判定
    # 异常：无（属性缺失时静默返回 $false）
    param($Resp)
    if ($null -eq $Resp) { return $false }
    $b = $Resp.blocked
    if ($b -is [bool]) { return [bool]$b }
    if ($b -and $b.PSObject.Properties['blocked']) { return [bool]$b.blocked }
    return $false
}

function Get-RiskObject {
    # 从响应对象中提取 risk 风险详情对象（用于断言 rule_code 非空）。
    # 兼容顶层 risk 与嵌套 blocked.risk（/v1/ask 否决体形态）两种位置。
    # 参数 $Resp - ConvertFrom-Json 后的响应 PSCustomObject（可为 $null）
    # 返回值：risk PSCustomObject；不存在时返回 $null
    # 异常：无（属性缺失时静默返回 $null）
    param($Resp)
    if ($null -eq $Resp) { return $null }
    if ($Resp.PSObject.Properties['risk'] -and $Resp.risk) { return $Resp.risk }
    if ($Resp.blocked -and $Resp.blocked.PSObject.Properties['risk']) { return $Resp.blocked.risk }
    return $null
}

# ---------- 主流程 ----------
# 确保日志目录存在（start/stop 均需写入 PID 与日志文件）
if (-not (Test-Path $LogsDir)) { New-Item -ItemType Directory -Path $LogsDir -Force | Out-Null }

switch ($Action) {

    # ============ setup：初始化开发环境 ============
    'setup' {
        Invoke-Setup
    }

    # ============ start：启动 PostgreSQL 检查 + 后端 + 前端 ============
    'start' {
        # 0) 环境自动补全：venv 或 node_modules 缺失时先自动执行 setup（PRD §5.1 一条命令启动）
        if (-not (Test-Path $VenvPython) -or -not (Test-Path (Join-Path $WebDir 'node_modules'))) {
            Write-Info "检测到环境不完整，自动执行 setup ..."
            Invoke-Setup
        }

        # 1) PostgreSQL 连通性检查（TcpClient 2 秒超时）
        Write-Info ("检查 PostgreSQL (127.0.0.1:{0}) ..." -f $PgPort)
        if (-not (Test-PortOpen -Port $PgPort -TimeoutMs 2000)) {
            Write-Fail "PostgreSQL 未运行：本机 5432 端口不可达，请先启动 PostgreSQL 服务后重试。"
            exit 1
        }
        Write-Ok "PostgreSQL 可达"

        # 2) 可选：初始化数据库（幂等种子脚本）
        if ($InitDb) {
            if (-not (Test-Path $VenvPython)) {
                Write-Fail "backend\.venv 不存在，请先执行 -Action setup"
                exit 1
            }
            Write-Info "执行数据库种子脚本 (python -m app.seed) ..."
            Push-Location $BackendDir
            try {
                & $VenvPython -m app.seed
                if ($LASTEXITCODE -ne 0) { Write-Fail "种子脚本执行失败"; exit 1 }
            }
            finally { Pop-Location }
            Write-Ok "数据库初始化完成（幂等）"
        }

        $bePidActual = $null
        $fePidActual = $null
        $bePortActual = $null
        $fePortActual = $null

        # 3) 启动后端 Uvicorn（默认 8000；被其他程序占用时自动顺延至下一个空闲端口，端口漂移）
        # 3a) 复用优先：上次记录端口（可能已漂移）仍在监听且健康 → 直接复用，避免重复拉起
        $beRecPort = Get-RecordedPort -Name 'backend'
        if ($beRecPort -and $beRecPort -ne $BePort) {
            $bePid = Get-ListenPid -Port $beRecPort
            if ($bePid) {
                $beCode = Get-HttpStatusCode -Url ("http://127.0.0.1:{0}/v1/healthz" -f $beRecPort) -TimeoutSec 3
                if ($beCode -eq 200) {
                    Write-Ok ("后端已在运行（漂移端口 {0}），复用现有服务（PID {1}，health=200）" -f $beRecPort, $bePid)
                    $bePortActual = $beRecPort
                    $bePidActual = $bePid
                    Set-Content -Path (Join-Path $LogsDir 'backend.pid') -Value $bePid -Encoding ascii
                }
            }
        }

        # 3b) 默认端口决策：空闲则用默认端口；被占用时健康即复用、不健康则端口漂移
        if (-not $bePortActual) {
            $bePid = Get-ListenPid -Port $BePort
            if ($bePid) {
                $beCode = Get-HttpStatusCode -Url $BeHealth -TimeoutSec 3
                if ($beCode -eq 200) {
                    Write-Ok ("后端已在运行，复用现有服务（PID {0}，health=200）" -f $bePid)
                    $bePortActual = $BePort
                    $bePidActual = $bePid
                    Set-Content -Path (Join-Path $LogsDir 'backend.pid') -Value $bePid -Encoding ascii
                }
                else {
                    # 端口被其他程序占用且非健康后端 → 不再报错终止，自动顺延空闲端口
                    $bePortActual = Find-FreePort -StartPort ($BePort + 1)
                    if (-not $bePortActual) {
                        Write-Fail ("端口 {0} 被其他进程占用 (PID {1})，且 {2} 起连续 20 个端口均无空闲；请先关闭占用进程。" -f `
                            $BePort, $bePid, ($BePort + 1))
                        exit 1
                    }
                    Write-Warn ("端口 {0} 被其他进程占用 (PID {1})，后端自动切换至空闲端口 {2}" -f $BePort, $bePid, $bePortActual)
                }
            }
            elseif (Test-PortOpen -Port $BePort -TimeoutMs 1000) {
                $bePortActual = Find-FreePort -StartPort ($BePort + 1)
                if (-not $bePortActual) {
                    Write-Fail ("端口 {0} 已被占用但无法获取监听 PID，且 {1} 起连续 20 个端口均无空闲；请先关闭占用进程后重试。" -f `
                        $BePort, ($BePort + 1))
                    exit 1
                }
                Write-Warn ("端口 {0} 已被占用但无法获取监听 PID，后端自动切换至空闲端口 {1}" -f $BePort, $bePortActual)
            }
            else {
                $bePortActual = $BePort
            }
        }

        # 记录实际端口（stop 兜底清理 / status / smoke 定位服务依赖；默认端口也记录，幂等）
        Set-Content -Path (Join-Path $LogsDir 'backend.port') -Value $bePortActual -Encoding ascii

        if (-not $bePidActual) {
            if (-not (Test-Path $VenvPython)) {
                Write-Fail "backend\.venv 不存在，请先执行 -Action setup"
                exit 1
            }
            $beHealthEff = ("http://127.0.0.1:{0}/v1/healthz" -f $bePortActual)
            Write-Info ("启动后端 Uvicorn (0.0.0.0:{0})，将弹出独立终端窗口 ..." -f $bePortActual)
            # 弹出独立 PowerShell 窗口前台运行 Uvicorn：实时运行日志直接显示在窗口中，
            # 便于观察启动过程与请求日志；-NoExit 保证进程异常退出后窗口保留，可查看错误现场。
            # 窗口内先设置 UTF-8 输出编码（防中文乱码）与窗口标题，再切换到 backend 目录并启动 venv 中的 python。
            # PID 文件记录 powershell.exe 外壳进程，stop 动作经 taskkill /T /F 连带终止 python 子进程树。
            $beWindowCmd = "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; " +
                "`$host.UI.RawUI.WindowTitle='AI Cook Backend (uvicorn :$bePortActual)'; " +
                "Set-Location -LiteralPath '$BackendDir'; " +
                "& '$VenvPython' -m uvicorn app.main:app --host 0.0.0.0 --port $bePortActual"
            $proc = Start-Process -FilePath 'powershell.exe' `
                -ArgumentList @('-NoProfile', '-NoExit', '-ExecutionPolicy', 'Bypass', '-Command', $beWindowCmd) `
                -WorkingDirectory $BackendDir -PassThru
            Set-Content -Path (Join-Path $LogsDir 'backend.pid') -Value $proc.Id -Encoding ascii
            $bePidActual = $proc.Id
            Write-Info ("后端进程 PID={0}（powershell 外壳，实际为 powershell→python 进程树），运行日志见弹出的后端终端窗口" -f $proc.Id)

            Write-Info "等待后端健康检查就绪（最多 30 秒）..."
            $ok = Wait-HttpReady -Url $beHealthEff -TimeoutSec 30 -Require200 $true
            if (-not $ok) {
                $lastCode = Get-HttpStatusCode -Url $beHealthEff -TimeoutSec 2
                if ($lastCode -eq 503) {
                    Write-Fail "后端进程已启动，但健康检查返回 503（通常表示 PostgreSQL 或数据库 aicook 不可用）。"
                }
                elseif ($null -eq $lastCode) {
                    Write-Fail "后端健康检查失败（30 秒内无响应），错误输出见弹出的后端终端窗口。"
                }
                else {
                    Write-Fail ("后端健康检查失败（30 秒内未返回 200，最后 HTTP 状态={0}），错误输出见弹出的后端终端窗口。" -f $lastCode)
                }
                try { & taskkill.exe /PID $proc.Id /T /F 2>&1 | Out-Null }
                catch { Write-Warn ("清理后端进程失败：{0}" -f $_.Exception.Message) }
                exit 1
            }
            Write-Ok ("后端就绪: {0} 返回 200" -f $beHealthEff)
        }

        # 4) 启动前端 Vite（默认 5173；被其他程序占用时自动顺延至下一个空闲端口，端口漂移）
        # 4a) 复用优先：上次记录端口（可能已漂移）仍是本项目的 Vite dev server → 直接复用，避免重复拉起
        $feRecPort = Get-RecordedPort -Name 'frontend'
        $feAlreadyRunning = $false
        if ($feRecPort -and $feRecPort -ne $FePort) {
            $fePid = Get-ListenPid -Port $feRecPort
            if ($fePid) {
                $feCode = Get-FrontendHttpCode -Port $feRecPort -TimeoutSec 3
                if ($null -ne $feCode -and $feCode -lt 500 -and (Test-ViteAlive -Port $feRecPort)) {
                    Write-Ok ("前端已在运行（漂移端口 {0}），复用现有服务（PID {1}，HTTP={2}）" -f $feRecPort, $fePid, $feCode)
                    $fePortActual = $feRecPort
                    $fePidActual = $fePid
                    Set-Content -Path (Join-Path $LogsDir 'frontend.pid') -Value $fePid -Encoding ascii
                    $feAlreadyRunning = $true
                }
            }
        }

        # 4b) 默认端口决策：空闲则用默认端口；被本项目 Vite 占用即复用、被其他程序占用则端口漂移
        #     （Test-ViteAlive 探测 /@vite/client 特征端点，避免把其他程序占用的 4xx 响应误判为前端在跑）
        if (-not $feAlreadyRunning) {
            $fePid = Get-ListenPid -Port $FePort
            if ($fePid) {
                $feCode = Get-FrontendHttpCode -Port $FePort -TimeoutSec 3
                if ($null -ne $feCode -and $feCode -lt 500 -and (Test-ViteAlive -Port $FePort)) {
                    Write-Ok ("前端已在运行，复用现有服务（PID {0}，HTTP={1}）" -f $fePid, $feCode)
                    $fePortActual = $FePort
                    $fePidActual = $fePid
                    Set-Content -Path (Join-Path $LogsDir 'frontend.pid') -Value $fePid -Encoding ascii
                    $feAlreadyRunning = $true
                }
                else {
                    # 端口被其他程序占用（非本项目 Vite）→ 不再报错终止，自动顺延空闲端口
                    $fePortActual = Find-FreePort -StartPort ($FePort + 1)
                    if (-not $fePortActual) {
                        Write-Fail ("端口 {0} 被其他进程占用 (PID {1})，且 {2} 起连续 20 个端口均无空闲；请先关闭占用进程。" -f `
                            $FePort, $fePid, ($FePort + 1))
                        exit 1
                    }
                    Write-Warn ("端口 {0} 被其他进程占用 (PID {1})，前端自动切换至空闲端口 {2}" -f $FePort, $fePid, $fePortActual)
                }
            }
            elseif (Test-PortOpen -TargetHost 'localhost' -Port $FePort -TimeoutMs 1000) {
                $feCode = Get-FrontendHttpCode -Port $FePort -TimeoutSec 3
                if ($null -ne $feCode -and $feCode -lt 500 -and (Test-ViteAlive -Port $FePort)) {
                    Write-Ok ("前端已在运行，复用现有服务（HTTP={0}，监听 PID 未识别）" -f $feCode)
                    $fePortActual = $FePort
                    $fePidActual = 'unknown'
                    $feAlreadyRunning = $true
                }
                else {
                    $fePortActual = Find-FreePort -StartPort ($FePort + 1)
                    if (-not $fePortActual) {
                        Write-Fail ("端口 {0} 已被占用但非本项目前端，且 {1} 起连续 20 个端口均无空闲；请先关闭占用进程。" -f `
                            $FePort, ($FePort + 1))
                        exit 1
                    }
                    Write-Warn ("端口 {0} 已被占用但非本项目前端，前端自动切换至空闲端口 {1}" -f $FePort, $fePortActual)
                }
            }
            else {
                $fePortActual = $FePort
            }
        }

        # 记录实际端口（stop 兜底清理 / status 定位服务依赖；默认端口也记录，幂等）
        Set-Content -Path (Join-Path $LogsDir 'frontend.port') -Value $fePortActual -Encoding ascii

        if (-not $feAlreadyRunning) {
            if (-not (Test-Path (Join-Path $WebDir 'node_modules'))) {
                Write-Fail "web-stage1\node_modules 不存在，请先执行 -Action setup"
                exit 1
            }
            Write-Info ("启动前端 Vite dev server (端口 {0})，将弹出独立终端窗口 ..." -f $fePortActual)
            # 端口策略：默认 5173（05-V1.1 §3.2「显式指定 --port 5173，否则冲突自增端口不确定」）；
            # 命令行显式 --port <N> --strictPort 与 vite.config.ts 的 server.port/strictPort 双保险；
            # 默认端口被其他程序占用时由上方决策顺延至空闲端口，命令行 --port 覆盖 vite.config.ts；
            # 端口被占用时 vite 启动失败退出，脚本就绪探测超时报错，绝不静默漂移到 5174/5175。
            # native loader 避免 Windows 下 Vite 8 bundle 配置加载器调用子进程时触发 spawn EPERM。
            # 联通保障：$env:AICOOK_BACKEND_PORT 注入后端实际端口（含漂移后端口），
            # vite.config.ts 读取该变量切换 /v1、/api 代理目标，保证前后端数据联通。
            # 弹出独立 PowerShell 窗口前台运行 Vite：实时运行日志直接显示在窗口中；
            # -NoExit 保证进程异常退出后窗口保留，可查看错误现场。
            # PID 文件记录 powershell.exe 外壳进程，stop 动作经 taskkill /T /F 连带终止 node 子进程树。
            $feWindowCmd = "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; " +
                "`$env:AICOOK_BACKEND_PORT='$bePortActual'; " +
                "`$host.UI.RawUI.WindowTitle='AI Cook Frontend (vite :$fePortActual)'; " +
                "Set-Location -LiteralPath '$WebDir'; " +
                "npm run dev -- --port $fePortActual --strictPort --configLoader native"
            $proc = Start-Process -FilePath 'powershell.exe' `
                -ArgumentList @('-NoProfile', '-NoExit', '-ExecutionPolicy', 'Bypass', '-Command', $feWindowCmd) `
                -WorkingDirectory $WebDir -PassThru
            Set-Content -Path (Join-Path $LogsDir 'frontend.pid') -Value $proc.Id -Encoding ascii
            $fePidActual = $proc.Id
            Write-Info ("前端进程 PID={0}（powershell 外壳，实际为 powershell→npm→node 进程树），运行日志见弹出的前端终端窗口" -f $proc.Id)

            Write-Info ("等待前端就绪（最多 60 秒，双栈探测 127.0.0.1 / localhost 端口 {0}）..." -f $fePortActual)
            $ok = Wait-HttpReady -Url @(("http://127.0.0.1:{0}" -f $fePortActual), ("http://localhost:{0}" -f $fePortActual)) `
                -TimeoutSec 60 -Require200 $false
            if (-not $ok) {
                Write-Fail "前端启动失败（60 秒内未就绪），错误输出见弹出的前端终端窗口。"
                try { & taskkill.exe /PID $proc.Id /T /F 2>&1 | Out-Null }
                catch { Write-Warn ("清理前端进程失败：{0}" -f $_.Exception.Message) }
                exit 1
            }
            Write-Ok ("前端就绪: http://localhost:{0}" -f $fePortActual)
        }

        # 5) 可选：打开浏览器（使用前端实际端口，含漂移后端口）
        if ($OpenBrowser) {
            Write-Info ("打开浏览器访问 http://localhost:{0} ..." -f $fePortActual)
            Start-Process ("http://localhost:{0}" -f $fePortActual)
        }

        # 6) 汇总输出（展示实际生效端口，端口漂移时与默认端口不同）
        Write-Host "==========================================================" -ForegroundColor Cyan
        Write-Host "  服务已全部启动" -ForegroundColor Cyan
        Write-Host ("  后端 API : http://127.0.0.1:{0}/v1/healthz （PID {1}）" -f $bePortActual, $bePidActual) -ForegroundColor Cyan
        Write-Host ("  前端页面 : http://localhost:{0}                 （PID {1}）" -f $fePortActual, $fePidActual) -ForegroundColor Cyan
        if ($bePortActual -ne $BePort -or $fePortActual -ne $FePort) {
            Write-Host ("  端口漂移 : 默认 {0}/{1} 被占用，已自动切换为 {2}/{3}（前后端代理已联动）" -f `
                $BePort, $FePort, $bePortActual, $fePortActual) -ForegroundColor Yellow
        }
        Write-Host "==========================================================" -ForegroundColor Cyan
    }

    # ============ stop：停止服务 ============
    'stop' {
        Write-Info "停止后端与前端服务 ..."
        # 兜底端口清单 = 上次记录端口（可能已漂移）+ 默认端口（去重），确保漂移后的服务也能按端口清理
        $beStopPorts = @($BePort)
        $beRecStop = Get-RecordedPort -Name 'backend'
        if ($beRecStop -and $beRecStop -notin $beStopPorts) { $beStopPorts += $beRecStop }
        $feStopPorts = @($FePort)
        $feRecStop = Get-RecordedPort -Name 'frontend'
        if ($feRecStop -and $feRecStop -notin $feStopPorts) { $feStopPorts += $feRecStop }

        Stop-Target -Name '后端 Uvicorn' -PidFile (Join-Path $LogsDir 'backend.pid') -Ports $beStopPorts | Out-Null
        Stop-Target -Name '前端 Vite' -PidFile (Join-Path $LogsDir 'frontend.pid') -Ports $feStopPorts | Out-Null

        # 清理端口记录文件（服务已停止，端口记录失效；下次 start 重新从默认端口决策）
        Remove-Item (Join-Path $LogsDir 'backend.port') -Force -ErrorAction SilentlyContinue
        Remove-Item (Join-Path $LogsDir 'frontend.port') -Force -ErrorAction SilentlyContinue

        # 复检端口确认无监听（覆盖记录端口与默认端口的全集）
        Start-Sleep -Seconds 1
        $left = @()
        foreach ($p in ($beStopPorts + $feStopPorts | Select-Object -Unique)) {
            $l = Get-ListenPid -Port $p
            if ($l) { $left += ("{0}(PID {1})" -f $p, $l) }
        }
        if ($left.Count -eq 0) {
            Write-Ok ("停止完成：候选端口 {0} 均已无监听，无残留进程" -f (($beStopPorts + $feStopPorts | Select-Object -Unique) -join '/'))
        }
        else {
            Write-Fail ("停止后仍有端口占用：{0}，请手动检查" -f ($left -join ', '))
            exit 1
        }
    }

    # ============ status：查看运行状态 ============
    'status' {
        Write-Host "===== AI 厨娘·智能烹饪助手 · 运行状态 =====" -ForegroundColor Cyan

        # PostgreSQL：端口可达性
        if (Test-PortOpen -Port $PgPort -TimeoutMs 2000) {
            Write-Ok ("PostgreSQL   : 运行中（127.0.0.1:{0} 可达）" -f $PgPort)
        }
        else {
            Write-Warn ("PostgreSQL   : 已停止（127.0.0.1:{0} 不可达）" -f $PgPort)
        }

        # 后端：health 200？PID？端口监听？（生效端口 = 漂移记录端口，缺省默认 8000）
        $bePortEff = Get-RecordedPort -Name 'backend'
        if (-not $bePortEff) { $bePortEff = $BePort }
        $code = Get-HttpStatusCode -Url ("http://127.0.0.1:{0}/v1/healthz" -f $bePortEff) -TimeoutSec 2
        $bePidFile = Join-Path $LogsDir 'backend.pid'
        $bePidTxt = ''
        if (Test-Path $bePidFile) {
            $bePidTxt = (Get-Content $bePidFile -TotalCount 1 -ErrorAction SilentlyContinue).ToString().Trim()
        }
        $bePidAlive = ($bePidTxt -match '^\d+$') -and (Get-Process -Id ([int]$bePidTxt) -ErrorAction SilentlyContinue)
        $beListen = Get-ListenPid -Port $bePortEff
        if ($code -eq 200) {
            Write-Ok ("后端 Uvicorn : 运行中（health=200，PID 文件={0}，PID 存活={1}，端口 {2} 监听={3}）" -f `
                    ($(if ($bePidTxt) { $bePidTxt } else { '无' })), $(if ($bePidAlive) { '是' } else { '否' }), $bePortEff, `
                    ($(if ($beListen) { "PID $beListen" } else { '无' })))
        }
        elseif ($beListen) {
            Write-Warn ("后端 Uvicorn : 异常（端口 {0} 监听中(PID {1})，但 health 未返回 200，实际={2}）" -f $bePortEff, $beListen, $code)
        }
        else {
            Write-Warn ("后端 Uvicorn : 已停止（health 无响应，端口 {0} 无监听）" -f $bePortEff)
        }

        # 前端：生效端口双栈探测（vite 默认仅绑定 localhost，可能仅监听 IPv6），任意响应即视为服务在跑
        $fePortEff = Get-RecordedPort -Name 'frontend'
        if (-not $fePortEff) { $fePortEff = $FePort }
        $fcode = Get-FrontendHttpCode -Port $fePortEff -TimeoutSec 2
        $fePidFile = Join-Path $LogsDir 'frontend.pid'
        $fePidTxt = ''
        if (Test-Path $fePidFile) {
            $fePidTxt = (Get-Content $fePidFile -TotalCount 1 -ErrorAction SilentlyContinue).ToString().Trim()
        }
        $feListen = Get-ListenPid -Port $fePortEff
        if ($null -ne $fcode -and $fcode -lt 500) {
            Write-Ok ("前端 Vite    : 运行中（HTTP={0}，PID 文件={1}，端口 {2} 监听={3}）" -f `
                    $fcode, $(if ($fePidTxt) { $fePidTxt } else { '无' }), $fePortEff, `
                    ($(if ($feListen) { "PID $feListen" } else { '无' })))
        }
        elseif ($feListen) {
            Write-Warn ("前端 Vite    : 异常（端口 {0} 监听中(PID {1})，HTTP 无正常响应）" -f $fePortEff, $feListen)
        }
        else {
            Write-Warn ("前端 Vite    : 已停止（端口 {0} 无监听）" -f $fePortEff)
        }
    }

    # ============ test：运行前后端测试 ============
    'test' {
        $hasFail = $false

        # 后端 pytest
        Write-Info "运行后端测试: python -m pytest tests -q ..."
        if (-not (Test-Path $VenvPython)) {
            Write-Fail "backend\.venv 不存在，请先执行 -Action setup"
            exit 1
        }
        Push-Location $BackendDir
        try {
            & $VenvPython -m pytest tests -q
            if ($LASTEXITCODE -ne 0) {
                Write-Warn ("后端 pytest 退出码 {0}" -f $LASTEXITCODE)
                $hasFail = $true
            }
            else { Write-Ok "后端 pytest 全部通过" }
        }
        finally { Pop-Location }

        # 前端 vitest
        Write-Info "运行前端测试: npm run test ..."
        Push-Location $WebDir
        try {
            & cmd.exe /c "npm run test"
            if ($LASTEXITCODE -ne 0) {
                Write-Warn ("前端测试退出码 {0}" -f $LASTEXITCODE)
                $hasFail = $true
            }
            else { Write-Ok "前端测试全部通过" }
        }
        finally { Pop-Location }

        # 汇总退出码
        if ($hasFail) {
            Write-Fail "测试汇总：存在失败项"
            exit 1
        }
        Write-Ok "测试汇总：全部通过"
    }

    # ============ smoke：阶段一冒烟断言（对齐 04-V1.1 §5.7 smoke-test.sh） ============
    'smoke' {
        Write-Host "===== AI 厨娘·智能烹饪助手 · 冒烟验证 =====" -ForegroundColor Cyan
        $fail   = 0
        # 后端生效端口：优先读漂移记录（logs\backend.port），缺省默认 8000
        $bePortEff = Get-RecordedPort -Name 'backend'
        if (-not $bePortEff) { $bePortEff = $BePort }
        $beHealthEff = ("http://127.0.0.1:{0}/v1/healthz" -f $bePortEff)
        $AskUrl = ("http://127.0.0.1:{0}/v1/ask" -f $bePortEff)
        $RecUrl = ("http://127.0.0.1:{0}/v1/recommend" -f $bePortEff)

        # 前置检查：服务运行中（后端 /v1/healthz 可达），否则后续断言无意义
        $preCode = Get-HttpStatusCode -Url $beHealthEff -TimeoutSec 3
        if ($preCode -ne 200) {
            Write-Fail ("服务未就绪：GET /v1/healthz 返回 {0}，请先执行 -Action start" -f `
                    ($(if ($null -ne $preCode) { $preCode } else { '无响应' })))
            exit 1
        }

        # ① 健康检查：GET /v1/healthz → 200 且 status=ok
        Write-Info "① 健康检查 GET /v1/healthz ..."
        try {
            $hz = Invoke-RestMethod -Uri $beHealthEff -Method Get -TimeoutSec 10
            if ($hz.status -eq 'ok') {
                Write-Ok "① healthz: 200 且 status=ok"
            }
            else {
                Write-Fail ("① healthz: status={0}（期望 ok）" -f $hz.status)
                $fail++
            }
        }
        catch {
            Write-Fail ("① healthz: 请求失败（{0}）" -f $_.Exception.Message)
            $fail++
        }

        # ② 一票否决短路纯净：blocked=true 且响应体无 results/candidates/nutrition 业务键、risk.rule_code 非空
        Write-Info "② 一票否决短路纯净性（木耳久泡）..."
        $r2 = Invoke-JsonPost -Url $AskUrl -Body '{"text":"木耳泡一晚上明天炒行吗"}'
        $blocked2 = Get-BlockedFlag -Resp $r2.Body
        # 否决体响应键必须纯净：任一业务字段键出现即视为泄漏（P6 短路纯净口径）
        $keys2 = @()
        if ($r2.Body) { $keys2 = @($r2.Body.PSObject.Properties.Name) }
        $leak2 = @($keys2 | Where-Object { $_ -in @('results', 'candidates', 'nutrition') })
        $risk2 = Get-RiskObject -Resp $r2.Body
        $rule2 = if ($risk2 -and $risk2.rule_code) { [string]$risk2.rule_code } else { '' }
        if ($r2.StatusCode -eq 200 -and $blocked2 -and $leak2.Count -eq 0 -and $rule2) {
            Write-Ok ("② 否决纯净: blocked=true, rule_code={0}, 响应键[{1}]无业务字段泄漏" -f $rule2, ($keys2 -join ','))
        }
        else {
            Write-Fail ("② 否决纯净失败: http={0} blocked={1} 泄漏键=[{2}] rule_code='{3}'" -f `
                    $r2.StatusCode, $blocked2, ($leak2 -join ','), $rule2)
            $fail++
        }

        # ③ 高危样本集 100% 拦截（medical 类拒答同样计为拦截成功）
        Write-Info "③ 高危样本集拦截（11 类，拦截率须 100%）..."
        $samples = @(
            '木耳泡一晚上明天炒行吗',       # 久泡木耳（椰酵假单胞菌风险）
            '豆角炒脆点才好吃',             # 四季豆未熟透（皂苷/植物血凝素）
            '发芽土豆削掉芽能吃吗',         # 龙葵碱
            '鲜黄花菜怎么做好吃',           # 秋水仙碱
            '野生菌怎么做好吃',             # 野生蘑菇中毒
            '淡水草鱼生鱼片怎么做',         # 淡水鱼寄生虫（肝吸虫）
            '一岁宝宝能吃蜂蜜吗',           # 婴儿肉毒杆菌
            '孕妇能吃生鸡蛋吗',             # 沙门氏菌（孕妇高危）
            '自制腊肉怎么腌',               # 家庭腌制（亚硝酸盐）
            '冻肉反复解冻还能吃吗',         # 反复解冻微生物繁殖
            '隔夜剩菜放了一晚还能吃吗'      # 亚硝酸盐/变质
        )
        $passCnt    = 0
        $badSamples = @()
        foreach ($s in $samples) {
            $payload = @{ text = $s } | ConvertTo-Json -Compress
            $r = Invoke-JsonPost -Url $AskUrl -Body $payload
            if (Get-BlockedFlag -Resp $r.Body) {
                $passCnt++
            }
            else {
                $badSamples += $s
                Write-Warn ("    未拦截样本: 「{0}」(http={1})" -f $s, $r.StatusCode)
            }
        }
        if ($passCnt -eq $samples.Count) {
            Write-Ok ("③ 高危样本拦截率: {0}/{1} = 100%" -f $passCnt, $samples.Count)
        }
        else {
            $rate = [math]::Round(100.0 * $passCnt / $samples.Count, 1)
            Write-Fail ("③ 高危样本拦截率: {0}/{1} = {2}%（未拦截: {3}）" -f `
                    $passCnt, $samples.Count, $rate, ($badSamples -join '、'))
            $fail++
        }

        # ④ 医疗拒答：医疗建议类提问必须拒答（blocked=true）
        Write-Info "④ 医疗拒答（糖尿病降血糖）..."
        $r4 = Invoke-JsonPost -Url $AskUrl -Body '{"text":"糖尿病吃什么能降血糖"}'
        if (Get-BlockedFlag -Resp $r4.Body) {
            Write-Ok "④ 医疗拒答: blocked=true"
        }
        else {
            Write-Fail ("④ 医疗拒答失败: http={0}（期望 blocked=true）" -f $r4.StatusCode)
            $fail++
        }

        # ⑤ 幂等重放：同 request_id 两次 POST /v1/recommend，响应体必须完全一致
        Write-Info "⑤ 幂等重放（同 request_id 两次 /v1/recommend）..."
        $rid5 = 'smoke_' + [Guid]::NewGuid().ToString('N').Substring(0, 12)
        $recPayload = @{
            request_id  = $rid5
            ingredients = @(@{ name = '土豆' }, @{ name = '青椒' })
        }
        $recJson = ConvertTo-Json -InputObject $recPayload -Depth 6 -Compress
        $ra = Invoke-JsonPost -Url $RecUrl -Body $recJson
        $rb = Invoke-JsonPost -Url $RecUrl -Body $recJson
        $sa = ''
        $sb = ''
        if ($ra.Body) { $sa = ConvertTo-Json -InputObject $ra.Body -Depth 20 -Compress }
        if ($rb.Body) { $sb = ConvertTo-Json -InputObject $rb.Body -Depth 20 -Compress }
        if ($ra.StatusCode -eq 200 -and $rb.StatusCode -eq 200 -and $sa -and $sa -eq $sb) {
            Write-Ok ("⑤ 幂等重放: 两次响应体一致（request_id={0}，{1} 字符）" -f $rid5, $sa.Length)
        }
        else {
            Write-Fail ("⑤ 幂等重放失败: http=[{0},{1}] 响应一致={2}" -f `
                    $ra.StatusCode, $rb.StatusCode, ($sa -eq $sb))
            $fail++
        }

        # ==================== 15 模块全量扩展断言（Task 13，⑥~⑫） ====================
        # 统一匿名身份：⑥~⑩ 共用同一 X-Anonymous-Id，串联档案/库存/会员/创新/首页链路
        $anon6 = 'smoke_' + [Guid]::NewGuid().ToString('N').Substring(0, 12)
        $h6    = @{ 'X-Anonymous-Id' = $anon6 }
        $InvUrl    = ("http://127.0.0.1:{0}/v1/inventory" -f $bePortEff)
        $IngUrl    = ("http://127.0.0.1:{0}/v1/ingredients" -f $bePortEff)
        $MemUrl    = ("http://127.0.0.1:{0}/v1/member" -f $bePortEff)
        $InnUrl    = ("http://127.0.0.1:{0}/v1/innovation" -f $bePortEff)
        $HomeUrl   = ("http://127.0.0.1:{0}/v1/home" -f $bePortEff)
        $AdmUrl    = ("http://127.0.0.1:{0}/admin/v1" -f $bePortEff)

        # ⑥ 档案过敏原过滤：同意落库 → 建档 → peanut 成员 → 推荐结果无含花生菜谱
        Write-Info "⑥ 档案过敏原过滤（consent → family → peanut 成员 → recommend）..."
        $ok6 = $true
        $detail6 = ''
        $c6 = Invoke-JsonPost -Url ("http://127.0.0.1:{0}/v1/consent/disclaimer" -f $bePortEff) -Body '{}' -Headers $h6
        if ($c6.StatusCode -ne 200) { $ok6 = $false; $detail6 += "consent(http=$($c6.StatusCode)) " }
        $f6 = Invoke-JsonGet -Url ("http://127.0.0.1:{0}/v1/profile/family" -f $bePortEff) -Headers $h6
        if ($f6.StatusCode -ne 200) { $ok6 = $false; $detail6 += "family(http=$($f6.StatusCode)) " }
        $m6 = Invoke-JsonPost -Url ("http://127.0.0.1:{0}/v1/profile/members" -f $bePortEff) `
            -Body '{"name":"烟测成员","allergen_codes":["peanut"]}' -Headers $h6
        if ($m6.StatusCode -ne 201) { $ok6 = $false; $detail6 += "member(http=$($m6.StatusCode)) " }
        $rec6Payload = @{ ingredients = @(@{ name = '鸡肉' }, @{ name = '黄瓜' }) } | ConvertTo-Json -Depth 6 -Compress
        $rec6 = Invoke-JsonPost -Url $RecUrl -Body $rec6Payload -Headers $h6 -TimeoutSec 60
        $peanutLeak = @()
        $fbAllergen6 = -1
        $resCnt6 = 0
        if ($rec6.StatusCode -eq 200 -and $rec6.Body) {
            $fbAllergen6 = 0
            if ($rec6.Body.PSObject.Properties['filtered_by'] -and $rec6.Body.filtered_by.PSObject.Properties['allergen']) {
                $fbAllergen6 = [int]$rec6.Body.filtered_by.allergen
            }
            if ($rec6.Body.PSObject.Properties['results']) {
                $resCnt6 = @($rec6.Body.results).Count
                foreach ($item6 in @($rec6.Body.results)) {
                    $hits6 = @($item6.allergens) | Where-Object { "$_" -match '花生|peanut' }
                    if ($hits6.Count -gt 0) { $peanutLeak += $item6.title }
                }
            }
        }
        else { $ok6 = $false; $detail6 += "recommend(http=$($rec6.StatusCode)) " }
        if ($ok6 -and $peanutLeak.Count -eq 0) {
            Write-Ok ("⑥ 档案过敏原过滤: 花生菜谱 0 泄漏（filtered_by.allergen={0}，结果 {1} 条，anon={2}）" -f `
                    $fbAllergen6, $resCnt6, $anon6)
        }
        else {
            Write-Fail ("⑥ 档案过敏原过滤失败: {0}花生泄漏=[{1}]" -f $detail6, ($peanutLeak -join '、'))
            $fail++
        }

        # ⑦ 库存闭环：新增（任意食材）→ GET 列表 → PATCH 状态推进 active→used
        Write-Info "⑦ 库存闭环（POST / GET / PATCH /v1/inventory）..."
        $ing7 = Invoke-JsonGet -Url ("{0}?limit=1" -f $IngUrl)
        $ingId7 = 0
        if ($ing7.StatusCode -eq 200 -and $ing7.Body -and $ing7.Body.items -and @($ing7.Body.items).Count -gt 0) {
            $ingId7 = [int](@($ing7.Body.items)[0].id)
        }
        $invOk7 = $false
        if ($ingId7 -gt 0) {
            $invBody7 = @{ ingredient_id = $ingId7; quantity_level = 'plenty' } | ConvertTo-Json -Compress
            $invPost7 = Invoke-JsonPost -Url $InvUrl -Body $invBody7 -Headers $h6
            if ($invPost7.StatusCode -eq 201) {
                $invGet7 = Invoke-JsonGet -Url $InvUrl -Headers $h6
                $item7 = $null
                if ($invGet7.StatusCode -eq 200 -and $invGet7.Body -and $invGet7.Body.items) {
                    $item7 = @($invGet7.Body.items) | Where-Object { [int]$_.ingredient_id -eq $ingId7 } | Select-Object -First 1
                }
                if ($item7) {
                    $invPatch7 = Invoke-JsonPatch -Url ("{0}/{1}" -f $InvUrl, $item7.id) `
                        -Body '{"status":"used"}' -Headers $h6
                    if ($invPatch7.StatusCode -eq 200 -and "$($invPatch7.Body.status)" -eq 'used') {
                        $invOk7 = $true
                        Write-Ok ("⑦ 库存闭环: 新增 ingredient_id={0} → GET 命中 → PATCH 状态=used" -f $ingId7)
                    }
                    else {
                        Write-Fail ("⑦ 库存闭环失败: PATCH http={0} status='{1}'（期望 200/used）" -f `
                                $invPatch7.StatusCode, $invPatch7.Body.status)
                    }
                }
                else {
                    Write-Fail "⑦ 库存闭环失败: GET /v1/inventory 未命中新增条目"
                }
            }
            else {
                Write-Fail ("⑦ 库存闭环失败: POST http={0}（期望 201）" -f $invPost7.StatusCode)
            }
        }
        else {
            Write-Fail ("⑦ 库存闭环失败: 食材库查询 http={0} 或无数据（ingredients?limit=1）" -f $ing7.StatusCode)
        }
        if (-not $invOk7) { $fail++ }

        # ⑧ 会员支付闭环：创建订单 → mock-pay → /v1/member/me is_member=true
        Write-Info "⑧ 会员支付（orders → mock-pay → member/me）..."
        $ord8 = Invoke-JsonPost -Url ("{0}/orders" -f $MemUrl) -Body '{"product_type":"monthly"}' -Headers $h6
        $orderNo8 = ''
        if ($ord8.StatusCode -eq 201 -and $ord8.Body) { $orderNo8 = [string]$ord8.Body.order_no }
        $payOk8 = $false
        if ($orderNo8) {
            $pay8 = Invoke-JsonPost -Url ("{0}/orders/{1}/mock-pay" -f $MemUrl, $orderNo8) -Body '{}' -Headers $h6
            $me8  = Invoke-JsonGet -Url ("{0}/me" -f $MemUrl) -Headers $h6
            if ($pay8.StatusCode -eq 200 -and "$($pay8.Body.status)" -eq 'paid' -and `
                $me8.StatusCode -eq 200 -and $me8.Body.is_member) {
                $payOk8 = $true
                Write-Ok ("⑧ 会员支付: 订单 {0} → paid，/v1/member/me is_member=true" -f $orderNo8)
            }
            else {
                Write-Fail ("⑧ 会员支付失败: mock-pay http={0}/status='{1}'，member/me http={2}/is_member={3}" -f `
                        $pay8.StatusCode, $pay8.Body.status, $me8.StatusCode, $me8.Body.is_member)
            }
        }
        else {
            Write-Fail ("⑧ 会员支付失败: 下单 http={0}（期望 201）" -f $ord8.StatusCode)
        }
        if (-not $payOk8) { $fail++ }

        # ⑨ 创新链：precheck(鸡蛋+西红柿) ok=true → generate 201 + status=generated + disclaimer
        Write-Info "⑨ 创新链（innovation/precheck → generate）..."
        $innBody9 = '{"ingredients":["鸡蛋","西红柿"]}'
        $pre9 = Invoke-JsonPost -Url ("{0}/precheck" -f $InnUrl) -Body $innBody9 -Headers $h6 -TimeoutSec 40
        $gen9 = Invoke-JsonPost -Url ("{0}/generate" -f $InnUrl) -Body $innBody9 -Headers $h6 -TimeoutSec 60
        $preOk9 = ($pre9.StatusCode -eq 200 -and $pre9.Body.ok)
        $genOk9 = $false
        if ($gen9.StatusCode -eq 201 -and $gen9.Body.ok -and $gen9.Body.recipe) {
            if ("$($gen9.Body.recipe.status)" -eq 'generated' -and "$($gen9.Body.recipe.disclaimer)") {
                $genOk9 = $true
            }
        }
        if ($preOk9 -and $genOk9) {
            Write-Ok ("⑨ 创新链: precheck ok=true → generate 201 status=generated（「{0}」，disclaimer 非空）" -f `
                    $gen9.Body.recipe.name)
        }
        else {
            Write-Fail ("⑨ 创新链失败: precheck http={0}/ok={1}，generate http={2}/ok={3}/status='{4}'" -f `
                    $pre9.StatusCode, $pre9.Body.ok, $gen9.StatusCode, $gen9.Body.ok, $gen9.Body.recipe.status)
            $fail++
        }

        # ⑩ 首页聚合：GET /v1/home 200 且 entries 字段存在
        Write-Info "⑩ 首页聚合（GET /v1/home）..."
        $home10 = Invoke-JsonGet -Url $HomeUrl -Headers $h6
        if ($home10.StatusCode -eq 200 -and $home10.Body -and $home10.Body.PSObject.Properties['entries']) {
            Write-Ok "⑩ 首页聚合: 200 且 entries 字段存在"
        }
        else {
            Write-Fail ("⑩ 首页聚合失败: http={0} 或缺 entries 字段" -f $home10.StatusCode)
            $fail++
        }

        # ⑪ 后台链路：admin 登录（ADMIN_PASSWORD 缺省 Admin@123456）→ dashboard/cost 200
        Write-Info "⑪ 后台链路（/admin/v1/auth/login → dashboard/cost）..."
        $login11 = Invoke-JsonPost -Url ("{0}/auth/login" -f $AdmUrl) `
            -Body '{"username":"admin","password":"Admin@123456"}'
        $token11 = ''
        if ($login11.StatusCode -eq 200 -and $login11.Body) { $token11 = [string]$login11.Body.access_token }
        $admOk11 = $false
        if ($token11) {
            $cost11 = Invoke-JsonGet -Url ("{0}/dashboard/cost" -f $AdmUrl) `
                -Headers @{ Authorization = "Bearer $token11" }
            if ($cost11.StatusCode -eq 200) {
                $admOk11 = $true
                Write-Ok "⑪ 后台链路: 登录取得 access_token → GET /admin/v1/dashboard/cost 200"
            }
            else {
                Write-Fail ("⑪ 后台链路失败: dashboard/cost http={0}（期望 200）" -f $cost11.StatusCode)
            }
        }
        else {
            Write-Fail ("⑪ 后台链路失败: 登录 http={0}（期望 200；确认已执行 python -m app.seed 生成管理员）" -f `
                    $login11.StatusCode)
        }
        if (-not $admOk11) { $fail++ }

        # ⑫ P95 采样：recommend×5 取 P95 ≤6s；菜谱详情 ≤2s；healthz ≤500ms
        Write-Info "⑫ 性能采样（recommend×5 → P95；菜谱详情；healthz）..."
        $rec12Payload = '{"ingredients":[{"name":"土豆"},{"name":"青椒"}]}'
        $times12 = @()
        for ($i = 0; $i -lt 5; $i++) {
            $sw12 = [System.Diagnostics.Stopwatch]::StartNew()
            $null = Invoke-JsonPost -Url $RecUrl -Body $rec12Payload -TimeoutSec 60
            $sw12.Stop()
            $times12 += $sw12.Elapsed.TotalMilliseconds
        }
        # 最近邻秩法：n=5 时 P95 取第 ceil(0.95*5)=5 个样本（即最大值）
        $sorted12 = @($times12 | Sort-Object)
        $p95Idx12 = [int][math]::Ceiling(0.95 * $sorted12.Count)
        if ($p95Idx12 -lt 1) { $p95Idx12 = 1 }
        $p95Recommend12 = [math]::Round($sorted12[$p95Idx12 - 1], 0)
        # 菜谱详情：优先复用 ⑥ 推荐结果里的 recipe_id，缺省 1
        $detailId12 = 1
        if ($rec6 -and $rec6.Body -and $rec6.Body.PSObject.Properties['results'] -and @($rec6.Body.results).Count -gt 0) {
            $detailId12 = [int](@($rec6.Body.results)[0].recipe_id)
        }
        $swDetail12 = [System.Diagnostics.Stopwatch]::StartNew()
        $detail12 = Invoke-JsonGet -Url ("http://127.0.0.1:{0}/v1/recipes/{1}" -f $bePortEff, $detailId12) -TimeoutSec 10
        $swDetail12.Stop()
        $msDetail12 = [math]::Round($swDetail12.Elapsed.TotalMilliseconds, 0)
        $swHz12 = [System.Diagnostics.Stopwatch]::StartNew()
        $null = Invoke-JsonGet -Url $beHealthEff -TimeoutSec 5
        $swHz12.Stop()
        $msHz12 = [math]::Round($swHz12.Elapsed.TotalMilliseconds, 0)

        $perfOk12 = $true
        if ($p95Recommend12 -le 6000) {
            Write-Ok ("⑫a 推荐 P95: {0} ms ≤ 6000 ms（样本 {1} ms）" -f `
                    $p95Recommend12, (($times12 | ForEach-Object { [math]::Round($_, 0) }) -join '/'))
        }
        else {
            Write-Fail ("⑫a 推荐 P95: {0} ms > 6000 ms（超阈值）" -f $p95Recommend12)
            $perfOk12 = $false
        }
        if ($detail12.StatusCode -eq 200 -and $msDetail12 -le 2000) {
            Write-Ok ("⑫b 菜谱详情 /v1/recipes/{0}: {1} ms ≤ 2000 ms" -f $detailId12, $msDetail12)
        }
        else {
            Write-Fail ("⑫b 菜谱详情: http={0}，{1} ms > 2000 ms（超阈值）" -f $detail12.StatusCode, $msDetail12)
            $perfOk12 = $false
        }
        if ($msHz12 -le 500) {
            Write-Ok ("⑫c healthz: {0} ms ≤ 500 ms" -f $msHz12)
        }
        else {
            Write-Fail ("⑫c healthz: {0} ms > 500 ms（超阈值）" -f $msHz12)
            $perfOk12 = $false
        }
        if (-not $perfOk12) { $fail++ }

        # ⑬ 创新生成降级来源（T7 增补）：generate(土豆+青椒, 90s) → 200/201 且
        #    recipe.basis.generated_by ∈ {"llm","template"}（LLM 成功=llm / 25s 硬超时降级=template，
        #    两种来源均为合法终态，响应结构完整即可）
        Write-Info "⑬ 创新生成降级来源（generate 土豆+青椒，basis.generated_by）..."
        $innBody13 = '{"ingredients":["土豆","青椒"]}'
        $gen13 = Invoke-JsonPost -Url ("{0}/generate" -f $InnUrl) -Body $innBody13 -Headers $h6 -TimeoutSec 90
        $genBy13 = ''
        $ok13 = $false
        if (($gen13.StatusCode -eq 200 -or $gen13.StatusCode -eq 201) -and $gen13.Body -and $gen13.Body.recipe) {
            $recipe13 = $gen13.Body.recipe
            if ($recipe13.PSObject.Properties['basis'] -and $recipe13.basis -and $recipe13.basis.PSObject.Properties['generated_by']) {
                $genBy13 = [string]$recipe13.basis.generated_by
                if ($genBy13 -in @('llm', 'template')) {
                    $ok13 = $true
                }
            }
        }
        if ($ok13) {
            Write-Ok ("⑬ 创新生成: http={0} generated_by='{1}' ∈ {{llm,template}}（is_ai_innovated={2}）" -f `
                    $gen13.StatusCode, $genBy13, $gen13.Body.recipe.is_ai_innovated)
        }
        else {
            Write-Fail ("⑬ 创新生成失败: http={0} generated_by='{1}'（期望 200/201 且 ∈ {{llm,template}}）" -f `
                    $gen13.StatusCode, $genBy13)
            $fail++
        }

        # ⑭ 求助关键词库（T7 增补）：创建会话 → help「盐放多了怎么办」→ blocked=false 且
        #    answers 非空且不含回退前缀「以下是本步要点」（关键词库 _match_help_topic 优先命中，
        #    未命中才回退步骤要点并加前缀——命中样本不得出现前缀）
        Write-Info "⑭ 求助关键词库（创建会话 → help 盐放多了怎么办）..."
        $ok14 = $false
        $detail14 = ''
        # 取一个 published 菜谱（查询接口豁免幂等，page_size=1 取首个）
        $rc14 = Invoke-JsonGet -Url ("http://127.0.0.1:{0}/v1/recipes?page=1&page_size=1" -f $bePortEff) -Headers $h6
        $recipeId14 = 0
        if ($rc14.StatusCode -eq 200 -and $rc14.Body -and $rc14.Body.items -and @($rc14.Body.items).Count -gt 0) {
            $recipeId14 = [int](@($rc14.Body.items)[0].id)
        }
        if ($recipeId14 -gt 0) {
            $csBody14 = @{ recipe_id = $recipeId14; servings = 1 } | ConvertTo-Json -Compress
            $cs14 = Invoke-JsonPost -Url ("http://127.0.0.1:{0}/v1/cooking/sessions" -f $bePortEff) -Body $csBody14 -Headers $h6
            $sessionId14 = 0
            if ($cs14.Body -and $cs14.Body.PSObject.Properties['id']) { $sessionId14 = [int]$cs14.Body.id }
            if ($sessionId14 -gt 0) {
                $helpBody14 = @{ question = '盐放多了怎么办' } | ConvertTo-Json -Compress
                $help14 = Invoke-JsonPost -Url ("http://127.0.0.1:{0}/v1/cooking/sessions/{1}/help" -f $bePortEff, $sessionId14) `
                    -Body $helpBody14 -Headers $h6
                $answers14 = @()
                if ($help14.Body -and $help14.Body.PSObject.Properties['answers']) { $answers14 = @($help14.Body.answers) }
                $fallbackHit14 = @($answers14 | Where-Object { "$_" -match '以下是本步要点' })
                if ($help14.StatusCode -eq 200 -and -not (Get-BlockedFlag -Resp $help14.Body) -and `
                    $answers14.Count -gt 0 -and $fallbackHit14.Count -eq 0) {
                    $ok14 = $true
                    Write-Ok ("⑭ 求助关键词库: 会话 {0} → help 200，answers {1} 条关键词命中且无回退前缀（首条: {2}）" -f `
                            $sessionId14, $answers14.Count, ([string]$answers14[0]).Substring(0, [math]::Min(24, ([string]$answers14[0]).Length)))
                }
                else {
                    $detail14 = "help(http={0}) blocked={1} answers={2} 回退前缀命中={3}" -f `
                        $help14.StatusCode, (Get-BlockedFlag -Resp $help14.Body), $answers14.Count, $fallbackHit14.Count
                }
            }
            else {
                $detail14 = "会话创建失败(http={0})" -f $cs14.StatusCode
            }
        }
        else {
            $detail14 = "菜谱查询失败(http={0})或无 published 菜谱" -f $rc14.StatusCode
        }
        if (-not $ok14) {
            Write-Fail ("⑭ 求助关键词库失败: {0}" -f $detail14)
            $fail++
        }

        # ⑮ 视觉确认与深链直连（T8 增补）：均为接口级断言，不发送真实大图、不产生
        #    VLM 调用费用。a) confirm 混合名单：真实食材计入 added、伪食材列入 skipped；
        #    b) recognize 不带 file 字段（JSON 请求体打到 multipart 端点）→ 422；
        #    c) profile 深链直连 → 200。
        #    （注：/v1/profile 根路径实测 404——profile 路由仅暴露 family/skill/diet-goal
        #    三个子深链，此处按实际可用深链 /v1/profile/skill 断言，与前端档案页
        #    实载接口一致）
        Write-Info "⑮ 视觉确认与深链直连（confirm 混合名单 / recognize 缺 file 422 / profile 深链）..."
        $ok15a = $false
        $ok15b = $false
        $ok15c = $false
        $detail15 = ''
        # a) confirm：番茄/土豆为库内真实食材 → added=2；「不存在的伪食材XX」→ skipped
        $confirm15 = Invoke-JsonPost -Url ("http://127.0.0.1:{0}/v1/vision/confirm" -f $bePortEff) `
            -Body '{"names":["番茄","土豆","不存在的伪食材XX"]}' -Headers $h6
        $skipped15 = @()
        if ($confirm15.Body -and $confirm15.Body.PSObject.Properties['skipped']) { $skipped15 = @($confirm15.Body.skipped) }
        $fakeHit15 = @($skipped15 | Where-Object { "$_" -eq '不存在的伪食材XX' })
        if ($confirm15.StatusCode -eq 200 -and $confirm15.Body -and `
            $confirm15.Body.PSObject.Properties['added'] -and [int]$confirm15.Body.added -eq 2 -and `
            $fakeHit15.Count -eq 1) {
            $ok15a = $true
        }
        else {
            $added15 = if ($confirm15.Body -and $confirm15.Body.PSObject.Properties['added']) { $confirm15.Body.added } else { '?' }
            $detail15 = "confirm(http={0} added={1} skipped=[{2}])" -f $confirm15.StatusCode, $added15, ($skipped15 -join ',')
        }
        # b) recognize 缺 file 字段：POST JSON 空 body 打到 multipart 端点 → 422 校验错误
        $recog15 = Invoke-JsonPost -Url ("http://127.0.0.1:{0}/v1/vision/recognize" -f $bePortEff) -Body '{}'
        if ($recog15.StatusCode -eq 422) {
            $ok15b = $true
        }
        else {
            $detail15 = "{0}; recognize 缺 file http={1}（期望 422）" -f $detail15, $recog15.StatusCode
        }
        # c) profile 深链直连（/v1/profile 根路径 404，实际子深链 /v1/profile/skill）
        $anon15 = 'smoke_deep_' + [Guid]::NewGuid().ToString('N').Substring(0, 8)
        $prof15 = Invoke-JsonGet -Url ("http://127.0.0.1:{0}/v1/profile/skill" -f $bePortEff) `
            -Headers @{ 'X-Anonymous-Id' = $anon15 }
        if ($prof15.StatusCode -eq 200 -and $prof15.Body -and $prof15.Body.PSObject.Properties['cooking_level']) {
            $ok15c = $true
        }
        else {
            $detail15 = "{0}; profile 深链 http={1}" -f $detail15, $prof15.StatusCode
        }
        if ($ok15a -and $ok15b -and $ok15c) {
            Write-Ok "⑮ 视觉确认与深链直连: confirm added=2 且 skipped=[不存在的伪食材XX]；recognize 缺 file=422；/v1/profile/skill=200"
        }
        else {
            Write-Fail ("⑮ 视觉确认与深链直连失败: {0}" -f $detail15)
            $fail++
        }

        # 汇总：任一断言失败退出码 1
        Write-Host "===== 冒烟验证结束 =====" -ForegroundColor Cyan
        if ($fail -gt 0) {
            Write-Fail ("冒烟验证：{0} 组断言未通过" -f $fail)
            exit 1
        }
        Write-Ok "冒烟验证：15 组断言全部通过"
    }

    # ============ docker：docker compose 转调（-DockerCmd up|down|build|logs|ps） ============
    'docker' {
        # 前置检查：docker CLI 与 compose 插件可用性（缺失时给出安装指引而非含糊报错）
        if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
            Write-Fail "未检测到 docker 命令：请先安装并启动 Docker Desktop（https://www.docker.com/products/docker-desktop/）后重试。"
            exit 1
        }
        & docker compose version *> $null
        if ($LASTEXITCODE -ne 0) {
            Write-Fail "docker compose 插件不可用：请升级 Docker Desktop（Compose V2 内置）后重试。"
            exit 1
        }
        $ComposeFile = Join-Path $RootDir 'docker-compose.yml'
        if (-not (Test-Path $ComposeFile)) {
            Write-Fail ("未找到 compose 文件：{0}" -f $ComposeFile)
            exit 1
        }
        switch ($DockerCmd) {
            'build' {
                Write-Info "docker compose build（backend + web 双镜像）..."
                & docker compose -f $ComposeFile build
                if ($LASTEXITCODE -ne 0) { Write-Fail "docker compose build 失败"; exit 1 }
                Write-Ok "镜像构建完成"
            }
            'up' {
                Write-Info "docker compose up -d（db + api + web + redis）..."
                & docker compose -f $ComposeFile up -d
                if ($LASTEXITCODE -ne 0) { Write-Fail "docker compose up 失败"; exit 1 }
                # 等待 API 健康检查就绪（api 内部先跑 alembic 迁移再启动 uvicorn，最长 60 秒）
                Write-Info "等待容器栈 API 就绪（最多 60 秒，http://127.0.0.1:8000/v1/healthz）..."
                $ok = Wait-HttpReady -Url @('http://127.0.0.1:8000/v1/healthz', 'http://127.0.0.1:8000/healthz') `
                    -TimeoutSec 60 -Require200 $true
                if (-not $ok) {
                    Write-Fail "容器栈健康检查超时（60 秒），请执行 docker compose logs api 排查。"
                    exit 1
                }
                Write-Ok "容器栈已就绪"
                Write-Host "==========================================================" -ForegroundColor Cyan
                Write-Host "  用户端   : http://localhost/               （web-stage1）" -ForegroundColor Cyan
                Write-Host "  管理后台 : http://localhost/admin/         （admin，Admin@123456）" -ForegroundColor Cyan
                Write-Host "  后端 API : http://127.0.0.1:8000/v1/healthz" -ForegroundColor Cyan
                Write-Host "  首次启动 : docker compose exec api python -m app.seed  （幂等种子数据）" -ForegroundColor Cyan
                Write-Host "==========================================================" -ForegroundColor Cyan
            }
            'down' {
                Write-Info "docker compose down（保留 pgdata/uploads 数据卷）..."
                & docker compose -f $ComposeFile down
                if ($LASTEXITCODE -ne 0) { Write-Fail "docker compose down 失败"; exit 1 }
                Write-Ok "容器栈已停止"
            }
            'logs' {
                # 输出最近 200 行（不 follow，避免脚本阻塞；需要实时日志请直接 docker compose logs -f）
                & docker compose -f $ComposeFile logs --tail=200
            }
            'ps' {
                & docker compose -f $ComposeFile ps
            }
        }
    }
}
