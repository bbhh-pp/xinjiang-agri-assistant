$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$url = 'http://127.0.0.1:8767/'

function Test-SiteReady {
    try {
        $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

if (-not (Test-SiteReady)) {
    $occupied = @(Get-NetTCPConnection -LocalPort 8767 -State Listen -ErrorAction SilentlyContinue)
    if ($occupied.Count -gt 0) {
        throw '8767 端口已被其他程序占用，无法启动网站。'
    }

    $launcher = Join-Path $projectRoot 'start.ps1'
    $serverProcess = Start-Process -FilePath 'powershell.exe' `
        -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + $launcher + '"')) `
        -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru

    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        Start-Sleep -Milliseconds 500
        if (Test-SiteReady) { break }
        if ($serverProcess.HasExited) {
            throw "网站启动失败，退出码：$($serverProcess.ExitCode)。"
        }
    }
    if (-not (Test-SiteReady)) {
        throw '网站启动超时，请检查 Python 和依赖是否安装完整。'
    }
}

Start-Process $url
Write-Host "网站已打开：$url"
