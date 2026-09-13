"""Tests for the Knowledge Base Service's plain, network-free core
(`KnowledgeBaseService`) and its pure HTTP route handlers -- no socket or
subprocess involved anywhere here, matching `test_search.py`'s own style.
The properties worth pinning: a failed (re)load never discards a
previously good KB, a load never exposes a half-built one, and
`/catalog`/`/file` correctly distinguish "never loaded" from "loading" from
"has content" (even stale content, per the spec's own "use the currently
active valid Knowledge Base if one exists" rule)."""

import json
import threading
import time

import pytest

from orchestrator.knowledge_base import service
from orchestrator.models.knowledge_base_service import (
    ERROR_FILE_NOT_FOUND,
    ERROR_KB_LOADING,
    ERROR_KB_NOT_LOADED,
    KB_ERROR,
    KB_LOADED,
    KB_LOADING,
    KB_NOT_LOADED,
)
from orchestrator.utils import config


@pytest.fixture
def blank_config(monkeypatch, tmp_path):
    cfg_path = tmp_path / "settings.json"
    cfg_path.write_text(json.dumps({}), encoding="utf-8")
    monkeypatch.setattr(config, "config_path", lambda: cfg_path)
    config.load_config.cache_clear()
    yield
    config.load_config.cache_clear()


@pytest.fixture
def vault(monkeypatch, tmp_path):
    """A configured `knowledgeBase.obsidianPath`, isolated from this repo's
    own config/settings.json -- same fixture shape as test_search.py's
    `vaults`."""
    kb = tmp_path / "kb"
    kb.mkdir()
    cfg_path = tmp_path / "settings.json"
    cfg_path.write_text(
        json.dumps({"knowledgeBase": {"obsidianPath": str(kb)}}), encoding="utf-8"
    )
    monkeypatch.setattr(config, "config_path", lambda: cfg_path)
    config.load_config.cache_clear()
    yield kb, cfg_path
    config.load_config.cache_clear()


# --- build_catalog_entry -----------------------------------------------------


def test_purpose_is_the_first_paragraph_before_any_heading():
    entry = service.build_catalog_entry(
        "architecture.md",
        "System architecture, services, components and integrations.\n\n"
        "## Services\ndetails\n## Dependencies\nmore\n",
    )
    assert entry.purpose == "System architecture, services, components and integrations."
    assert entry.topics == ["Services", "Dependencies"]


def test_purpose_is_the_first_headings_own_leading_paragraph_when_no_preamble():
    entry = service.build_catalog_entry(
        "workflows.md", "# Workflows\nExisting system and business workflows.\n## Detail\nx\n"
    )
    assert entry.purpose == "Existing system and business workflows."
    assert entry.topics == ["Workflows", "Detail"]


def test_topics_use_the_leaf_of_each_heading_trail_deduplicated():
    entry = service.build_catalog_entry(
        "a.md", "# Rules\nintro\n## KYC\nbody\n## KYC\nbody again\n"
    )
    assert entry.topics == ["Rules", "KYC"]


def test_headingless_file_has_no_topics_but_still_gets_a_purpose():
    entry = service.build_catalog_entry("flat.md", "Just a flat note with no headings at all.\n")
    assert entry.purpose == "Just a flat note with no headings at all."
    assert entry.topics == []


# --- KnowledgeBaseService.load -----------------------------------------------


def test_initial_state_is_not_loaded_with_no_content():
    kb = service.KnowledgeBaseService()
    status = kb.status()
    assert status.kb_state == KB_NOT_LOADED
    assert status.files_loaded == 0
    assert status.catalog_ready is False
    assert kb.has_content() is False


def test_load_populates_kb_and_catalog(vault):
    folder, _ = vault
    (folder / "business_rules.md").write_text(
        "Business rules and constraints.\n\n## Validation\ndetails\n", encoding="utf-8"
    )

    kb = service.KnowledgeBaseService()
    status = kb.load()

    assert status.kb_state == KB_LOADED
    assert status.files_loaded == 1
    assert status.catalog_ready is True
    assert status.loaded_at
    assert kb.has_content() is True
    assert "Business rules and constraints." in kb.get_file("business_rules.md")
    assert kb.get_catalog()[0]["name"] == "business_rules.md"


def test_load_with_unconfigured_path_is_an_error_with_no_content(blank_config):
    kb = service.KnowledgeBaseService()
    status = kb.load()

    assert status.kb_state == KB_ERROR
    assert status.error
    assert kb.has_content() is False


def test_load_with_missing_directory_is_an_error(monkeypatch, tmp_path):
    cfg_path = tmp_path / "settings.json"
    cfg_path.write_text(
        json.dumps({"knowledgeBase": {"obsidianPath": str(tmp_path / "gone")}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "config_path", lambda: cfg_path)
    config.load_config.cache_clear()
    try:
        kb = service.KnowledgeBaseService()
        status = kb.load()
        assert status.kb_state == KB_ERROR
        assert "does not exist" in status.error
    finally:
        config.load_config.cache_clear()


def test_failed_reload_preserves_the_previous_good_kb(vault):
    folder, cfg_path = vault
    (folder / "a.md").write_text("Original content.\n", encoding="utf-8")

    kb = service.KnowledgeBaseService()
    first = kb.load()
    assert first.kb_state == KB_LOADED

    # Break the configured path, then reload.
    cfg_path.write_text(
        json.dumps({"knowledgeBase": {"obsidianPath": str(folder.parent / "gone")}}),
        encoding="utf-8",
    )
    second = kb.load()

    assert second.kb_state == KB_ERROR
    assert second.error
    # The previously good content is still being served, not wiped.
    assert kb.has_content() is True
    assert kb.get_file("a.md") == "Original content.\n"
    assert kb.get_catalog()[0]["name"] == "a.md"


def test_reload_picks_up_a_config_change_without_a_restart(vault):
    """The server process is long-lived, so `load_config`'s cache must be
    cleared on every call -- otherwise a mid-session edit to
    knowledgeBase.obsidianPath would be invisible until the process is
    restarted, unlike every other orchestrator invocation (always a fresh,
    cold-cache process)."""
    folder, cfg_path = vault
    (folder / "a.md").write_text("first vault\n", encoding="utf-8")

    other = folder.parent / "other-kb"
    other.mkdir()
    (other / "b.md").write_text("second vault\n", encoding="utf-8")

    kb = service.KnowledgeBaseService()
    kb.load()
    assert kb.get_file("a.md") == "first vault\n"

    cfg_path.write_text(
        json.dumps({"knowledgeBase": {"obsidianPath": str(other)}}), encoding="utf-8"
    )
    kb.load()

    assert kb.get_file("b.md") == "second vault\n"
    assert kb.get_file("a.md") is None


def test_unreadable_file_is_skipped_without_failing_the_whole_load(vault):
    folder, _ = vault
    (folder / "bad.md").write_bytes(b"\xff\xfe\x00 not utf-8 \xff")
    (folder / "good.md").write_text("readable content\n", encoding="utf-8")

    kb = service.KnowledgeBaseService()
    status = kb.load()

    assert status.kb_state == KB_LOADED
    assert status.files_loaded == 1
    assert kb.get_file("good.md") == "readable content\n"
    assert kb.get_file("bad.md") is None


def test_concurrent_load_returns_loading_status_instead_of_racing(vault, monkeypatch):
    folder, _ = vault
    (folder / "a.md").write_text("content\n", encoding="utf-8")

    kb = service.KnowledgeBaseService()
    started = threading.Event()
    release = threading.Event()

    real_find = service.find_markdown_files

    def slow_find(path):
        started.set()
        release.wait(timeout=5)
        return real_find(path)

    monkeypatch.setattr(service, "find_markdown_files", slow_find)

    results: list = []
    first_thread = threading.Thread(target=lambda: results.append(kb.load()))
    first_thread.start()
    assert started.wait(timeout=5)

    second_status = kb.load()
    release.set()
    first_thread.join(timeout=5)

    assert second_status.kb_state == KB_LOADING
    assert results[0].kb_state == KB_LOADED


def test_get_file_not_found_is_none(vault):
    kb = service.KnowledgeBaseService()
    kb.load()
    assert kb.get_file("does-not-exist.md") is None


# --- pure route handlers ------------------------------------------------------


def test_handle_status_always_succeeds():
    kb = service.KnowledgeBaseService()
    status_code, payload = service.handle_status(kb)
    assert status_code == 200
    assert payload["kb_state"] == KB_NOT_LOADED


def test_handle_catalog_before_any_load_is_not_loaded_error():
    kb = service.KnowledgeBaseService()
    status_code, payload = service.handle_catalog(kb)
    assert status_code == 409
    assert payload["error"] == ERROR_KB_NOT_LOADED


def test_handle_catalog_while_loading_for_the_first_time_is_loading_error(vault, monkeypatch):
    folder, _ = vault
    (folder / "a.md").write_text("content\n", encoding="utf-8")
    kb = service.KnowledgeBaseService()

    started = threading.Event()
    release = threading.Event()
    real_find = service.find_markdown_files

    def slow_find(path):
        started.set()
        release.wait(timeout=5)
        return real_find(path)

    monkeypatch.setattr(service, "find_markdown_files", slow_find)

    thread = threading.Thread(target=kb.load)
    thread.start()
    assert started.wait(timeout=5)

    status_code, payload = service.handle_catalog(kb)

    release.set()
    thread.join(timeout=5)

    assert status_code == 409
    assert payload["error"] == ERROR_KB_LOADING


def test_handle_catalog_after_successful_load(vault):
    folder, _ = vault
    (folder / "a.md").write_text("Purpose text.\n", encoding="utf-8")
    kb = service.KnowledgeBaseService()
    kb.load()

    status_code, payload = service.handle_catalog(kb)

    assert status_code == 200
    assert payload[0]["name"] == "a.md"


def test_handle_file_success_and_not_found(vault):
    folder, _ = vault
    (folder / "a.md").write_text("full content\n", encoding="utf-8")
    kb = service.KnowledgeBaseService()
    kb.load()

    ok_code, ok_payload = service.handle_file(kb, "a.md")
    assert ok_code == 200
    assert ok_payload["content"] == "full content\n"

    missing_code, missing_payload = service.handle_file(kb, "missing.md")
    assert missing_code == 404
    assert missing_payload["error"] == ERROR_FILE_NOT_FOUND


def test_handle_file_serves_stale_content_after_a_failed_reload(vault):
    """Per the spec: a failed reload preserves the previous KB, and
    /catalog and /file should keep serving it rather than reporting
    unavailable just because the *last* load attempt failed."""
    folder, cfg_path = vault
    (folder / "a.md").write_text("still here\n", encoding="utf-8")
    kb = service.KnowledgeBaseService()
    kb.load()

    cfg_path.write_text(
        json.dumps({"knowledgeBase": {"obsidianPath": str(folder.parent / "gone")}}),
        encoding="utf-8",
    )
    reload_status = kb.load()
    assert reload_status.kb_state == KB_ERROR

    status_code, payload = service.handle_file(kb, "a.md")
    assert status_code == 200
    assert payload["content"] == "still here\n"
