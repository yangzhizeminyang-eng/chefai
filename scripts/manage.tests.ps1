Import-Module Pester -MinimumVersion 3.4.0

$repoRoot = Split-Path -Parent $PSScriptRoot
$manageScript = Join-Path $PSScriptRoot 'manage.ps1'
$startScript = Join-Path $PSScriptRoot 'start.bat'

function Invoke-ManageMenuInput {
    param(
        [string]$InputText,
        [string]$Arguments = ''
    )

    $hostProcess = Get-Process -Id $PID
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $hostProcess.Path
    $startInfo.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$manageScript`" $Arguments"
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardInput = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $process = [System.Diagnostics.Process]::Start($startInfo)
    try {
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        $process.StandardInput.WriteLine($InputText)
        $process.StandardInput.Close()
        if (-not $process.WaitForExit(45000)) {
            $process.Kill()
            throw 'manage.ps1 did not exit after receiving menu input.'
        }
        return @{
            ExitCode = $process.ExitCode
            Output = $stdoutTask.GetAwaiter().GetResult() + $stderrTask.GetAwaiter().GetResult()
        }
    }
    finally {
        $process.Dispose()
    }
}

Describe 'AI Cook startup scripts' {
    It 'opens an interactive menu by default and exits on choice 4' {
        $result = Invoke-ManageMenuInput -InputText '4'

        $result.ExitCode | Should Be 0
        $result.Output | Should Match 'AI Cook.*服务管理'
        $result.Output | Should Match '4.*退出'
    }

    It 'dispatches the status choice to the existing status action' {
        $result = Invoke-ManageMenuInput -InputText "3`n4"

        $result.ExitCode | Should Be 0
        $result.Output | Should Match '运行状态'
        $result.Output | Should Match '4.*退出'
    }

    It 'rejects an invalid menu choice and keeps the menu available' {
        $result = Invoke-ManageMenuInput -InputText "x`n4"

        $result.ExitCode | Should Be 0
        $result.Output | Should Match '无效选择'
        $result.Output | Should Match '4.*退出'
    }

    It 'recognizes services that are listening on their configured ports' {
        $netstat = @(netstat -ano -p tcp | Select-String -Pattern 'LISTENING\s+\d+$')
        $backendLine = $netstat | Where-Object { $_.ToString() -match ':(8000)\s+\S+\s+LISTENING\s+\d+$' }

        if (-not $backendLine) {
            Set-TestInconclusive 'This integration test requires the backend on port 8000.'
        }

        . $manageScript -Action status | Out-Null
        Get-ListenPid -Port 8000 | Should Not Be $null

        if (Test-PortOpen -TargetHost 'localhost' -Port 5173 -TimeoutMs 1000) {
            Get-ListenPid -Port 5173 | Should Not Be $null
        }
    }

    It 'keeps a one-click startup window open when startup fails' {
        Test-Path $startScript | Should Be $true

        $content = Get-Content -Raw $startScript
        $content | Should Match '(?i)(errorlevel|EXIT_CODE)'
        $content | Should Match '(?i)\bpause\b'
    }

    It 'does not treat a proxy response as local service readiness' {
        . $manageScript -Action status | Out-Null
        $content = Get-Content -Raw $manageScript
        $content | Should Match '(?i)\$req\.Proxy\s*=\s*\[System\.Net\.GlobalProxySelection\]::GetEmptyWebProxy\(\)'
    }

    It 'keeps the original startup failure when process cleanup is denied' {
        $content = Get-Content -Raw $manageScript
        $content | Should Match '(?s)taskkill\.exe.*?try\s*\{'
    }

    It 'uses the native Vite config loader on Windows' {
        $content = Get-Content -Raw $manageScript
        $content | Should Match '(?i)--configLoader native'
    }

    It 'reuses a healthy backend instead of reporting a port conflict' {
        $content = Get-Content -Raw $manageScript
        $content | Should Match '(?s)\$bePid\s*=\s*Get-ListenPid.*?\$beCode\s*=\s*Get-HttpStatusCode.*?复用'
    }

    It 'reuses a healthy frontend instead of reporting a port conflict' {
        $content = Get-Content -Raw $manageScript
        $content | Should Match '(?s)\$fePid\s*=\s*Get-ListenPid.*?\$feCode\s*=\s*Get-FrontendHttpCode.*?复用'
    }

    It 'identifies project-owned listeners by process command line, not by vite endpoint probing' {
        $content = Get-Content -Raw $manageScript
        $content | Should Match '(?s)function\s+Test-ProjectProcess\b'
        # 其他项目的 Vite dev server 同样响应 /@vite/client，特征端点探测会误复用，必须淘汰
        $content | Should Not Match 'function\s+Test-ViteAlive\b'
        $content | Should Match '(?s)Test-ProjectProcess\s+-Port\s+\$FePort\s+-ProjectDir\s+\$WebDir'
        $content | Should Match '(?s)Test-ProjectProcess\s+-Port\s+\$AdmPort\s+-ProjectDir\s+\$AdminDir'
    }

    It 'verifies the injected backend port before reusing a frontend and restarts it when stale' {
        $content = Get-Content -Raw $manageScript
        $content | Should Match '(?s)function\s+Test-ProxyStale\b'
        $content | Should Match 'frontend\.bkport'
        $content | Should Match 'admin\.bkport'
        $content | Should Match '(?s)function\s+Remove-StaleVite\b'
    }
}

# =====================================================================
# Test-ProjectProcess 多重证据归属判定（TDD 回归新增）
# 背景：本项目 venv 的 uvicorn 经 PATH 解析启动时（python.exe 走 PATH），监听进程
#       命令行为 `python -m uvicorn app.main:app --port <N>`，不含仓库路径；旧的
#       「命令行含项目目录」单一判据会误判为其他程序占用（healthz 200 也不复用），
#       导致重复启动与端口漂移。修复后判定改为多重证据（PID 文件 / venv 可执行
#       路径含父链 / 命令行），任一命中即归属本项目。
# logs 注入性说明：manage.ps1 的 $LogsDir 为脚本内硬编码变量（无参数可注入），
#       start/stop 全流程不真跑；按 spec 降级为判定函数层行为测试 + start/stop
#       分支代码审读断言。本测试将脚本作用域 $LogsDir 重定向至独立临时目录，
#       隔离真实 logs\backend.pid 等记录，AfterAll 还原。
# 进程纪律：8291/8292 的监听进程均为本轮自启（AfterAll 终止并复核端口释放）；
#       绝不终止外部进程；隔离端口被外部占用时本轮测试直接中止（throw）。
# =====================================================================

# 顶层加载 manage.ps1 函数（dot-source 到脚本作用域；-Action status 仅打印状态，无副作用）
. $manageScript -Action status *>&1 | Out-Null

Describe 'Test-ProjectProcess multi-evidence ownership' {
    # ---- 隔离环境与端口常量（Describe 体执行一次，进程于 AfterAll 统一清理）----
    # 注意：Pester 3.4 的 AfterAll 看不到 Describe 体局部变量，需在 AfterAll 中清理的
    # 状态一律以 $script: 作用域存放（其 It 内可经作用域链正常读取）。
    $script:ownPort     = 8291   # 本轮自启：本项目 venv uvicorn（PATH 方式启动，命令行不含仓库路径）
    $script:foreignPort = 8292   # 本轮自启：非本项目 python http.server（系统解释器 + 系统临时目录）
    $freePort    = 8299   # 全程无监听的空闲端口（无监听分支用例）

    $beDir = Join-Path $repoRoot 'backend'
    $venvScripts = Join-Path $beDir '.venv\Scripts'
    if (-not (Test-Path (Join-Path $venvScripts 'python.exe'))) {
        throw 'backend\.venv\Scripts\python.exe 不存在，请先执行 setup'
    }

    # logs 目录重定向（隔离真实记录；AfterAll 还原）
    $script:origLogsDir = $LogsDir
    $script:isolatedLogs = Join-Path ([System.IO.Path]::GetTempPath()) ('aicook-manage-tests-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $script:isolatedLogs -Force | Out-Null
    $script:LogsDir = $script:isolatedLogs

    # 离线运行环境变量（由本轮自启的子进程继承；进程环境变量优先级高于 backend\.env）
    $env:EMBEDDING_PROVIDER = 'hash'
    $env:EMBEDDING_WARMUP = 'off'
    $env:LLM_BASE_URL = 'http://127.0.0.1:9'
    $env:LLM_API_KEY = 'offline'
    $env:VISION_PROVIDER = 'mock'
    $env:SPEECH_PROVIDER = 'mock'
    $env:TTS_PROVIDER = 'mock'
    $env:PAYMENT_PROVIDER = 'mock'

    # 前置校验：隔离端口必须空闲，否则中止本轮测试（避免误伤/误判外部进程）
    foreach ($probePort in @($ownPort, $foreignPort, $freePort)) {
        if (Get-ListenPid -Port $probePort) {
            throw ("隔离端口 {0} 已被外部进程监听，为避免终止外部进程，本轮测试中止" -f $probePort)
        }
    }

    # 本轮自启①：本项目 venv uvicorn。在 cmd 中把 venv\Scripts 前置到 PATH 后以
    # `python -m uvicorn` 启动，复刻真实场景：命令行只有 `python -m uvicorn app.main:app ...`
    # （argv[0] 为 PATH 解析的 python，不含仓库路径），而 Win32_Process.ExecutablePath
    # 仍解析为 venv python（新判据②的命中场景）。
    $ownCmd = 'set "PATH={0};%PATH%" && python -m uvicorn app.main:app --host 127.0.0.1 --port {1}' -f $venvScripts, $ownPort
    $script:ownHost = Start-Process -FilePath 'cmd.exe' -ArgumentList '/d', '/s', '/c', $ownCmd -WorkingDirectory $beDir -WindowStyle Hidden -PassThru

    # 本轮自启②：非本项目 python 监听进程（PATH 系统解释器，cwd=系统临时目录）
    $foreignExe = Get-Command python -ErrorAction SilentlyContinue
    if ($foreignExe) { $foreignExe = $foreignExe.Source } else { $foreignExe = (Get-Command py -ErrorAction Stop).Source }
    if ($foreignExe -ieq (Join-Path $venvScripts 'python.exe')) {
        throw ("PATH 解析到的 python 属于本项目 venv（{0}），非本项目对照进程构造不成立" -f $foreignExe)
    }
    $script:foreignProc = Start-Process -FilePath $foreignExe -ArgumentList '-m', 'http.server', "$foreignPort" -WorkingDirectory $env:TEMP -WindowStyle Hidden -PassThru

    # 等待指定端口出现监听（本轮自启进程就绪用；超时返回 $null）
    # 参数 $Port - 目标端口；$TimeoutSec - 最长等待秒数
    # 返回值：监听进程 PID；超时未监听返回 $null
    function Wait-TestListener {
        param([int]$Port, [int]$TimeoutSec = 90)
        $deadline = (Get-Date).AddSeconds($TimeoutSec)
        while ((Get-Date) -lt $deadline) {
            $hit = Get-ListenPid -Port $Port
            if ($hit) { return $hit }
            Start-Sleep -Milliseconds 500
        }
        return $null
    }

    $script:ownListenPid = Wait-TestListener -Port $ownPort -TimeoutSec 120
    if (-not $ownListenPid) { throw ("本轮自启的 uvicorn 未在端口 {0} 进入监听（启动或导入失败）" -f $ownPort) }
    $script:foreignListenPid = Wait-TestListener -Port $foreignPort -TimeoutSec 30
    if (-not $foreignListenPid) { throw ("本轮自启的对照 http.server 未在端口 {0} 监听" -f $foreignPort) }

    It 'treats a PATH-launched venv uvicorn as ours even though its command line lacks the repo path' {
        # 测试①：命令行不含仓库路径的本项目 venv uvicorn → 判定 $true
        # （修复前仅凭命令行判据返回 $false → Red）
        $result = Test-ProjectProcess -Port $ownPort -ProjectDir $repoRoot
        $result | Should Be $true
    }

    It 'matches the recorded pid file evidence for our own listener' {
        # 证据①：监听 PID == logs\backend.pid 记录值 → $true（隔离 logs 写入后即时清理）
        $pidFile = Join-Path $isolatedLogs 'backend.pid'
        Set-Content -Path $pidFile -Value $ownListenPid -Encoding ascii
        try {
            Test-ProjectProcess -Port $ownPort -ProjectDir $BackendDir | Should Be $true
        }
        finally {
            Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
        }
    }

    It 'would reuse instead of relaunching when the start branch criteria hold (health mocked to 200)' {
        # 测试②（复用语义·判定层）：复刻 start 分支判定表达式
        #   $beOurs = Test-ProjectProcess ...；复用条件 $beCode -eq 200 -and $beOurs -ne $false
        # healthz=200 用 Mock 固定（与真实 DB 状态解耦），复现「healthz 200 也不认」场景：
        # 旧实现 $beOurs=$false → 条件不成立 → 误判漂移重启；新实现 $beOurs=$true → 复用不新启。
        Mock Get-HttpStatusCode { return 200 }
        $beOurs = Test-ProjectProcess -Port $ownPort -ProjectDir $BackendDir
        $beCode = Get-HttpStatusCode -Url ('http://127.0.0.1:{0}/v1/healthz' -f $ownPort) -TimeoutSec 3
        ($beCode -eq 200 -and $beOurs -ne $false) | Should Be $true
    }

    It 'gates the start reuse branches on Test-ProjectProcess (code-read assertion)' {
        # 测试②（代码审读层）：start 的后端复用分支必须以 Test-ProjectProcess 判定为门
        # （logs 路径为脚本硬编码变量不可注入，start 全流程不真跑，按 spec 以代码审读兜底）
        $content = Get-Content -Raw $manageScript
        # 漂移端口复用分支：Test-ProjectProcess → health 200 → 复用现有服务（不新启进程）
        $content | Should Match '(?s)\$beOurs\s*=\s*Test-ProjectProcess\s+-Port\s+\$beRecPort\s+-ProjectDir\s+\$BackendDir\s*\r?\n\s*if\s*\(\s*\$beCode\s*-eq\s*200\s+-and\s+\$beOurs\s*-ne\s+\$false\)\s*\{.*?复用现有服务'
        # 默认端口复用分支同样以 Test-ProjectProcess 判定为复用前提
        $content | Should Match '(?s)\$beOurs\s*=\s*Test-ProjectProcess\s+-Port\s+\$BePort\s+-ProjectDir\s+\$BackendDir\s*\r?\n\s*if\s*\(\s*\$beCode\s*-eq\s*200\s+-and\s+\$beOurs\s*-ne\s+\$false\)'
    }

    It 'returns false conservatively for a foreign listener even with a stale pid file (no throw)' {
        # 测试③a：PID 文件过期（指向早已退出的进程）时不得凭 PID 文件误判 $true；返回 $false 不抛错
        $pidFile = Join-Path $isolatedLogs 'backend.pid'
        Set-Content -Path $pidFile -Value '99999999' -Encoding ascii
        try {
            $result = Test-ProjectProcess -Port $foreignPort -ProjectDir $repoRoot
            $result | Should Be $false
        }
        finally {
            Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
        }
    }

    It 'returns false for a foreign listener when the pid file is missing, invalid, or no listener exists' {
        # 测试③b：PID 文件缺失（隔离 logs 为空）+ 非本项目监听 → $false
        Test-ProjectProcess -Port $foreignPort -ProjectDir $repoRoot | Should Be $false
        # 测试③c：PID 文件内容无效（非数字）→ 不抛错，仍 $false
        Set-Content -Path (Join-Path $isolatedLogs 'backend.pid') -Value 'not-a-pid' -Encoding ascii
        try {
            Test-ProjectProcess -Port $foreignPort -ProjectDir $repoRoot | Should Be $false
        }
        finally {
            Remove-Item (Join-Path $isolatedLogs 'backend.pid') -Force -ErrorAction SilentlyContinue
        }
        # 测试③d：目标端口无监听 → $false（保守，不抛错）
        Test-ProjectProcess -Port $freePort -ProjectDir $repoRoot | Should Be $false
    }

    It 'returns null conservatively when process info is unavailable (simulated CIM outage)' {
        # 测试③e：进程树信息不可用（模拟 CIM 故障）→ $null（保守：不误判、不抛错）
        Remove-Item (Join-Path $isolatedLogs '*.pid') -Force -ErrorAction SilentlyContinue
        # 用 It 作用域内定义的同名函数遮蔽真实查询（It 结束即随作用域还原，避免
        # Pester 3.4 的 It 内 Mock 泄漏到后续用例的问题），模拟 CIM 不可用
        function Get-ProcessCommandLine { param([int]$ProcessId) return $null }
        function Get-ProcessExecutablePath { param([int]$ProcessId) return $null }
        $result = Test-ProjectProcess -Port $ownPort -ProjectDir $repoRoot
        ($null -eq $result) | Should Be $true
    }

    It 'does not misjudge a foreign python listener as ours (anti-false-kill guard)' {
        # 测试④（防误杀·判定层）：非本项目 python 监听进程（系统解释器 + 临时目录 cwd）→ $false
        Test-ProjectProcess -Port $foreignPort -ProjectDir $repoRoot | Should Be $false
    }

    It 'makes stop fallback port termination ownership-verified, never a blind kill (code-read assertion)' {
        # 测试④（防误杀·代码审读层）：stop 的按端口兜底必须先经 Test-ProjectProcess
        # 归属验证（fail-closed，仅判定 $true 才 taskkill），且三个调用点分别传入对应目录
        $content = Get-Content -Raw $manageScript
        # Stop-Target 兜底循环：归属验证 → 非 $true 跳过 → 验证通过才按监听 PID 终止
        $content | Should Match '(?s)function\s+Stop-Target\b.*?\$ours\s*=\s*Test-ProjectProcess\s+-Port\s+\$port\s+-ProjectDir\s+\$ProjectDir.*?if\s*\(\s*\$ours\s*-ne\s+\$true\s*\).*?taskkill\.exe\s+/PID\s+\$listenPid'
        # 三个调用点分别传入 backend/web/admin 目录（防按端口盲杀的入口闭环；
        # 模式一律单引号避免 $ 变量被插值，pid 文件名两侧引号用 . 通配）
        $content | Should Match '\(Join-Path\s+\$LogsDir\s+.backend\.pid.\)\s+-Ports\s+\$beStopPorts\s+-ProjectDir\s+\$BackendDir'
        $content | Should Match '\(Join-Path\s+\$LogsDir\s+.frontend\.pid.\)\s+-Ports\s+\$feStopPorts\s+-ProjectDir\s+\$WebDir'
        $content | Should Match '\(Join-Path\s+\$LogsDir\s+.admin\.pid.\)\s+-Ports\s+\$admStopPorts\s+-ProjectDir\s+\$AdminDir'
    }

    AfterAll {
        # 进程纪律：仅终止本轮自启进程（记录的宿主 PID + 监听 PID 双保险），随后复核端口释放
        # （Pester 3.4 的 AfterAll 作用域看不到 Describe 体局部变量，一律读 $script: 作用域）
        foreach ($rootPid in @($script:ownHost.Id, $script:foreignProc.Id)) {
            if ($rootPid) {
                try { & taskkill.exe /PID $rootPid /T /F 2>&1 | Out-Null } catch { }
            }
        }
        foreach ($listenPidLeft in @($script:ownListenPid, $script:foreignListenPid)) {
            if ($listenPidLeft -and (Get-Process -Id $listenPidLeft -ErrorAction SilentlyContinue)) {
                try { & taskkill.exe /PID $listenPidLeft /T /F 2>&1 | Out-Null } catch { }
            }
        }
        # 复核端口释放（最长等 15 秒）
        $waitedMs = 0
        while ($waitedMs -lt 15000) {
            $left = @() + @(Get-ListenPid -Port $script:ownPort) + @(Get-ListenPid -Port $script:foreignPort)
            if ($left.Count -eq 0) { break }
            Start-Sleep -Milliseconds 500
            $waitedMs += 500
        }
        $stillOpen = @()
        foreach ($p in @($script:ownPort, $script:foreignPort)) {
            if (Get-ListenPid -Port $p) { $stillOpen += $p }
        }
        if ($stillOpen.Count -gt 0) {
            Write-Host ("[WARN] 本轮测试端口未完全释放: {0}（请人工检查，切勿盲目杀进程）" -f ($stillOpen -join '/')) -ForegroundColor Yellow
        }
        # 还原 logs 目录注入并清理临时隔离目录
        $script:LogsDir = $script:origLogsDir
        Remove-Item $script:isolatedLogs -Recurse -Force -ErrorAction SilentlyContinue
    }
}
