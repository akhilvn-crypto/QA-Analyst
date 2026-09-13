import json
from pathlib import Path

import pytest

from orchestrator.utils import config


@pytest.fixture
def isolated_config(monkeypatch, tmp_path):
    """Point config_path() at a scratch file and clear the module cache
    before and after each test, so tests never touch this repo's own
    config/settings.json or leak state between each other."""
    cfg_path = tmp_path / "settings.json"
    monkeypatch.setattr(config, "config_path", lambda: cfg_path)
    config.load_config.cache_clear()
    yield cfg_path
    config.load_config.cache_clear()


def test_missing_config_self_creates_with_defaults(isolated_config):
    assert not isolated_config.exists()

    loaded = config.load_config()

    assert isolated_config.exists()
    assert loaded == config.DEFAULTS
    on_disk = json.loads(isolated_config.read_text(encoding="utf-8"))
    assert on_disk == config.DEFAULTS


def test_corrupt_config_falls_back_to_defaults(isolated_config):
    isolated_config.write_text("not valid json", encoding="utf-8")

    loaded = config.load_config()

    assert loaded == config.DEFAULTS


def test_partial_config_is_merged_with_defaults(isolated_config):
    isolated_config.write_text(
        json.dumps({"knowledgeBase": {"obsidianPath": "/notes"}}), encoding="utf-8"
    )

    loaded = config.load_config()

    assert loaded["knowledgeBase"]["obsidianPath"] == "/notes"
    assert loaded["requirementReading"]["obsidianPath"] == ""


def test_retired_chunking_limit_is_carried_through_without_breaking_load(isolated_config):
    """A config written before the vector store was removed still carries
    `chunkingLimit`. Nothing reads it, but an unknown key must not make the
    file look corrupt and get overwritten with defaults."""
    isolated_config.write_text(
        json.dumps({"knowledgeBase": {"chunkingLimit": 1500, "obsidianPath": "/notes"}}),
        encoding="utf-8",
    )

    loaded = config.load_config()

    assert loaded["knowledgeBase"]["obsidianPath"] == "/notes"
    assert loaded["knowledgeBase"]["chunkingLimit"] == 1500


def test_retired_top_k_is_carried_through_without_breaking_load(isolated_config):
    """A config written before ranked search results were uncapped still
    carries `topK`. Nothing reads it, but an unknown key must not make the
    file look corrupt and get overwritten with defaults -- same contract
    `chunkingLimit` already gets above."""
    isolated_config.write_text(
        json.dumps({"knowledgeBase": {"topK": 3, "obsidianPath": "/notes"}}),
        encoding="utf-8",
    )

    loaded = config.load_config()

    assert loaded["knowledgeBase"]["obsidianPath"] == "/notes"
    assert loaded["knowledgeBase"]["topK"] == 3


def test_obsidian_vault_path_is_none_when_blank(isolated_config):
    assert config.obsidian_vault_path() is None


def test_obsidian_vault_path_returns_configured_path(isolated_config, tmp_path):
    vault = tmp_path / "MyVault" / "QA"
    isolated_config.write_text(
        json.dumps({"knowledgeBase": {"obsidianPath": str(vault)}}), encoding="utf-8"
    )

    assert config.obsidian_vault_path() == vault


def test_requirement_reading_vault_path_is_none_when_blank(isolated_config):
    assert config.requirement_reading_vault_path() is None


def test_requirement_reading_vault_path_returns_configured_path(isolated_config, tmp_path):
    vault = tmp_path / "ReadingVault" / "Reference"
    isolated_config.write_text(
        json.dumps({"requirementReading": {"obsidianPath": str(vault)}}), encoding="utf-8"
    )

    assert config.requirement_reading_vault_path() == vault


def test_requirement_reading_vault_path_independent_of_knowledge_base_path(isolated_config, tmp_path):
    kb_vault = tmp_path / "KbVault"
    isolated_config.write_text(
        json.dumps({"knowledgeBase": {"obsidianPath": str(kb_vault)}}), encoding="utf-8"
    )

    assert config.obsidian_vault_path() == kb_vault
    assert config.requirement_reading_vault_path() is None


def test_requirement_handoff_destination_path_is_none_when_blank(isolated_config):
    assert config.requirement_handoff_destination_path() is None


def test_requirement_handoff_destination_path_returns_configured_path(isolated_config, tmp_path):
    destination = tmp_path / "Vault" / "Handoff"
    isolated_config.write_text(
        json.dumps({"requirementHandoff": {"obsidianDestinationPath": str(destination)}}),
        encoding="utf-8",
    )

    assert config.requirement_handoff_destination_path() == destination


def test_partial_config_merges_new_sections_with_defaults(isolated_config):
    isolated_config.write_text(
        json.dumps({"knowledgeBase": {"obsidianPath": "/notes"}}), encoding="utf-8"
    )

    loaded = config.load_config()

    assert loaded["requirementReading"] == config.DEFAULTS["requirementReading"]
    assert loaded["requirementHandoff"] == config.DEFAULTS["requirementHandoff"]
    assert loaded["operator"] == config.DEFAULTS["operator"]


def test_operator_info_is_blank_by_default(isolated_config):
    assert config.operator_info() == config.DEFAULTS["operator"]


def test_operator_info_returns_configured_identity(isolated_config):
    isolated_config.write_text(
        json.dumps(
            {
                "operator": {
                    "name": "Akhil VN",
                    "designation": "QA Lead",
                    "projectName": "LinkGrid",
                    "projectId": "LG-001",
                }
            }
        ),
        encoding="utf-8",
    )

    assert config.operator_info() == {
        "name": "Akhil VN",
        "designation": "QA Lead",
        "projectName": "LinkGrid",
        "projectId": "LG-001",
    }
