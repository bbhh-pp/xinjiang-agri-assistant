$ErrorActionPreference = 'Stop'
# Keep this bootstrap script ASCII-only for Windows PowerShell 5.1.
Write-Host 'Paste the real glossary IDs returned by Tencent. Leave blank to disable one direction.'
$ugZhId = (Read-Host 'Uyghur to Chinese (ug -> zh) GlossaryId').Trim()
$zhUgId = (Read-Host 'Chinese to Uyghur (zh -> ug) GlossaryId').Trim()
[Environment]::SetEnvironmentVariable('TENCENT_GLOSSARY_UG_ZH_ID', $ugZhId, 'User')
[Environment]::SetEnvironmentVariable('TENCENT_GLOSSARY_ZH_UG_ID', $zhUgId, 'User')
Write-Host 'Glossary IDs were saved. Close the old server and run start.cmd again.'
