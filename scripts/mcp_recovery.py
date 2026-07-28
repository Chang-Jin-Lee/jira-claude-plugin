#!/usr/bin/env python3
"""Clear this plugin's stale "needs authentication" flag.

When an MCP server fails to start, Claude Code records it in
``~/.claude/mcp-needs-auth-cache.json`` — and then stops starting that server
in later sessions. Restarting does not clear it; the user has to reconnect the
server by hand. That is the reconnect step people keep hitting: one early
failure, usually because uv or the server package wasn't ready yet, and the
server stays down from then on no matter how many times they restart.

For this plugin the label is always wrong. It authenticates with an API token
passed in through the server's environment and never performs an OAuth flow,
so an entry there only ever means "failed to start once".

So once the environment is healthy again, drop our own entry — and only ours —
and the next session starts the server normally.
"""
import json
import os
import sys
from pathlib import Path

SERVER_KEY = "plugin:jira-claude-plugin:atlassian"


def needs_auth_cache_path() -> Path:
    return Path.home() / ".claude" / "mcp-needs-auth-cache.json"


def clear_needs_auth(path: Path, key: str = SERVER_KEY) -> bool:
    """Remove our entry. Returns whether anything was actually removed.

    Claude Code owns this file, so every failure mode here is non-fatal: a
    shape we don't recognise, a missing file, a read-only directory, another
    process writing at the same time. Leave it alone and move on.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(data, dict) or key not in data:
        return False
    del data[key]
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(json.dumps(data), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
        return False
    return True


def main() -> int:
    """Entry point for the bootstrap scripts, which call this with the uv they
    have just installed — by then the environment is fixed and the flag is the
    only thing left holding the server down."""
    sys.stdout.reconfigure(encoding="utf-8")
    if clear_needs_auth(needs_auth_cache_path()):
        print("이전에 실패로 표시됐던 Jira 서버 상태를 초기화했습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
