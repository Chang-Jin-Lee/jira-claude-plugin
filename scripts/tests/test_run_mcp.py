import json
from types import SimpleNamespace

import run_mcp as rm

CREDS = {"jira_url": "https://x.atlassian.net", "jira_email": "a@b.com", "jira_api_token": "t"}


def test_build_env_injects_credentials_and_read_only():
    env = rm.build_env(CREDS, {"PATH": "/usr/bin"})
    assert env["JIRA_URL"] == "https://x.atlassian.net"
    assert env["JIRA_USERNAME"] == "a@b.com"
    assert env["JIRA_API_TOKEN"] == "t"
    assert env["READ_ONLY_MODE"] == "true"
    assert env["PATH"] == "/usr/bin"


def test_creds_from_env_reads_user_config_substituted_vars():
    # The documented mechanism: Claude Code substitutes ${user_config.*} into
    # the plugin's .mcp.json env block before spawning this process.
    env = {
        "JIRA_URL": "https://x.atlassian.net",
        "JIRA_USERNAME": "a@b.com",
        "JIRA_API_TOKEN": "t",
    }
    assert rm.creds_from_env(env) == CREDS


def test_creds_from_env_falls_back_to_plugin_option_vars():
    env = {
        "CLAUDE_PLUGIN_OPTION_JIRA_URL": "https://x.atlassian.net",
        "CLAUDE_PLUGIN_OPTION_JIRA_EMAIL": "a@b.com",
        "CLAUDE_PLUGIN_OPTION_JIRA_API_TOKEN": "t",
    }
    assert rm.creds_from_env(env) == CREDS


def test_creds_from_env_ignores_unexpanded_placeholders():
    # A Claude Code build that does not expand ${user_config.*} (or this repo's
    # own project-scoped .mcp.json copy, which has no plugin context) hands the
    # references through literally. Those are not credentials.
    env = {
        "JIRA_URL": "${user_config.jira_url}",
        "JIRA_USERNAME": "${user_config.jira_email}",
        "JIRA_API_TOKEN": "${user_config.jira_api_token}",
    }
    assert rm.creds_from_env(env) is None


def test_creds_from_env_ignores_partially_set_vars():
    env = {"JIRA_URL": "https://x.atlassian.net", "JIRA_USERNAME": "", "JIRA_API_TOKEN": "t"}
    assert rm.creds_from_env(env) is None


def test_creds_from_env_returns_none_when_unset():
    assert rm.creds_from_env({"PATH": "/usr/bin"}) is None


def test_resolve_from_env_labels_the_source_it_used():
    direct = {"JIRA_URL": "u", "JIRA_USERNAME": "e", "JIRA_API_TOKEN": "t"}
    assert rm.resolve_from_env(direct)[1] == "env (user_config)"
    options = {
        "CLAUDE_PLUGIN_OPTION_JIRA_URL": "u",
        "CLAUDE_PLUGIN_OPTION_JIRA_EMAIL": "e",
        "CLAUDE_PLUGIN_OPTION_JIRA_API_TOKEN": "t",
    }
    assert rm.resolve_from_env(options)[1] == "env (plugin options)"


def test_main_logs_the_credential_source_without_the_values(monkeypatch, tmp_path, capsys):
    secret = "ATATT-do-not-log-me"
    monkeypatch.setenv("JIRA_URL", CREDS["jira_url"])
    monkeypatch.setenv("JIRA_USERNAME", CREDS["jira_email"])
    monkeypatch.setenv("JIRA_API_TOKEN", secret)
    monkeypatch.setattr(rm, "credentials_path", lambda: tmp_path / "credentials.json")
    monkeypatch.setattr(rm.subprocess, "run", lambda cmd, env: SimpleNamespace(returncode=0))
    assert rm.main() == 0
    err = capsys.readouterr().err
    assert "credentials from env (user_config)" in err
    assert secret not in err
    assert CREDS["jira_email"] not in err


def test_wait_for_credentials_returns_creds_when_present(tmp_path):
    path = tmp_path / "credentials.json"
    path.write_text(json.dumps(CREDS), encoding="utf-8")
    assert rm.wait_for_credentials(path, attempts=1, delay=0) == CREDS


def test_wait_for_credentials_retries_then_gives_up(tmp_path, monkeypatch):
    sleeps = []
    monkeypatch.setattr(rm.time, "sleep", lambda s: sleeps.append(s))
    assert rm.wait_for_credentials(tmp_path / "nope.json", attempts=3, delay=2) is None
    assert sleeps == [2, 2]


def test_wait_for_credentials_picks_up_file_appearing_between_attempts(tmp_path, monkeypatch):
    path = tmp_path / "credentials.json"

    def write_then_noop(_):
        path.write_text(json.dumps(CREDS), encoding="utf-8")

    monkeypatch.setattr(rm.time, "sleep", write_then_noop)
    assert rm.wait_for_credentials(path, attempts=2, delay=1) == CREDS


def test_wait_for_credentials_retries_past_a_truncated_file(tmp_path, monkeypatch):
    # Regression: the hook's write and this process's read raced, so the file
    # existed with no content yet. Reading it crashed the server, which made
    # Claude Code flag the plugin's MCP server as needing authentication.
    path = tmp_path / "credentials.json"
    path.write_text("", encoding="utf-8")

    def fill(_):
        path.write_text(json.dumps(CREDS), encoding="utf-8")

    monkeypatch.setattr(rm.time, "sleep", fill)
    assert rm.wait_for_credentials(path, attempts=2, delay=1) == CREDS


def test_wait_for_credentials_gives_up_on_a_file_that_stays_truncated(tmp_path, monkeypatch):
    path = tmp_path / "credentials.json"
    path.write_text("", encoding="utf-8")
    monkeypatch.setattr(rm.time, "sleep", lambda s: None)
    assert rm.wait_for_credentials(path, attempts=2, delay=1) is None


def test_main_uses_env_creds_without_waiting_on_the_file(monkeypatch, tmp_path):
    # With credentials in the environment there is nothing to race against:
    # the wrapper must not consult the shared file at all.
    monkeypatch.setenv("JIRA_URL", CREDS["jira_url"])
    monkeypatch.setenv("JIRA_USERNAME", CREDS["jira_email"])
    monkeypatch.setenv("JIRA_API_TOKEN", CREDS["jira_api_token"])
    monkeypatch.setattr(rm, "credentials_path", lambda: tmp_path / "credentials.json")

    def fail(*a, **k):
        raise AssertionError("must not wait for the credentials file")

    monkeypatch.setattr(rm, "wait_for_credentials", fail)
    monkeypatch.setattr(rm.subprocess, "run", lambda cmd, env: SimpleNamespace(returncode=0))
    assert rm.main() == 0


def test_main_backfills_credentials_file_from_env(monkeypatch, tmp_path):
    # Keeps the standalone tree browser working even if the SessionStart hook
    # never ran, so one round of /plugin config is genuinely enough.
    monkeypatch.setenv("JIRA_URL", CREDS["jira_url"])
    monkeypatch.setenv("JIRA_USERNAME", CREDS["jira_email"])
    monkeypatch.setenv("JIRA_API_TOKEN", CREDS["jira_api_token"])
    path = tmp_path / "credentials.json"
    monkeypatch.setattr(rm, "credentials_path", lambda: path)
    monkeypatch.setattr(rm.subprocess, "run", lambda cmd, env: SimpleNamespace(returncode=0))
    assert rm.main() == 0
    assert json.loads(path.read_text(encoding="utf-8")) == CREDS


def test_main_starts_server_even_if_backfill_fails(monkeypatch, tmp_path):
    monkeypatch.setenv("JIRA_URL", CREDS["jira_url"])
    monkeypatch.setenv("JIRA_USERNAME", CREDS["jira_email"])
    monkeypatch.setenv("JIRA_API_TOKEN", CREDS["jira_api_token"])
    monkeypatch.setattr(rm, "credentials_path", lambda: tmp_path / "credentials.json")
    monkeypatch.setattr(
        rm, "write_credentials", lambda *a: (_ for _ in ()).throw(OSError("read-only"))
    )
    monkeypatch.setattr(rm.subprocess, "run", lambda cmd, env: SimpleNamespace(returncode=0))
    assert rm.main() == 0


def test_main_runs_server_with_injected_env(monkeypatch, tmp_path):
    for var in ("JIRA_URL", "JIRA_USERNAME", "JIRA_API_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    path = tmp_path / "credentials.json"
    path.write_text(json.dumps(CREDS), encoding="utf-8")
    monkeypatch.setattr(rm, "credentials_path", lambda: path)
    calls = []

    def fake_run(cmd, env):
        calls.append((cmd, env))
        return SimpleNamespace(returncode=7)

    monkeypatch.setattr(rm.subprocess, "run", fake_run)
    assert rm.main() == 7
    cmd, env = calls[0]
    assert cmd == ["uvx", "mcp-atlassian"]
    assert env["JIRA_URL"] == "https://x.atlassian.net"
    assert env["JIRA_API_TOKEN"] == "t"


def test_main_returns_1_when_credentials_never_appear(monkeypatch, tmp_path, capsys):
    for var in ("JIRA_URL", "JIRA_USERNAME", "JIRA_API_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(rm, "credentials_path", lambda: tmp_path / "nope.json")
    monkeypatch.setattr(rm.time, "sleep", lambda s: None)
    calls = []
    monkeypatch.setattr(rm.subprocess, "run", lambda *a, **k: calls.append(a))
    assert rm.main() == 1
    assert calls == []
    assert "credentials" in capsys.readouterr().err
