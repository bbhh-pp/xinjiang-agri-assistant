$ErrorActionPreference = 'Stop'

Write-Host 'Enter your Shennong API key. Input will be hidden:'
$secureKey = Read-Host -AsSecureString
$keyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
try {
    $apiKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPointer)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPointer)
}

if ([string]::IsNullOrWhiteSpace($apiKey)) {
    Write-Error 'No API key was entered. Nothing was saved.'
    exit 1
}

[Environment]::SetEnvironmentVariable('SHENNONG_API_KEY', $apiKey, 'User')
Write-Host 'Saved for this Windows user. Start the site with start.cmd.'
