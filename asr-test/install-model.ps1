$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $root '..\.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw 'Project .venv not found. Set up the main project first.' }
& $python -m pip install --timeout 120 --retries 5 'onnxruntime>=1.18,<2' 'imageio-ffmpeg>=0.5,<1'
if ($LASTEXITCODE -ne 0) { throw 'onnxruntime install failed.' }
$modelDir = Join-Path $root 'model'
New-Item -ItemType Directory -Force -Path $modelDir | Out-Null
$modelPath = Join-Path $modelDir 'uyghur_asr.onnx'
if ((Test-Path $modelPath) -and (Get-Item $modelPath).Length -gt 200000000) {
  Write-Host 'Model file already exists.'
  exit 0
}
$url = 'https://github.com/gheyret/uyghurasr_python/releases/download/tunji/uyghur_asr.onnx'
$tempPath = Join-Path $modelDir 'uyghur_asr.onnx.download'
try {
  Invoke-WebRequest -Uri $url -OutFile $tempPath -TimeoutSec 600
  if ((Get-Item $tempPath).Length -lt 200000000) { throw 'Model download incomplete.' }
  Move-Item -LiteralPath $tempPath -Destination $modelPath -Force
  Write-Host 'Model installed.'
} finally {
  if (Test-Path $tempPath) { Remove-Item -LiteralPath $tempPath -Force }
}
