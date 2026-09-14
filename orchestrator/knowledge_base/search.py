"""Direct-from-markdown search over the attached folder's `Requirements/`
subfolder -- the per-requirement reasoning fallback, with no vector store
in the middle. (The general domain-background source, `Knowledge Base/`,
is a different, unrelated mechanism -- see `knowledge_base.catalog`: a
deterministic catalog an agent scans, then reads a chosen file's complete
content directly with `Read`. There is nothing to search there; ranked,
excerpted sections are specifically this module's own answer to
`Requirements/` being read for a single, often-vague doubt, not a whole
file worth reading in full.)

There used to be a Chroma DB here: notes were chunked, embedded, and
upserted into collections by a separate manual `/sync-knowledge-base` pass,
then queried by cosine distance. That was removed. Embedding a note is a
lossy summary of it, and a nearest-neighbour hit is only ever
*approximately* about what was asked -- which showed up as confidently-cited
snippets that weren't the passage that actually answered the question. This
module reads the `.md` files themselves, every time, so what an agent gets
back is the client's own words at their real path, and there is no index to
keep in sync with the notes it describes.

    python -m orchestrator.knowledge_base.search "<query>" [--folder <name>] [--max-chars N]
    python -m orchestrator.knowledge_base.search --list [--folder <name>]

`--folder` is an exact top-level folder name to search instead of matching
`Requirements` by convention -- for a client vault that names it something
else entirely (see `orchestrator.utils.workspace`'s folder-auto-detection
note). Not cached anywhere; supply it again on every call that needs it.

`search` prints a JSON list of `{source_file, path, heading_path, text,
truncated, score, matched_terms}`, best first -- `text` is the section's real
markdown, not a reconstruction. A section over `--max-chars` comes back as a
match-centred excerpt of itself (still verbatim, `[...]` where something was
dropped) with `truncated: true`; everything else comes back whole.

`--list` prints every note with its size and heading outline. That plus the
`path` on every result is the escape hatch when an excerpt isn't enough: an
agent reads the named file directly with its own `Read` tool and gets the
whole thing, exactly as written.

A missing subfolder or simply no match both print `[]` and exit 0. A
missing `Requirements/` note isn't itself a gap -- the caller falls back to
the requirement text alone.
"""

import argparse
import json
import re
import sys
from pathlib import Path

from orchestrator.utils import workspace

_SKIP_DIR_NAMES = {"node_modules"}

# Per-result ceiling on how much of a section is printed. A section under it
# comes back whole, which is the common case for a well-structured note. Past
# it, `_excerpt` keeps the parts the query actually landed on and flags the
# result `truncated` -- a note with no `#` headings at all is a single
# section spanning the entire file, and answering one question with 30 KB of
# a pasted PRD buries the answer rather than giving it.
DEFAULT_MAX_CHARS = 4000

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_WORD_RE = re.compile(r"[a-z0-9][a-z0-9_'\-]*")

# Words too common to say anything about relevance. Deliberately short and
# English-only: this is a tie-breaker for ranking sections a human reads
# anyway, not a linguistic model, and every term dropped here is one an
# agent's query could otherwise have scored a whole vault on.
_STOPWORDS = frozenset(
    """a an and are as at be but by can could do does for from has have how if in into is it
    its may might must no not of on or should so some such than that the their then there these
    they this to was we what when where which who why will with would you your""".split()
)


def _tokenize(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def _query_terms(query: str) -> list[str]:
    """The query's distinct content words, in order. Falls back to the raw
    tokens when every one of them is a stopword -- a query like "what is
    this" should still match something rather than silently match nothing."""
    tokens = _tokenize(query)
    terms = [t for t in dict.fromkeys(tokens) if t not in _STOPWORDS and len(t) > 1]
    return terms or list(dict.fromkeys(tokens))


def find_markdown_files(folder: Path) -> list[Path]:
    """Every `.md` file under `folder`, skipping dot-directories
    (`.obsidian`, `.git`, and this project's own `.history` snapshots) and
    `node_modules` -- housekeeping, never notes. Same rule
    `parsing.reading_vault_fetch` applies to the same folders."""
    return sorted(
        path
        for path in folder.rglob("*.md")
        if path.is_file()
        and not any(
            part.startswith(".") or part in _SKIP_DIR_NAMES
            for part in path.relative_to(folder).parts[:-1]
        )
    )


def split_sections(text: str) -> list[dict]:
    """Split one note into heading-scoped sections, each carrying the full
    heading trail that leads to it (e.g. "Domain Rules > KYC > Session
    Expiry").

    A section is a heading plus everything under it up to the next heading
    of the same or shallower depth -- so a section never straddles two
    unrelated topics, and quoting one quotes something a human actually
    wrote as a unit. Content before a note's first heading forms its own
    section with an empty trail; a note with no headings at all is one
    section, which is common and fine.

    Sections come back whole here, however long they are -- the old chunker
    split them to fit an embedding window, and there isn't one anymore. Any
    bounding happens later, at the point of printing, in `_excerpt`.
    """
    sections: list[dict] = []
    trail: list[tuple[int, str]] = []  # (depth, title) for the open headings
    current: dict | None = None

    for line in text.splitlines():
        match = _HEADING_RE.match(line)
        if not match:
            if current is None:
                current = {"heading_path": "", "text": ""}
            current["text"] += line + "\n"
            continue

        if current is not None:
            sections.append(current)
        depth, title = len(match.group(1)), match.group(2).strip()
        while trail and trail[-1][0] >= depth:
            trail.pop()
        trail.append((depth, title))
        current = {"heading_path": " > ".join(t for _, t in trail), "text": line + "\n"}

    if current is not None:
        sections.append(current)

    for section in sections:
        section["text"] = section["text"].strip()
    return [s for s in sections if s["text"]]


def _score(section: dict, terms: list[str]) -> tuple[float, list[str]]:
    """How well one section answers `terms`, and which terms it actually hit.

    Three signals, in the order they deserve trust: how many of the query's
    distinct terms appear at all (breadth -- a section mentioning every term
    once beats one repeating a single term ten times), how often (frequency,
    capped per term so a long section can't win on bulk alone), and whether
    the match landed in the heading trail rather than the body (a section
    *titled* "Session Expiry" is about session expiry; one that mentions it
    in passing may not be).
    """
    heading_tokens = set(_tokenize(section["heading_path"]))
    body_tokens = _tokenize(section["text"])
    if not body_tokens:
        return 0.0, []

    counts: dict[str, int] = {}
    for token in body_tokens:
        counts[token] = counts.get(token, 0) + 1

    matched = [t for t in terms if counts.get(t) or t in heading_tokens]
    if not matched:
        return 0.0, []

    coverage = len(matched) / len(terms)
    frequency = sum(min(counts.get(t, 0), 4) for t in matched) / len(body_tokens)
    heading_hits = sum(1 for t in terms if t in heading_tokens) / len(terms)

    return round((coverage * 10.0) + (frequency * 5.0) + (heading_hits * 3.0), 4), matched


def _excerpt(text: str, terms: list[str], max_chars: int) -> tuple[str, bool]:
    """`text` if it fits in `max_chars`, otherwise the parts of it the query
    actually landed on. Returns `(text, was_excerpted)`.

    Sections stay whole wherever they can -- that's the point of splitting on
    headings. But a note written without any `#` headings at all is one
    section covering the whole file, and plenty of real notes are exactly
    that (a Word export, a pasted PRD). Printing 30 KB of it to answer one
    question buries the answer instead of giving it.

    So when a section is oversized, keep the lines that matched plus the two
    lines either side of each, in document order, joined by `[...]` where
    something was dropped. Every character still comes verbatim from the
    note, and the result carries `truncated: true` and the note's `path`, so
    a caller that needs the rest reads the file itself.
    """
    if max_chars <= 0 or len(text) <= max_chars:
        return text, False

    lines = text.splitlines()
    wanted: set[int] = set()
    for i, line in enumerate(lines):
        tokens = set(_tokenize(line))
        if any(term in tokens for term in terms):
            wanted.update(range(max(0, i - 2), min(len(lines), i + 3)))

    if not wanted:  # matched only via the heading trail -- lead with the top
        return text[:max_chars].rstrip(), True

    separator = "\n\n[...]\n\n"
    parts: list[str] = []
    # Reserve room for the leading/trailing elision markers up front so the
    # finished excerpt honours `max_chars` rather than overshooting it.
    budget = max(1, max_chars - 2 * len("\n\n[...]"))
    block: list[str] = []
    previous = None
    for i in sorted(wanted):
        if previous is not None and i != previous + 1:
            parts.append("\n".join(block))
            block = []
        block.append(lines[i])
        previous = i
    if block:
        parts.append("\n".join(block))

    kept: list[str] = []
    for part in parts:
        cost = len(part) + (len(separator) if kept else 0)
        if cost > budget:
            break
        kept.append(part)
        budget -= cost

    if not kept:  # a single matched line longer than the whole budget
        return parts[0][:max_chars].rstrip(), True

    # Mark every elision, including the ones at the edges: an excerpt that
    # silently starts mid-note reads like the note starts there, and a
    # caller quoting it would misrepresent what the client actually wrote.
    ordered = sorted(wanted)
    excerpt = separator.join(kept)
    if ordered[0] > 0:
        excerpt = "[...]\n\n" + excerpt
    if len(kept) < len(parts) or ordered[-1] < len(lines) - 1:
        excerpt = excerpt + "\n\n[...]"
    return excerpt.strip(), True


def _resolve_folder(folder_override: str | None) -> Path | None:
    folder = workspace.requirements_path(folder_override) if folder_override else workspace.requirements_path()
    if folder is None or not folder.is_dir():
        return None
    return folder


def search(
    query: str,
    folder_override: str | None = None,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> list[dict]:
    """Every matching note section for `query`, best first -- no cap. A
    ranked cutoff (this used to take a `top_k`, configured via
    `knowledgeBase.topK`) silently drops whatever scored just past it, which
    is exactly the wrong failure mode for a search an agent falls back to
    precisely because it's genuinely unsure: better to hand back everything
    that matched and let the agent judge relevance itself (as every caller
    already does per-result) than to guess how many results are "enough" and
    hide the rest.

    Each result carries the section's own markdown (`text`), where it came
    from (`source_file` relative to `Requirements/`, `path` absolute), and
    whether what's shown is the whole section or a match-centred excerpt of
    an oversized one (`truncated`). `max_chars` caps each result's `text`;
    pass `0` for no cap.

    Returns `[]` -- never raises -- when `Requirements/` (or the given
    `folder_override`) doesn't exist, or nothing matches. Both mean the same
    thing to a caller: there is no knowledge-base answer here, reason from
    the requirement text instead.
    """
    folder = _resolve_folder(folder_override)
    if folder is None:
        return []

    terms = _query_terms(query)
    if not terms:
        return []

    scored: list[dict] = []
    for md_file in find_markdown_files(folder):
        try:
            text = md_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue  # unreadable note -- skip it, don't fail the whole search

        rel_path = md_file.relative_to(folder).as_posix()
        for section in split_sections(text):
            score, matched = _score(section, terms)
            if score <= 0:
                continue
            body, truncated = _excerpt(section["text"], matched, max_chars)
            scored.append(
                {
                    "source_file": rel_path,
                    "path": str(md_file),
                    "heading_path": section["heading_path"],
                    "text": body,
                    "truncated": truncated,
                    "score": score,
                    "matched_terms": matched,
                }
            )

    # Ties break on path then heading so two runs over unchanged notes always
    # return the same order -- an agent citing "[source: X]" should not get a
    # different X for the same question.
    scored.sort(key=lambda s: (-s["score"], s["source_file"], s["heading_path"]))
    return scored


def list_notes(folder_override: str | None = None) -> list[dict]:
    """Every note under `Requirements/` (or `folder_override`), with its
    size and heading outline -- the map an agent uses to decide which file
    to `Read` in full when a searched section isn't enough. `[]` when the
    folder isn't configured."""
    folder = _resolve_folder(folder_override)
    if folder is None:
        return []

    notes = []
    for md_file in find_markdown_files(folder):
        try:
            text = md_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        notes.append(
            {
                "source_file": md_file.relative_to(folder).as_posix(),
                "path": str(md_file),
                "chars": len(text),
                "headings": [s["heading_path"] for s in split_sections(text) if s["heading_path"]],
            }
        )
    return notes


def _use_utf8_stdout() -> None:
    """Print UTF-8 whatever the console claims to be.

    This module is the one that echoes arbitrary client-authored note text
    back to a caller, verbatim -- a single `->` or a smart quote in someone's
    vault is enough to crash `print` on a Windows console defaulting to
    cp1252, and crashing on the *content* of a note is never the right
    answer. `errors="replace"` keeps a stray unencodable character from
    taking down a whole result set on the rare terminal that can't be
    reconfigured at all.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass  # already-wrapped or non-reconfigurable stream -- print anyway


def main() -> None:
    _use_utf8_stdout()
    parser = argparse.ArgumentParser(
        prog="python -m orchestrator.knowledge_base.search",
        description="Search this project's configured markdown notes directly, no index involved.",
    )
    parser.add_argument("query", nargs="?", default=None)
    parser.add_argument(
        "--folder",
        default=None,
        help=(
            "Exact top-level folder name to search instead of matching 'Requirements' by "
            "convention -- for a client vault that names it something else entirely."
        ),
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=DEFAULT_MAX_CHARS,
        help=(
            "Per-result ceiling on printed section text; an oversized section comes back as a "
            f"match-centred excerpt flagged `truncated`. 0 disables. Default {DEFAULT_MAX_CHARS}."
        ),
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_notes",
        help="List every note with its size and heading outline instead of searching.",
    )
    args = parser.parse_args()

    if args.list_notes:
        result = list_notes(folder_override=args.folder)
    elif args.query:
        result = search(args.query, folder_override=args.folder, max_chars=args.max_chars)
    else:
        parser.error("a query is required unless --list is passed")
        return

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
