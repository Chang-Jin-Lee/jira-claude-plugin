#!/usr/bin/env python3
"""Keep the bundled Jira MCP server package ready to start instantly.

Claude Code gives an MCP server 30 seconds to finish connecting. A plain
``uvx mcp-atlassian`` resolves against the package index first, so on a cold
cache — or on the day a new release lands — it spends that whole budget
downloading ~150 MB and gets killed before it ever speaks. What the user sees
is a server that "failed to start", or is labelled as needing authentication,
and a reconnect-and-hope loop with no indication of what is actually wrong.

SessionStart hooks can't prevent that on their own: they start ~150ms *after*
the MCP server and run concurrently with it, so they cannot warm the cache in
time for the session they run in.

So responsibilities are split. The server only ever starts from the local
cache, which is fast and needs no network. The hook is the only part that
talks to the index: it fetches the package when nothing is cached, and
otherwise refreshes it in the background at most once a week. Downloads
therefore happen off the startup path, where taking two minutes is fine.
"""
import subprocess
import sys
from pathlib import Path

PACKAGE = "mcp-atlassian"
REFRESH_INTERVAL_SECONDS = 7 * 24 * 60 * 60
REFRESH_MARKER = "server-refreshed"
PROBE_TIMEOUT_SECONDS = 60

# Points at /mcp rather than "start a new session" on purpose. A server that
# failed to start is flagged by Claude Code and skipped in later sessions, so
# restarting alone can take two rounds to recover; reconnecting works at once.
COLD_CACHE_NOTICE = (
    f"[jira-claude-plugin] Jira 서버 패키지({PACKAGE}, 약 150MB)를 처음 "
    "내려받는 중입니다. 이번 세션에서는 Jira 도구가 보이지 않습니다.\n"
    "  → 다운로드가 끝나면 /mcp 에서 atlassian 을 재연결하세요. "
    "그 다음부터는 매 세션 자동으로 연결됩니다."
)


def is_cached() -> bool:
    """Whether the server can be started without touching the network."""
    try:
        proc = subprocess.run(
            ["uvx", "--offline", PACKAGE, "--version"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=PROBE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def start_command(cached: bool) -> list[str]:
    """The command that launches the server. ``--offline`` keeps an index
    resolve — and any download it would trigger — out of the 30s connect
    budget. Without a cache there is nothing to do but fetch and hope."""
    return ["uvx", "--offline", PACKAGE] if cached else ["uvx", PACKAGE]


def _detach_kwargs() -> dict:
    if sys.platform == "win32":
        flags = getattr(subprocess, "DETACHED_PROCESS", 0)
        flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        return {"creationflags": flags}
    return {"start_new_session": True}


def fetch_in_background() -> bool:
    """Start downloading the package without holding up session start. Fully
    detached: a hook that leaves a child holding its stdout would block
    Claude Code until the download finished."""
    try:
        subprocess.Popen(
            ["uvx", PACKAGE, "--version"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            **_detach_kwargs(),
        )
    except OSError:
        return False
    return True


def refresh_marker(state_dir: Path) -> Path:
    return state_dir / REFRESH_MARKER


def is_refresh_due(marker: Path, now: float) -> bool:
    try:
        last_refresh = float(marker.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return True
    return now - last_refresh >= REFRESH_INTERVAL_SECONDS


def record_refresh(marker: Path, now: float) -> None:
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(f"{now:.0f}\n", encoding="utf-8")
    except OSError:
        pass


def prepare(state_dir: Path, now: float) -> str | None:
    """Make sure the package will be cached for the next server start.
    Returns a message for the user, or None when there is nothing to say."""
    if not is_cached():
        fetch_in_background()
        return COLD_CACHE_NOTICE
    marker = refresh_marker(state_dir)
    if is_refresh_due(marker, now) and fetch_in_background():
        record_refresh(marker, now)
    return None
