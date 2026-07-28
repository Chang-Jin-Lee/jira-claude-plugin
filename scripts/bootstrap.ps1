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
    Write-Output '[jira-claude-plugin] uv는 이미 설치돼 있지만 지금 실행 중인 터미널이 그걸 못 보고 있습니다.'
    Write-Output "  설치 위치: $found"
    Write-Output '  원인: uv 설치 프로그램이 PATH를 바꿔도, 이미 떠 있던 프로그램은 그 변경을 못 봅니다.'
    Write-Output '  → 터미널 앱을 완전히 종료하세요. 창 하나만 닫는 게 아니라 앱 전체입니다.'
    Write-Output '     그 다음 새 터미널에서 Claude Code를 다시 실행하면 됩니다. 재설치는 필요 없습니다.'
    exit 0
}

if ($env:JIRA_PLUGIN_NO_BOOTSTRAP -eq '1') {
    Write-Output '[jira-claude-plugin] uv가 없어 Jira 연결을 쓸 수 없습니다. (JIRA_PLUGIN_NO_BOOTSTRAP=1 이라 자동 설치는 건너뜁니다.)'
    Write-Output '  → https://docs.astral.sh/uv/ 를 보고 직접 설치한 뒤, 터미널 앱을 완전히 종료했다가 새로 열어 주세요.'
    exit 0
}

Write-Output '[jira-claude-plugin] Jira 연결에 필요한 uv가 없어 지금 설치합니다. 관리자 권한은 필요 없습니다...'
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
    Write-Output '[jira-claude-plugin] uv 자동 설치에 실패했습니다. 네트워크나 보안 정책 때문일 수 있습니다.'
    Write-Output '  → https://docs.astral.sh/uv/ 를 보고 직접 설치한 뒤, 터미널 앱을 완전히 종료했다가 새로 열어 주세요.'
    Write-Output '     사내 미러를 쓰신다면 JIRA_PLUGIN_UV_INSTALLER 환경변수로 설치 명령을 지정할 수 있습니다.'
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
Write-Output "[jira-claude-plugin] uv 설치 완료. 이어서 Jira 서버 패키지($ServerPackage, 약 150MB)를 백그라운드로 받는 중입니다."
Write-Output '  → 남은 건 재시작 한 번뿐입니다. 터미널 앱을 완전히 종료하세요. 창 하나만 닫는 게 아니라 앱 전체입니다.'
Write-Output '     그 다음 새 터미널에서 Claude Code를 실행하면 Jira가 바로 붙습니다.'
Write-Output '     (다운로드가 아직 끝나지 않았다면 Jira 도구가 안 보일 수 있습니다. 그때는 /mcp 에서 atlassian 만 재연결하세요.)'
exit 0
