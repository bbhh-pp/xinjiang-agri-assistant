$ErrorActionPreference = 'Stop'

# Keep this bootstrap script ASCII-only so Windows PowerShell 5.1 can parse it
# correctly even when the file is stored as UTF-8 without a BOM.
Write-Host 'Enter your Tencent TokenHub API Key (input is hidden):'
$secureKey = Read-Host -AsSecureString
$pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
try {
    $apiKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer).Trim()
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
}
if ([string]::IsNullOrWhiteSpace($apiKey)) {
    Write-Error 'No API Key was entered. Nothing was saved.'
    exit 1
}

[Environment]::SetEnvironmentVariable('TENCENT_TOKENHUB_API_KEY', $apiKey, 'User')
[Environment]::SetEnvironmentVariable('TENCENT_HYMT_API_URL', 'https://tokenhub.tencentmaas.com/v1/api/translations', 'User')
[Environment]::SetEnvironmentVariable('TENCENT_HYMT_MODEL', 'hy-mt2-plus', 'User')
Write-Host 'Tencent TokenHub settings were saved in Windows user environment variables.'
Write-Host 'Close the old web server window, then run start.cmd again.'
