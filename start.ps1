$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'

if (Test-Path -LiteralPath $venvPython) {
    $pythonExecutable = $venvPython
} elseif (Test-Path -LiteralPath $bundledPython) {
    $pythonExecutable = $bundledPython
} else {
    $pythonCommand = Get-Command py,python -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $pythonCommand) {
        Write-Error 'Python 3.10 or newer is required.'
        exit 1
    }
    $pythonExecutable = $pythonCommand.Source
}

$savedShennongKey = [Environment]::GetEnvironmentVariable('SHENNONG_API_KEY', 'User')
if (-not [string]::IsNullOrWhiteSpace($savedShennongKey)) {
    $env:SHENNONG_API_KEY = $savedShennongKey
}

foreach ($variableName in @(
    'XFYUN_TTS_APP_ID', 'XFYUN_TTS_API_KEY', 'XFYUN_TTS_API_SECRET', 'XFYUN_TTS_VOICE',
    'TENCENT_TOKENHUB_API_KEY', 'TENCENT_HYMT_API_URL', 'TENCENT_HYMT_MODEL',
    'TENCENT_GLOSSARY_UG_ZH_ID', 'TENCENT_GLOSSARY_ZH_UG_ID'
)) {
    $savedValue = [Environment]::GetEnvironmentVariable($variableName, 'User')
    if (-not [string]::IsNullOrWhiteSpace($savedValue)) {
        [Environment]::SetEnvironmentVariable($variableName, $savedValue, 'Process')
    }
}

if ([string]::IsNullOrWhiteSpace($env:SHENNONG_API_KEY)) {
    Write-Host '未配置神农 API 密钥，网页仍可直接打开；问答功能需要稍后配置密钥。'
}

# This project is back in local demo mode. Keep it reachable only from this PC.
$env:SHENNONG_PORT = '8767'
$env:SHENNONG_BIND_HOST = '127.0.0.1'
Remove-Item Env:SHENNONG_PUBLIC_ORIGIN -ErrorAction SilentlyContinue
Remove-Item Env:PORT -ErrorAction SilentlyContinue

# CIM process inspection is unavailable on some Windows installations. The
# port check below is sufficient to avoid starting a duplicate local server.
$occupied = @(Get-NetTCPConnection -LocalPort 8767 -State Listen -ErrorAction SilentlyContinue)
if ($occupied.Count -gt 0) {
    Write-Error '8767 端口仍被其他程序占用。请关闭该程序后再运行 start.cmd。'
    exit 1
}
Set-Location -LiteralPath $projectRoot
& $pythonExecutable (Join-Path $projectRoot 'server.py')
