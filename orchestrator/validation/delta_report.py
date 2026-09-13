"""Advisory change report for delta re-analysis.

Usage:
    python -m orchestrator.validation.delta_report <doc-name>

Compares the *existing* analysis JSON (the previous run's requirements)
against the *current* combined requirement markdown staged by
`parsing.reading_vault_fetch`, and reports — per requirement — whether it
still appears in the document:

- "matched"        — its source_ref appears in the new document, or its text
                     is found near-verbatim. Strong signal it's unchanged.
- "likely_changed" — partially found; the wording around it has moved.
- "missing"        — neither its source_ref nor similar text was found.
                     Candidate for removal in this revision.

Plus `unmatched_source_refs`: requirement-ID-like tokens (e.g. US-031)
present in the new document but absent from the previous analysis —
candidates for newly added requirements.

This is an **advisory** signal for the requirement-analyzer agent's delta
step, not a gate: extraction legitimately rewords document text, so fuzzy
scores guide attention — the agent still judges. source_ref matches are the
reliable anchor; text-similarity fallback is best-effort.
"""

import json
import re
import sys
from difflib import SequenceMatcher

from orchestrator.models.requirement import AnalysisDocument
from orchestrator.utils.io_helpers import read_json
from orchestrator.utils.paths import analysis_json_path, requirement_source_md_path

_MATCHED = 0.75
_LIKELY_CHANGED = 0.45

# Tokens that look like a document's own requirement/story IDs (US-001,
# REQ_12, FR-3.2, ...). Deliberately excludes this system's REQ-### IDs when
# scanning the *document*, since those are ours, not the document's.
_SOURCE_REF = re.compile(r"\b[A-Z]{2,4}[-_]\d+(?:\.\d+)?\b")


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", text.lower())).strip()


def _best_similarity(needle: str, haystack_lines: list[str]) -> float:
    """Best fuzzy match of `needle` against any document line (both
    normalized; needle truncated to keep this cheap)."""
    needle = _normalize(needle)[:300]
    if not needle:
        return 0.0
    best = 0.0
    for line in haystack_lines:
        score = SequenceMatcher(None, needle, line[:300]).ratio()
        if score > best:
            best = score
            if best >= 0.98:
                break
    return best


def build_report(doc_name: str) -> dict:
    json_path = analysis_json_path(doc_name)
    if not json_path.exists():
        raise FileNotFoundError(
            f"No previous analysis at {json_path} — nothing to delta against; "
            "this is a first analysis."
        )
    md_path = requirement_source_md_path(doc_name)
    if not md_path.exists():
        raise FileNotFoundError(
            f"Combined requirement source not found: {md_path} — run "
            "`parsing.reading_vault_fetch` first."
        )

    analysis = AnalysisDocument.from_any(read_json(json_path))
    md_text = md_path.read_text(encoding="utf-8")
    md_lines = [
        _normalize(line) for line in md_text.splitlines() if line.strip()
    ]

    doc_refs = set(_SOURCE_REF.findall(md_text))
    known_refs = {
        req.source_ref for req in analysis.requirements if req.source_ref
    }

    entries = []
    for req in analysis.requirements:
        ref_found = bool(req.source_ref) and req.source_ref in doc_refs
        score = _best_similarity(req.requirement_text, md_lines)

        if ref_found or score >= _MATCHED:
            status = "matched"
        elif score >= _LIKELY_CHANGED:
            status = "likely_changed"
        else:
            status = "missing"

        entries.append(
            {
                "req_id": req.req_id,
                "source_ref": req.source_ref,
                "source_ref_found": ref_found,
                "text_similarity": round(score, 2),
                "status": status,
            }
        )

    unmatched_refs = sorted(ref for ref in doc_refs if ref not in known_refs)

    return {
        "previous_version": analysis.meta.version or ("legacy" if analysis.legacy else ""),
        "requirements": entries,
        "unmatched_source_refs": unmatched_refs,
        "note": (
            "Advisory only: source_ref matches are reliable; text similarity is "
            "best-effort (extraction rewords). 'matched' requirements are "
            "carry-forward candidates; 'missing' are removal candidates; "
            "unmatched_source_refs are likely new requirements. Judge each."
        ),
    }


def main() -> None:
    if len(sys.argv) != 2:
        print(
            "Usage: python -m orchestrator.validation.delta_report <doc-name>",
            file=sys.stderr,
        )
        sys.exit(1)

    _, doc_name = sys.argv
    try:
        report = build_report(doc_name)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
