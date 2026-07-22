import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MARKETPLACE_PATH = REPO_ROOT / ".agents" / "plugins" / "marketplace.json"


def test_marketplace_lists_the_plugin_with_local_root_source():
    marketplace = json.loads(MARKETPLACE_PATH.read_text(encoding="utf-8"))
    assert marketplace["name"] == "jira-claude-plugin"
    entries = marketplace["plugins"]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["name"] == "jira-claude-plugin"
    assert entry["source"] == {"source": "url", "url": "./"}
    assert entry["policy"] == {"installation": "AVAILABLE", "authentication": "ON_INSTALL"}
    assert entry["category"]
