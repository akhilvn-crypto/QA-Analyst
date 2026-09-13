#!/usr/bin/env bash
# PostToolUse hook for Bash|PowerShell: after
# `orchestrator.generation.docx_report_writer`,
# `orchestrator.generation.test_plan_docx_writer`, or
# `orchestrator.generation.clarification_sheet_writer` runs, renders the
# generated .docx to PDF/JPEG purely to verify it opens and paginates
# cleanly, then deletes the temporary render. Matches both tools -- the
# module-path substring this hook looks for (see below) appears identically
# regardless of which shell tool issued the command.
#
# This is a verification step only. It does not touch formatting -- the
# page/table layout, widths, shading, and header-repeat logic all live in
# the individual writer modules and orchestrator/utils/docx_helpers.py.
#
# This system only ever runs on Windows machines with Microsoft Word
# installed, so rendering goes through Word COM automation (pywin32) rather
# than a portable CLI converter -- no extra install (LibreOffice/poppler)
# required on any machine running this project.
#
# Contract: reads the tool-call JSON from stdin (Claude Code PostToolUse hook
# payload: tool_input.command + tool_response.stdout). No-ops (exit 0) if the
# command wasn't the docx writer, or if any render step fails -- this hook
# must never block the parent command.
#
# Match pattern is on the bare module path (`generation.docx_report_writer`,
# not `orchestrator.generation.docx_report_writer`) -- agents now invoke
# writers via `bash ./.qa-orchestrator generation.docx_report_writer ...`
# (the shim prepends the `orchestrator.` package prefix itself), so the
# literal command text an agent issues never contains `orchestrator.` at all.

set -uo pipefail

input="$(cat)"

command_str="$(printf '%s' "$input" | python -c '
import json, sys
try:
    data = json.load(sys.stdin)
    print(data.get("tool_input", {}).get("command", ""))
except Exception:
    print("")
')"

case "$command_str" in
  *generation.docx_report_writer*|*generation.test_plan_docx_writer*|*generation.clarification_sheet_writer*)
    ;;
  *)
    exit 0
    ;;
esac

docx_path="$(printf '%s' "$input" | python -c '
import json, sys
try:
    data = json.load(sys.stdin)
    out = data.get("tool_response", {}).get("stdout", "") or ""
    lines = [line.strip() for line in out.splitlines() if line.strip().endswith(".docx")]
    print(lines[-1] if lines else "")
except Exception:
    print("")
')"

if [ -z "$docx_path" ] || [ ! -f "$docx_path" ]; then
  python -c '
import json
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": "format-report hook: could not resolve generated .docx path, skipping.",
    }
}))
'
  exit 0
fi

python -c '
import json, sys, os, tempfile, shutil

def _report(message):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": message,
        }
    }))

docx_path = os.path.abspath(sys.argv[1])
tmp_dir = tempfile.mkdtemp(prefix="format-report-")

try:
    import win32com.client as win32
    import fitz

    pdf_path = os.path.join(tmp_dir, "preview.pdf")

    word = win32.gencache.EnsureDispatch("Word.Application")
    word.Visible = False
    try:
        doc = word.Documents.Open(docx_path)
        try:
            doc.SaveAs(pdf_path, FileFormat=17)  # wdFormatPDF
        finally:
            doc.Close(False)
    finally:
        word.Quit()

    if not os.path.isfile(pdf_path):
        _report("format-report hook: Word did not produce a PDF, skipping.")
        sys.exit(0)

    pdf = fitz.open(pdf_path)
    page_count = pdf.page_count
    for i, page in enumerate(pdf):
        page.get_pixmap(dpi=100).save(os.path.join(tmp_dir, f"page-{i + 1}.jpg"))
    pdf.close()

    _report(
        f"format-report hook: rendered {os.path.basename(docx_path)} -> {page_count} page(s), layout verified OK."
    )
except Exception as exc:
    _report(f"format-report hook: render verification skipped ({exc}).")
finally:
    shutil.rmtree(tmp_dir, ignore_errors=True)
' "$docx_path"

exit 0
