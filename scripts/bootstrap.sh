#!/bin/sh
# Make sure uv exists, because everything else this plugin runs needs it.
#
# This is the one piece that cannot be written in Python and launched with
# `uv run`: when uv is missing, a `uv run` hook simply never executes, so the
# plugin stays silent and the user is left to discover the dependency from an
# error somewhere else. So it runs under `sh`, which is present on every
# platform Claude Code supports — Git Bash on Windows included.
#
# Set JIRA_PLUGIN_NO_BOOTSTRAP=1 to keep it from installing anything.

set -u

UV_INSTALL_PS1="https://astral.sh/uv/install.ps1"
UV_INSTALL_SH="https://astral.sh/uv/install.sh"
SERVER_PACKAGE="mcp-atlassian"

# Environment markers first: `uname` lives outside the shell and a hook's
# PATH is not ours to assume.
is_windows() {
    # Windows normalises env var names to upper case, but a shell does not, so
    # check the spellings that actually reach us.
    if [ "${OS:-}" = "Windows_NT" ] || [ -n "${MSYSTEM:-}" ] ||
        [ -n "${WINDIR:-}" ] || [ -n "${windir:-}" ] ||
        [ -n "${SYSTEMROOT:-}" ] || [ -n "${SystemRoot:-}" ]; then
        return 0
    fi
    case "$(uname -s 2>/dev/null)" in
        MINGW* | MSYS* | CYGWIN*) return 0 ;;
        *) return 1 ;;
    esac
}

have_uv() {
    command -v uv >/dev/null 2>&1 && command -v uvx >/dev/null 2>&1
}

# uv installs here and edits PATH, which processes that were already running
# never see. Finding it here means it is installed but invisible to us.
uv_install_dir() {
    for dir in "${HOME:-}/.local/bin" "${USERPROFILE:-}/.local/bin"; do
        if [ -x "$dir/uv" ] || [ -x "$dir/uv.exe" ]; then
            printf '%s' "$dir"
            return 0
        fi
    done
    return 1
}

# Detached, with every descriptor closed: a child still holding this hook's
# stdout would make Claude Code wait for the whole ~150 MB download.
prefetch_server_package() {
    "$1/uvx" "$SERVER_PACKAGE" --version >/dev/null 2>&1 </dev/null &
}

if have_uv; then
    exit 0
fi

if found_dir="$(uv_install_dir)"; then
    echo "uv는 설치돼 있지만 이 세션의 PATH에 없습니다 ($found_dir)."
    echo "터미널 앱을 완전히 종료했다가 새로 열고 Claude Code를 다시 실행하세요."
    exit 0
fi

if [ "${JIRA_PLUGIN_NO_BOOTSTRAP:-}" = "1" ]; then
    echo "uv가 없어 Jira 연결을 사용할 수 없습니다. https://docs.astral.sh/uv/ 를 보고 설치하세요."
    exit 0
fi

echo "Jira 연결에 필요한 uv가 없어 지금 설치합니다 (관리자 권한 불필요)..."
if [ -n "${JIRA_PLUGIN_UV_INSTALLER:-}" ]; then
    # Escape hatch for networks that can't reach astral.sh directly, e.g. an
    # internal mirror behind a proxy.
    sh -c "$JIRA_PLUGIN_UV_INSTALLER" >/dev/null 2>&1
elif is_windows; then
    powershell -NoProfile -ExecutionPolicy Bypass \
        -Command "irm $UV_INSTALL_PS1 | iex" >/dev/null 2>&1
elif command -v curl >/dev/null 2>&1; then
    curl -LsSf "$UV_INSTALL_SH" | sh >/dev/null 2>&1
elif command -v wget >/dev/null 2>&1; then
    wget -qO- "$UV_INSTALL_SH" | sh >/dev/null 2>&1
else
    echo "uv 설치 실패: curl 도 wget 도 없습니다. https://docs.astral.sh/uv/ 를 보고 직접 설치하세요."
    exit 0
fi

if ! installed_dir="$(uv_install_dir)"; then
    echo "uv 자동 설치에 실패했습니다. https://docs.astral.sh/uv/ 를 보고 직접 설치한 뒤 Claude Code를 재시작하세요."
    exit 0
fi

prefetch_server_package "$installed_dir"
echo "uv 설치 완료. 이어서 Jira 서버 패키지($SERVER_PACKAGE, 약 150MB)를 백그라운드로 받는 중입니다."
echo "다운로드가 끝나면 Claude Code를 완전히 종료했다가 다시 실행하세요. 그 다음부터는 바로 사용할 수 있습니다."
exit 0
