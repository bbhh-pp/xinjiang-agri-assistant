$ErrorActionPreference = 'Stop'

function Read-HiddenValue([string]$prompt) {
    Write-Host $prompt
    $secureValue = Read-Host -AsSecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureValue)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
}

$appId = Read-HiddenValue '讯飞 TTS APPID（输入内容不会显示）:'
$apiKey = Read-HiddenValue '讯飞 TTS APIKey（输入内容不会显示）:'
$apiSecret = Read-HiddenValue '讯飞 TTS APISecret（输入内容不会显示）:'
$voiceName = Read-Host '维语发音人参数 [默认 x2_ugsp_dilare]'
if ([string]::IsNullOrWhiteSpace($voiceName)) { $voiceName = 'x2_ugsp_dilare' }

$appId = $appId.Trim()
$apiKey = $apiKey.Trim()
$apiSecret = $apiSecret.Trim()
if ($appId -eq '') {
    Write-Error 'APPID、APIKey 和 APISecret 都需要填写，未保存。'
    exit 1
}
if ($apiKey -eq '') {
    Write-Error 'APPID、APIKey 和 APISecret 都需要填写，未保存。'
    exit 1
}
if ($apiSecret -eq '') {
    Write-Error 'APPID、APIKey 和 APISecret 都需要填写，未保存。'
    exit 1
}

[Environment]::SetEnvironmentVariable('XFYUN_TTS_APP_ID', $appId, 'User')
[Environment]::SetEnvironmentVariable('XFYUN_TTS_API_KEY', $apiKey, 'User')
[Environment]::SetEnvironmentVariable('XFYUN_TTS_API_SECRET', $apiSecret, 'User')
[Environment]::SetEnvironmentVariable('XFYUN_TTS_VOICE', $voiceName, 'User')
Write-Host '讯飞语音合成凭据已保存到当前 Windows 用户环境变量。重启网页服务后生效；不会写入网页或项目源代码。'
