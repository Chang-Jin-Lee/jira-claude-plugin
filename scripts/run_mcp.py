#!/usr/bin/env python3
"""Launch the bundled mcp-atlassian server with the user's Jira credentials.

Credentials are resolved in this order, first hit wins:

1. ``JIRA_URL`` / ``JIRA_USERNAME`` / ``JIRA_API_TOKEN`` in this process's
   environment. The plugin's ``.mcp.json`` sets these from
   ``${user_config.*}``, which Claude Code substitutes before spawning us.
   This is the only path with no shared state and nothing to race against.
2. ``CLAUDE_PLUGIN_OPTION_*``, in case a Claude Code build passes plugin
   options through but leaves ``${user_config.*}`` unexpanded
   (anthropics/claude-code#51573).
3. ``~/.jira-claude-plugin/credentials.json``, written by the SessionStart
   hook. Last resort: that hook and this process start together in no
   guaranteed order, so the file may not be there yet — hence the wait.

Whichever path wins, the file is refreshed from it, so the standalone tree
browser works after one round of ``/plugin`` configuration even if the hook
never got the options.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sync_credentials import (  # noqa: E402
    DIRECT_ENV_KEYS,
    ENV_KEYS as PLUGIN_OPTION_KEYS,
    creds_from_env_vars,
    credentials_path,
    read_credentials,
    write_credentials,
)

ENV_MAP = {var: key for key, var in DIRECT_ENV_KEYS.items()}


def build_env(creds: dict, base_env: dict) -> dict:
    env = dict(base_env)
    for var, key in ENV_MAP.items():
        env[var] = creds[key]
    env["READ_ONLY_MODE"] = "true"
    return env


ENV_SOURCES = (
    (DIRECT_ENV_KEYS, "env (user_config)"),
    (PLUGIN_OPTION_KEYS, "env (plugin options)"),
)


def resolve_from_env(env: dict) -> tuple[dict, str] | None:
    """Credentials from this process's environment, labelled with which
    variables carried them, or None if neither set is fully populated."""
    for keys, label in ENV_SOURCES:
        creds = creds_from_env_vars(env, keys)
        if creds is not None:
            return creds, label
    return None


def creds_from_env(env: dict) -> dict | None:
    resolved = resolve_from_env(env)
    return resolved[0] if resolved else None


def wait_for_credentials(path: Path, attempts: int = 5, delay: float = 2.0) -> dict | None:
    for attempt in range(attempts):
        creds = read_credentials(path)
        if creds is not None:
            return creds
        if attempt < attempts - 1:
            time.sleep(delay)
    return None


def main() -> int:
    env = dict(os.environ)
    resolved = resolve_from_env(env)
    if resolved is None:
        creds = wait_for_credentials(credentials_path())
        source = "synced credentials file"
    else:
        creds, source = resolved
    if creds is None:
        print(
            "jira-claude-plugin: no Jira credentials available - configure the "
            "plugin via /plugin (jira_url/jira_email/jira_api_token), then "
            "start a new session or reconnect this server from /mcp.",
            file=sys.stderr,
        )
        return 1
    # Names the boundary the credentials came across. Claude Code captures
    # this in the server's log, which is where you look when Jira stops
    # working — never the values themselves.
    print(f"jira-claude-plugin: credentials from {source}", file=sys.stderr)
    try:
        write_credentials(creds, credentials_path())
    except OSError as exc:
        # The tree browser loses its credentials file, but the MCP server this
        # process exists to run does not depend on it.
        print(f"jira-claude-plugin: could not refresh credentials file: {exc}", file=sys.stderr)
    proc = subprocess.run(["uvx", "mcp-atlassian"], env=build_env(creds, env))
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
