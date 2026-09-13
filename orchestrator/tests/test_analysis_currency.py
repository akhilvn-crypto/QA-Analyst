"""Tests for the requirement-analyzer's no-op guard -- whether a full/delta
re-analysis run has anything to do, decided purely from mtimes so it never
requires reading (or reasoning over) the requirement content itself."""

import json
import os

from orchestrator.validation import analysis_currency


def _touch(path, *, after=None):
    path.write_text("x", encoding="utf-8")
    if after is not None:
        newer = os.path.getmtime(after) + 1
        os.utime(path, (newer, newer))


def test_changed_when_no_prior_analysis(tmp_path, monkeypatch):
    json_path = tmp_path / "Doc-analysis.json"
    source_path = tmp_path / "Doc-source.md"
    source_path.write_text("x", encoding="utf-8")

    monkeypatch.setattr(analysis_currency, "analysis_json_path", lambda doc: json_path)
    monkeypatch.setattr(analysis_currency, "requirement_source_md_path", lambda doc: source_path)

    changed, message = analysis_currency.check("Doc")

    assert changed is True
    assert "first analysis" in message


def test_changed_when_source_newer_than_analysis(tmp_path, monkeypatch):
    json_path = tmp_path / "Doc-analysis.json"
    source_path = tmp_path / "Doc-source.md"
    json_path.write_text(json.dumps({"meta": {"version": "1.0"}}), encoding="utf-8")
    _touch(source_path, after=json_path)

    monkeypatch.setattr(analysis_currency, "analysis_json_path", lambda doc: json_path)
    monkeypatch.setattr(analysis_currency, "requirement_source_md_path", lambda doc: source_path)

    changed, message = analysis_currency.check("Doc")

    assert changed is True
    assert "newer" in message


def test_unchanged_when_analysis_already_current(tmp_path, monkeypatch):
    source_path = tmp_path / "Doc-source.md"
    json_path = tmp_path / "Doc-analysis.json"
    source_path.write_text("x", encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {
                "meta": {"version": "2.0"},
                "document_control": {"prepared_date": "2026-08-10"},
            }
        ),
        encoding="utf-8",
    )
    newer = os.path.getmtime(source_path) + 1
    os.utime(json_path, (newer, newer))

    monkeypatch.setattr(analysis_currency, "analysis_json_path", lambda doc: json_path)
    monkeypatch.setattr(analysis_currency, "requirement_source_md_path", lambda doc: source_path)

    changed, message = analysis_currency.check("Doc")

    assert changed is False
    assert "version 2.0" in message
    assert "2026-08-10" in message


def test_changed_when_source_missing(tmp_path, monkeypatch):
    json_path = tmp_path / "Doc-analysis.json"
    source_path = tmp_path / "Doc-source.md"
    json_path.write_text(json.dumps({"meta": {"version": "1.0"}}), encoding="utf-8")

    monkeypatch.setattr(analysis_currency, "analysis_json_path", lambda doc: json_path)
    monkeypatch.setattr(analysis_currency, "requirement_source_md_path", lambda doc: source_path)

    changed, message = analysis_currency.check("Doc")

    assert changed is True
    assert "no staged source" in message
