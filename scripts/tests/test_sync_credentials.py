import json

import pytest

import sync_credentials as sc

CREDS = {"jira_url": "https://x.atlassian.net", "jira_email": "a@b.com", "jira_api_token": "t"}
ENV_VARS = (
    "CLAUDE_PLUGIN_OPTION_JIRA_URL",
    "CLAUDE_PLUGIN_OPTION_JIRA_EMAIL",
    "CLAUDE_PLUGIN_OPTION_JIRA_API_TOKEN",
)


@pytest.fixture(autouse=True)
def offline_server_package(monkeypatch):
    """main() asks server_package to keep the MCP server's package downloaded.
    Keep that off the network unless a test opts in; server_package's own
    behaviour is covered in test_server_package.py."""
    monkeypatch.setattr(sc.server_package, "prepare", lambda state_dir, now: None)
    monkeypatch.setattr(sc.mcp_recovery, "clear_needs_auth", lambda path, **k: False)


def test_build_credentials_returns_dict_when_all_present():
    env = {
        "CLAUDE_PLUGIN_OPTION_JIRA_URL": "https://x.atlassian.net",
        "CLAUDE_PLUGIN_OPTION_JIRA_EMAIL": "a@b.com",
        "CLAUDE_PLUGIN_OPTION_JIRA_API_TOKEN": "tok",
    }
    result = sc.build_credentials(env)
    assert result == {
        "jira_url": "https://x.atlassian.net",
        "jira_email": "a@b.com",
        "jira_api_token": "tok",
    }


def test_build_credentials_returns_none_when_missing():
    env = {
        "CLAUDE_PLUGIN_OPTION_JIRA_URL": "https://x.atlassian.net",
        "CLAUDE_PLUGIN_OPTION_JIRA_EMAIL": "",
        "CLAUDE_PLUGIN_OPTION_JIRA_API_TOKEN": "tok",
    }
    assert sc.build_credentials(env) is None


def test_write_credentials_writes_json_to_path(tmp_path):
    creds = {"jira_url": "u", "jira_email": "e", "jira_api_token": "t"}
    target = tmp_path / "nested" / "credentials.json"
    sc.write_credentials(creds, target)
    assert json.loads(target.read_text(encoding="utf-8")) == creds


def test_read_credentials_returns_none_when_missing(tmp_path):
    assert sc.read_credentials(tmp_path / "nope.json") is None


def test_read_credentials_returns_none_for_truncated_file(tmp_path):
    # The exact state that crashed the MCP wrapper: the file exists but a
    # concurrent write has not put any content in it yet.
    path = tmp_path / "credentials.json"
    path.write_text("", encoding="utf-8")
    assert sc.read_credentials(path) is None


def test_read_credentials_returns_none_for_partial_json(tmp_path):
    path = tmp_path / "credentials.json"
    path.write_text('{"jira_url": "https://x.atlas', encoding="utf-8")
    assert sc.read_credentials(path) is None


def test_read_credentials_returns_none_when_a_field_is_blank(tmp_path):
    path = tmp_path / "credentials.json"
    path.write_text(json.dumps({**CREDS, "jira_api_token": ""}), encoding="utf-8")
    assert sc.read_credentials(path) is None


def test_read_credentials_returns_creds_when_complete(tmp_path):
    path = tmp_path / "credentials.json"
    path.write_text(json.dumps(CREDS), encoding="utf-8")
    assert sc.read_credentials(path) == CREDS


def test_write_credentials_skips_rewrite_when_unchanged(tmp_path):
    path = tmp_path / "credentials.json"
    assert sc.write_credentials(CREDS, path) is True
    before = path.stat().st_mtime_ns
    assert sc.write_credentials(CREDS, path) is False
    assert path.stat().st_mtime_ns == before


def test_write_credentials_leaves_previous_file_intact_when_publish_fails(tmp_path, monkeypatch):
    # Proves the target is never truncated-then-filled: a failure mid-write
    # must leave a reader seeing the old, complete credentials.
    path = tmp_path / "credentials.json"
    sc.write_credentials(CREDS, path)
    monkeypatch.setattr(sc.os, "replace", lambda *a: (_ for _ in ()).throw(OSError("boom")))
    with pytest.raises(OSError):
        sc.write_credentials({**CREDS, "jira_api_token": "new"}, path)
    assert sc.read_credentials(path) == CREDS


def test_write_credentials_leaves_no_temp_files_behind(tmp_path):
    path = tmp_path / "credentials.json"
    sc.write_credentials(CREDS, path)
    assert [p.name for p in tmp_path.iterdir()] == ["credentials.json"]


def test_browse_command_hint_includes_resolved_path():
    hint = sc.browse_command_hint("/plugin/root")
    assert "/plugin/root/scripts/browse_tree.py" in hint
    # --no-project so running the browser from inside the user's own Python
    # project doesn't make uv resolve and build that project first.
    assert "uv run --no-project --with textual,requests" in hint


def test_main_writes_file_and_prints_hint(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_JIRA_URL", "https://x.atlassian.net")
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_JIRA_EMAIL", "a@b.com")
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_JIRA_API_TOKEN", "tok")
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/plugin/root")
    monkeypatch.setattr(sc, "credentials_path", lambda: tmp_path / "credentials.json")
    exit_code = sc.main()
    assert exit_code == 0
    written = json.loads((tmp_path / "credentials.json").read_text(encoding="utf-8"))
    assert written["jira_url"] == "https://x.atlassian.net"
    captured = capsys.readouterr()
    assert "/plugin/root/scripts/browse_tree.py" in captured.out


def test_main_skips_write_when_incomplete(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("CLAUDE_PLUGIN_OPTION_JIRA_URL", raising=False)
    monkeypatch.delenv("CLAUDE_PLUGIN_OPTION_JIRA_EMAIL", raising=False)
    monkeypatch.delenv("CLAUDE_PLUGIN_OPTION_JIRA_API_TOKEN", raising=False)
    monkeypatch.setattr(sc, "credentials_path", lambda: tmp_path / "credentials.json")
    exit_code = sc.main()
    assert exit_code == 0
    assert not (tmp_path / "credentials.json").exists()
    assert "설정이 아직 없습니다" in capsys.readouterr().out


def test_load_credentials_reads_file_when_present(tmp_path):
    creds = {"jira_url": "https://x.atlassian.net", "jira_email": "a@b.com", "jira_api_token": "t"}
    path = tmp_path / "credentials.json"
    path.write_text(json.dumps(creds), encoding="utf-8")
    assert sc.load_credentials(path) == creds


def test_load_credentials_falls_back_to_env_when_file_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("JIRA_URL", "https://x.atlassian.net")
    monkeypatch.setenv("JIRA_USERNAME", "a@b.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "t")
    result = sc.load_credentials(tmp_path / "nope.json")
    assert result == {
        "jira_url": "https://x.atlassian.net",
        "jira_email": "a@b.com",
        "jira_api_token": "t",
    }


def test_load_credentials_returns_none_when_file_missing_and_env_incomplete(monkeypatch, tmp_path):
    monkeypatch.delenv("JIRA_URL", raising=False)
    monkeypatch.delenv("JIRA_USERNAME", raising=False)
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    assert sc.load_credentials(tmp_path / "nope.json") is None


def test_load_credentials_falls_back_to_env_when_file_incomplete(monkeypatch, tmp_path):
    path = tmp_path / "credentials.json"
    path.write_text(
        json.dumps({"jira_url": "", "jira_email": "", "jira_api_token": ""}),
        encoding="utf-8",
    )
    monkeypatch.setenv("JIRA_URL", "https://x.atlassian.net")
    monkeypatch.setenv("JIRA_USERNAME", "a@b.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "t")
    result = sc.load_credentials(path)
    assert result == {
        "jira_url": "https://x.atlassian.net",
        "jira_email": "a@b.com",
        "jira_api_token": "t",
    }


def test_load_credentials_falls_back_to_env_when_file_is_mid_write(monkeypatch, tmp_path):
    # A torn read must fall through to the environment, not raise.
    path = tmp_path / "credentials.json"
    path.write_text("", encoding="utf-8")
    monkeypatch.setenv("JIRA_URL", "https://x.atlassian.net")
    monkeypatch.setenv("JIRA_USERNAME", "a@b.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "t")
    assert sc.load_credentials(path) == CREDS


def test_creds_from_env_vars_ignores_unexpanded_references():
    env = dict.fromkeys(sc.DIRECT_ENV_KEYS.values(), "${JIRA_URL}")
    assert sc.creds_from_env_vars(env, sc.DIRECT_ENV_KEYS) is None


def test_main_does_not_nag_when_options_absent_but_creds_already_stored(
    monkeypatch, tmp_path, capsys
):
    # Options only reach hooks after the plugin is configured; on a session
    # where they are missing, already-stored credentials still work, so the
    # hook must not tell the user to go re-enter them.
    monkeypatch.delenv("CLAUDE_PLUGIN_OPTION_JIRA_URL", raising=False)
    monkeypatch.delenv("CLAUDE_PLUGIN_OPTION_JIRA_EMAIL", raising=False)
    monkeypatch.delenv("CLAUDE_PLUGIN_OPTION_JIRA_API_TOKEN", raising=False)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/plugin/root")
    path = tmp_path / "credentials.json"
    path.write_text(json.dumps(CREDS), encoding="utf-8")
    monkeypatch.setattr(sc, "credentials_path", lambda: path)
    assert sc.main() == 0
    out = capsys.readouterr().out
    assert "설정이 아직 없습니다" not in out
    assert "/plugin/root/scripts/browse_tree.py" in out


def test_main_downloads_the_server_package_before_jira_is_configured(monkeypatch, tmp_path):
    # The freshly-installed, not-yet-configured session is the best moment to
    # start the ~150 MB download — the user is busy pasting in a token.
    for var in ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(sc, "credentials_path", lambda: tmp_path / "credentials.json")
    prepared = []
    monkeypatch.setattr(
        sc.server_package, "prepare", lambda state_dir, now: prepared.append(state_dir)
    )
    assert sc.main() == 0
    assert prepared == [tmp_path]


def test_main_clears_a_stale_needs_auth_flag_once_the_package_is_ready(
    monkeypatch, tmp_path, capsys
):
    # Claude Code stops starting a flagged server entirely, across restarts,
    # so leaving the flag set is what forces the manual /mcp reconnect.
    for var, value in zip(ENV_VARS, CREDS.values()):
        monkeypatch.setenv(var, value)
    monkeypatch.setattr(sc, "credentials_path", lambda: tmp_path / "credentials.json")
    monkeypatch.setattr(sc.server_package, "prepare", lambda state_dir, now: None)
    cleared = []
    monkeypatch.setattr(
        sc.mcp_recovery, "clear_needs_auth", lambda path, **k: cleared.append(path) or True
    )
    assert sc.main() == 0
    assert len(cleared) == 1
    assert "초기화했습니다" in capsys.readouterr().out


def test_main_leaves_the_flag_alone_while_the_package_is_still_downloading(
    monkeypatch, tmp_path
):
    # Clearing it now would just let the next session fail and set it again.
    for var, value in zip(ENV_VARS, CREDS.values()):
        monkeypatch.setenv(var, value)
    monkeypatch.setattr(sc, "credentials_path", lambda: tmp_path / "credentials.json")
    monkeypatch.setattr(sc.server_package, "prepare", lambda state_dir, now: "받는 중")
    monkeypatch.setattr(
        sc.mcp_recovery,
        "clear_needs_auth",
        lambda path, **k: (_ for _ in ()).throw(AssertionError("must not clear")),
    )
    assert sc.main() == 0


def test_main_says_nothing_when_there_was_no_stale_flag(monkeypatch, tmp_path, capsys):
    for var, value in zip(ENV_VARS, CREDS.values()):
        monkeypatch.setenv(var, value)
    monkeypatch.setattr(sc, "credentials_path", lambda: tmp_path / "credentials.json")
    monkeypatch.setattr(sc.server_package, "prepare", lambda state_dir, now: None)
    monkeypatch.setattr(sc.mcp_recovery, "clear_needs_auth", lambda path, **k: False)
    assert sc.main() == 0
    assert "초기화했습니다" not in capsys.readouterr().out


def test_main_passes_on_the_server_package_notice(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_JIRA_URL", CREDS["jira_url"])
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_JIRA_EMAIL", CREDS["jira_email"])
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_JIRA_API_TOKEN", CREDS["jira_api_token"])
    monkeypatch.setattr(sc, "credentials_path", lambda: tmp_path / "credentials.json")
    monkeypatch.setattr(sc.server_package, "prepare", lambda state_dir, now: "다운로드 중입니다")
    assert sc.main() == 0
    assert "다운로드 중입니다" in capsys.readouterr().out


def test_main_says_nothing_extra_when_the_server_package_is_ready(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_JIRA_URL", CREDS["jira_url"])
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_JIRA_EMAIL", CREDS["jira_email"])
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_JIRA_API_TOKEN", CREDS["jira_api_token"])
    monkeypatch.setattr(sc, "credentials_path", lambda: tmp_path / "credentials.json")
    out = (sc.main(), capsys.readouterr().out)[1]
    assert out.strip().count("\n") == 0  # just the tree-browser hint


def test_main_keeps_the_refresh_marker_beside_the_credentials_file(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_JIRA_URL", CREDS["jira_url"])
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_JIRA_EMAIL", CREDS["jira_email"])
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_JIRA_API_TOKEN", CREDS["jira_api_token"])
    seen = {}
    monkeypatch.setattr(sc, "credentials_path", lambda: tmp_path / "sub" / "credentials.json")
    monkeypatch.setattr(
        sc.server_package, "prepare", lambda state_dir, now: seen.setdefault("dir", state_dir)
    )
    assert sc.main() == 0
    assert seen["dir"] == tmp_path / "sub"


def test_main_does_not_rewrite_an_identical_credentials_file(monkeypatch, tmp_path):
    # Rewriting the same values every session is what opened the torn-read
    # window the MCP server crashed on.
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_JIRA_URL", CREDS["jira_url"])
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_JIRA_EMAIL", CREDS["jira_email"])
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_JIRA_API_TOKEN", CREDS["jira_api_token"])
    path = tmp_path / "credentials.json"
    path.write_text(json.dumps(CREDS), encoding="utf-8")
    monkeypatch.setattr(sc, "credentials_path", lambda: path)
    before = path.stat().st_mtime_ns
    assert sc.main() == 0
    assert path.stat().st_mtime_ns == before
