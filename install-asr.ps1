param([switch]$CpuOnly)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
$bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'

if (-not (Test-Path -LiteralPath $venvPython)) {
    if (Test-Path -LiteralPath $bundledPython) {
        $basePython = $bundledPython
    } else {
        $pythonCommand = Get-Command py,python -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $pythonCommand) { throw 'Python 3.10 or newer is required.' }
        $basePython = $pythonCommand.Source
    }
    & $basePython -m venv (Join-Path $projectRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Failed to create the Python environment.' }
}

if (-not $CpuOnly -and (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) {
    & $venvPython -m pip install 'torch==2.6.0' --index-url 'https://download.pytorch.org/whl/cu126' --timeout 120 --retries 5
    if ($LASTEXITCODE -ne 0) {
        Write-Warning 'CUDA PyTorch download failed. Falling back to CPU inference; retry later for GPU training.'
        $CpuOnly = $true
    }
}
if ($CpuOnly) {
    & $venvPython -m pip install 'torch==2.6.0' --index-url 'https://download.pytorch.org/whl/cpu' --timeout 120 --retries 5
    if ($LASTEXITCODE -ne 0) { throw 'Failed to install CPU PyTorch.' }
}
& $venvPython -m pip install -r (Join-Path $projectRoot 'requirements-asr.txt')
if ($LASTEXITCODE -ne 0) { throw 'Failed to install ASR dependencies.' }
& $venvPython (Join-Path $projectRoot 'download_asr_model.py')
if ($LASTEXITCODE -ne 0) { throw 'Failed to download the ASR model.' }
Write-Host 'Installed. Run .\start.cmd or .\start.ps1 to open the website.'
