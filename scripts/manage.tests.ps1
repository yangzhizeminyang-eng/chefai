Import-Module Pester -MinimumVersion 3.4.0

$repoRoot = Split-Path -Parent $PSScriptRoot
$manageScript = Join-Path $PSScriptRoot 'manage.ps1'
$startScript = Join-Path $PSScriptRoot 'start.bat'

Describe 'AI Cook startup scripts' {
    It 'recognizes services that are listening on their configured ports' {
        $netstat = @(netstat -ano -p tcp | Select-String -Pattern 'LISTENING\s+\d+$')
        $backendLine = $netstat | Where-Object { $_.ToString() -match ':(8000)\s+\S+\s+LISTENING\s+\d+$' }

        if (-not $backendLine) {
            throw 'This integration test requires the backend on port 8000.'
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
