# Windows counterpart of bootstrap.sh: make sure uv exists, then start the
# Jira server package downloading.
#
# Not wired to a SessionStart hook. A hook naming an interpreter that isn't
# installed fails loudly every single session ("Executable not found in
# $PATH"), and Claude Code has no way to limit a hook to one platform — so a
# `sh` hook breaks Windows machines without Git Bash, and a `powershell` hook
# breaks macOS and Linux. The jira-to-backlog skill runs whichever of these
# two scripts matches the platform instead.
#
# Set JIRA_PLUGIN_NO_BOOTSTRAP=1 to keep it from installing anything.

$ErrorActionPreference = 'Continue'

# This file must stay saved with a UTF-8 BOM: Windows PowerShell 5.1 decodes a
# BOM-less .ps1 with the system ANSI codepage, which turns every Korean
# message below into mojibake. The BOM fixes reading; this fixes writing.
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$OutputEncoding = [Text.Encoding]::UTF8

$UvInstallUrl = 'https://astral.sh/uv/install.ps1'
$ServerPackage = 'mcp-atlassian'

function Test-UvOnPath {
    [bool](Get-Command uv -ErrorAction SilentlyContinue) -and
    [bool](Get-Command uvx -ErrorAction SilentlyContinue)
}

# uv installs here and edits the user PATH, which processes that are already
# running never see. Finding it here means installed-but-invisible.
function Get-UvInstallDir {
    foreach ($dir in @("$env:USERPROFILE\.local\bin", "$env:LOCALAPPDATA\Programs\uv")) {
        if ($dir -and (Test-Path (Join-Path $dir 'uv.exe'))) { return $dir }
    }
    return $null
}

# Detached, output discarded: a child still attached to this process would
# hold up whoever is waiting on it for the whole ~150 MB download.
function Start-ServerPackageDownload($uvxPath) {
    Start-Process -FilePath $uvxPath -ArgumentList @($ServerPackage, '--version') `
        -WindowStyle Hidden | Out-Null
}

if (Test-UvOnPath) {
    exit 0
}

$found = Get-UvInstallDir
if ($found) {
    Write-Output "uv는 설치돼 있지만 이 세션의 PATH에 없습니다 ($found)."
    Write-Output '터미널 앱을 완전히 종료했다가(창 하나만 닫는 게 아니라 앱 전체) 새 터미널에서 Claude Code를 다시 실행하세요.'
    exit 0
}

if ($env:JIRA_PLUGIN_NO_BOOTSTRAP -eq '1') {
    Write-Output 'uv가 없어 Jira 연결을 사용할 수 없습니다. https://docs.astral.sh/uv/ 를 보고 설치하세요.'
    exit 0
}

Write-Output 'Jira 연결에 필요한 uv가 없어 지금 설치합니다 (관리자 권한 불필요)...'
try {
    if ($env:JIRA_PLUGIN_UV_INSTALLER) {
        # Escape hatch for networks that can't reach astral.sh directly.
        Invoke-Expression $env:JIRA_PLUGIN_UV_INSTALLER | Out-Null
    }
    else {
        Invoke-Expression (Invoke-RestMethod $UvInstallUrl) | Out-Null
    }
}
catch {
    Write-Output "uv 설치 중 오류: $($_.Exception.Message)"
}

$installed = Get-UvInstallDir
if (-not $installed) {
    Write-Output 'uv 자동 설치에 실패했습니다. https://docs.astral.sh/uv/ 를 보고 직접 설치한 뒤 Claude Code를 재시작하세요.'
    exit 0
}

Start-ServerPackageDownload (Join-Path $installed 'uvx.exe')
# An earlier session almost certainly failed to start the Jira server (uv was
# missing), and Claude Code keeps such a server down across restarts until it
# is reconnected by hand. Clear that now, with the uv we just installed, so
# the restart below is the only thing the user has to do.
try {
    & (Join-Path $installed 'uv.exe') run --no-project `
        (Join-Path $PSScriptRoot 'mcp_recovery.py') 2>$null
}
catch { }
Write-Output "uv 설치 완료. 이어서 Jira 서버 패키지($ServerPackage, 약 150MB)를 백그라운드로 받는 중입니다."
Write-Output '다운로드가 끝나면 터미널 앱을 완전히 종료했다가(창 하나만 닫는 게 아니라 앱 전체) 새 터미널에서 Claude Code를 다시 실행하세요.'
Write-Output '그 다음부터는 바로 사용할 수 있습니다.'
exit 0
