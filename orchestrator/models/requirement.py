"""Shared data structures for requirement analysis. No logic lives here."""

from dataclasses import dataclass, field

# The Document Release History table has eight columns, so its free-text
# `reasons` cell is only ~1.5in wide -- identical constraint to
# orchestrator/models/test_plan.py's own MAX_RELEASE_REASON_CHARS (and
# orchestrator/models/test_case.py's copy of the same constant), and for the
# same reason. Kept as its own constant here rather than imported from
# either so the three deliverables' models stay independent of each other.
MAX_RELEASE_REASON_CHARS = 120


@dataclass
class DocumentControlMeta:
    """Controlled-document identification fields for the analysis report's
    Document Version Control section — mirrors DocumentMeta in
    orchestrator/models/test_plan.py and DocumentControlMeta in
    orchestrator/models/test_case.py's shape (a requirement analysis is
    just as much an ISO-audit-relevant controlled document as those two)."""

    title: str = ""
    project_id: str = ""
    document_id: str = ""
    description: str = ""
    prepared_by: str = ""
    prepared_date: str = ""
    approved_date: str = ""
    master_template_id: str = ""
    version: str = ""
    # Document sensitivity label shown on the analysis report's Document
    # Control & Metadata section (e.g. "Internal / Highly Confidential").
    # Empty (never invented) until the agent has a real value to put here.
    classification: str = ""

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "project_id": self.project_id,
            "document_id": self.document_id,
            "description": self.description,
            "prepared_by": self.prepared_by,
            "prepared_date": self.prepared_date,
            "approved_date": self.approved_date,
            "master_template_id": self.master_template_id,
            "version": self.version,
            "classification": self.classification,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DocumentControlMeta":
        return cls(
            title=data.get("title", ""),
            project_id=data.get("project_id", ""),
            document_id=data.get("document_id", ""),
            description=data.get("description", ""),
            prepared_by=data.get("prepared_by", ""),
            prepared_date=data.get("prepared_date", ""),
            approved_date=data.get("approved_date", ""),
            master_template_id=data.get("master_template_id", ""),
            version=data.get("version", ""),
            classification=data.get("classification", ""),
        )


@dataclass
class ReleaseHistoryEntry:
    """One formal sign-off record for the Document Release History section
    — same eight fields as orchestrator/models/test_plan.py's and
    orchestrator/models/test_case.py's own ReleaseHistoryEntry. Distinct
    from AnalysisMeta.changelog: `changelog` is the informal content-delta
    narrative already used internally by validation/regeneration;
    `release_history` is the audit-facing sign-off table (who authored/
    reviewed/approved each version)."""

    version: str
    date: str
    author: str
    reviewed_by: str
    reviewed_on: str
    approved_by: str
    approved_on: str
    # Short and concise -- see MAX_RELEASE_REASON_CHARS above.
    reasons: str

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "date": self.date,
            "author": self.author,
            "reviewed_by": self.reviewed_by,
            "reviewed_on": self.reviewed_on,
            "approved_by": self.approved_by,
            "approved_on": self.approved_on,
            "reasons": self.reasons,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ReleaseHistoryEntry":
        return cls(
            version=data.get("version", ""),
            date=data.get("date", ""),
            author=data.get("author", ""),
            reviewed_by=data.get("reviewed_by", ""),
            reviewed_on=data.get("reviewed_on", ""),
            approved_by=data.get("approved_by", ""),
            approved_on=data.get("approved_on", ""),
            reasons=data.get("reasons", ""),
        )


@dataclass
class Gap:
    description: str
    question: str
    blocking: bool = False
    # Verbatim, character-for-character quote of the passage in the
    # originating vault note (Requirement.source_file) this gap's ambiguity
    # was drawn from -- the anchor /apply-clarifications' vault write-back
    # uses to locate and rewrite that passage in place once the client
    # answers it. Empty for a gap about literally *absent* information (a
    # "missing information" gap has no text to quote/anchor to) -- such a
    # gap's answer only ever lands in the JSON/clarification_log, never an
    # in-place note edit. Never paraphrased -- it must literal-match later.
    source_excerpt: str = ""


@dataclass
class Recommendation:
    recommendation: str
    reason: str
    business_benefit: str
    client_confirmation_recommended: bool = False


@dataclass
class Requirement:
    req_id: str
    requirement_text: str
    acceptance_criteria_status: str
    acceptance_criteria: str
    # Structured facts lifted from the source document when it states them
    # (user-story ID / row reference, MoSCoW or similar priority, sprint or
    # phase tag). Empty string when the document doesn't state one — never
    # invented.
    source_ref: str = ""
    priority: str = ""
    sprint_or_phase: str = ""
    # Vault-relative path (from the enclosing `## Source: <relative path>`
    # heading in the staged combined document) this requirement was
    # extracted from -- e.g. "Checkout/Payment.md". Empty string when
    # unknown (a legacy analysis JSON predating this field, or a requirement
    # whose extraction genuinely can't be pinned to one file). This is what
    # lets /apply-clarifications' vault write-back find the right note to
    # edit in place; it plays no other role in analysis or reporting.
    source_file: str = ""
    # Short, plain-English label for this requirement (a few words, e.g.
    # "Initial Login Interface") shown next to req_id as the card heading in
    # both reports. Empty string falls back to showing the bare req_id — a
    # legacy analysis JSON predating this field reads back fine.
    title: str = ""
    # Which numbered report section this requirement is grouped under:
    # "Functional" (default — a client-stated business requirement),
    # "Non-Functional" (an NFR the requirement set addresses — performance,
    # compatibility, usability, etc.), or "Compliance" (a regulatory/
    # compliance consideration the inferred domain implicates). See the
    # requirement-analysis-framework skill's NFR analysis / Compliance
    # analysis sections for how these are derived. A legacy analysis JSON
    # predating this field reads back as "Functional" for every requirement.
    category: str = "Functional"
    gaps: list[Gap] = field(default_factory=list)
    recommendations: list[Recommendation] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    related_to: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "req_id": self.req_id,
            "requirement_text": self.requirement_text,
            "acceptance_criteria_status": self.acceptance_criteria_status,
            "acceptance_criteria": self.acceptance_criteria,
            "source_ref": self.source_ref,
            "priority": self.priority,
            "sprint_or_phase": self.sprint_or_phase,
            "source_file": self.source_file,
            "title": self.title,
            "category": self.category,
            "gaps": [
                {
                    "description": gap.description,
                    "question": gap.question,
                    "blocking": gap.blocking,
                    "source_excerpt": gap.source_excerpt,
                }
                for gap in self.gaps
            ],
            "recommendations": [
                {
                    "recommendation": rec.recommendation,
                    "reason": rec.reason,
                    "business_benefit": rec.business_benefit,
                    "client_confirmation_recommended": rec.client_confirmation_recommended,
                }
                for rec in self.recommendations
            ],
            "depends_on": list(self.depends_on),
            "related_to": list(self.related_to),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Requirement":
        return cls(
            req_id=data["req_id"],
            requirement_text=data["requirement_text"],
            acceptance_criteria_status=data["acceptance_criteria_status"],
            acceptance_criteria=data["acceptance_criteria"],
            source_ref=data.get("source_ref", ""),
            priority=data.get("priority", ""),
            sprint_or_phase=data.get("sprint_or_phase", ""),
            source_file=data.get("source_file", ""),
            title=data.get("title", ""),
            category=data.get("category", "Functional") or "Functional",
            gaps=[Gap(**gap) for gap in data.get("gaps", [])],
            recommendations=[
                Recommendation(**rec) for rec in data.get("recommendations", [])
            ],
            depends_on=list(data.get("depends_on", [])),
            related_to=list(data.get("related_to", [])),
        )


@dataclass
class AnalysisMeta:
    """Document-level facts about one analysis run — the domain inference,
    extraction manifest, and revision history that per-requirement rows
    can't carry."""

    source_doc: str
    domain: str = ""
    domain_evidence: str = ""
    version: str = "1.0"
    generated_date: str = ""
    # e.g. {"sheets_processed": [...], "rows_seen": 65,
    #       "requirements_extracted": 63, "skipped": ["Cover sheet — no requirements"]}
    extraction_manifest: dict = field(default_factory=dict)
    # [{"version": "1.0", "date": "...", "changes": "Initial analysis."}, ...]
    changelog: list = field(default_factory=list)
    # [{"req_id": "...", "question": "...", "answer": "...", "date": "..."}, ...]
    clarification_log: list = field(default_factory=list)
    # Document-level, cross-cutting narrative (plain text, may hold its own
    # numbered/labeled sub-points the same way a Requirement's own
    # `acceptance_criteria` does) written by the requirement-analyzer agent,
    # not derived mechanically -- which non-functional-requirement categories
    # (performance, security, usability, accessibility, compatibility,
    # reliability, ...) this document actually addresses, which REQ-IDs cover
    # each, and which expected categories the document is silent on. Empty
    # until the agent populates it; never fabricated -- see the
    # requirement-analysis-framework skill's NFR analysis section.
    nfr_analysis: str = ""
    # Same shape and authorship as nfr_analysis: which compliance/regulatory
    # standards the inferred domain plausibly implicates (e.g. WCAG for
    # accessibility, PCI-DSS for payment handling, GDPR/HIPAA for personal or
    # health data), whether the document actually addresses them, and where
    # it's silent. States "Not Applicable"/TBD explicitly rather than
    # inventing an obligation the domain doesn't support.
    # Legacy note: nfr_analysis/compliance_analysis are no longer rendered as
    # their own narrative paragraphs in the report (see the report's "Non-
    # Functional Requirements (NFR) Analysis" / "Compliance & Regulatory
    # Requirements Analysis" sections, now built from individual
    # `Requirement` entries whose `category` is "Non-Functional"/
    # "Compliance" instead). Both fields are kept for backward compatibility
    # with analysis JSON written before that change — a legacy file with
    # narrative text here but no categorized requirements still reads back
    # and validates.
    compliance_analysis: str = ""
    # Document-level narrative for the report's "Project Overview & Scope"
    # section — a short executive summary of what the analyzed document
    # covers, written the same way acceptance_criteria/nfr_analysis are:
    # plain prose, never fabricated, "TBD – To be added by QA" until the
    # agent populates it.
    executive_summary: str = ""
    # What the analyzed document states is in scope / out of scope for this
    # project, in the client's own terms where possible — same authorship
    # convention as executive_summary above.
    in_scope: str = ""
    out_of_scope: str = ""

    def to_dict(self) -> dict:
        return {
            "source_doc": self.source_doc,
            "domain": self.domain,
            "domain_evidence": self.domain_evidence,
            "version": self.version,
            "generated_date": self.generated_date,
            "extraction_manifest": dict(self.extraction_manifest),
            "changelog": list(self.changelog),
            "clarification_log": list(self.clarification_log),
            "nfr_analysis": self.nfr_analysis,
            "compliance_analysis": self.compliance_analysis,
            "executive_summary": self.executive_summary,
            "in_scope": self.in_scope,
            "out_of_scope": self.out_of_scope,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AnalysisMeta":
        return cls(
            source_doc=data.get("source_doc", ""),
            domain=data.get("domain", ""),
            domain_evidence=data.get("domain_evidence", ""),
            version=data.get("version", "1.0"),
            generated_date=data.get("generated_date", ""),
            extraction_manifest=dict(data.get("extraction_manifest", {})),
            changelog=list(data.get("changelog", [])),
            clarification_log=list(data.get("clarification_log", [])),
            nfr_analysis=data.get("nfr_analysis", ""),
            compliance_analysis=data.get("compliance_analysis", ""),
            executive_summary=data.get("executive_summary", ""),
            in_scope=data.get("in_scope", ""),
            out_of_scope=data.get("out_of_scope", ""),
        )


@dataclass
class AnalysisDocument:
    """The full *-analysis.json payload: meta block + requirement list +
    the controlled-document fields.

    Accepts both shapes: the current `{"meta": ..., "requirements": [...]}`
    and the legacy bare list of requirements (meta defaults, `legacy` True).

    `document_control`/`release_history` default to empty — a file written
    before these fields existed reads back fine (legacy shape, the same
    tolerance a pre-`meta` bare list already gets); the next analysis run
    populates them for real.
    """

    meta: AnalysisMeta
    requirements: list[Requirement]
    legacy: bool = False
    document_control: DocumentControlMeta = field(default_factory=DocumentControlMeta)
    release_history: list[ReleaseHistoryEntry] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "meta": self.meta.to_dict(),
            "requirements": [req.to_dict() for req in self.requirements],
            "document_control": self.document_control.to_dict(),
            "release_history": [entry.to_dict() for entry in self.release_history],
        }

    @classmethod
    def from_any(cls, data) -> "AnalysisDocument":
        if isinstance(data, list):
            return cls(
                meta=AnalysisMeta(source_doc="", version=""),
                requirements=[Requirement.from_dict(item) for item in data],
                legacy=True,
            )
        return cls(
            meta=AnalysisMeta.from_dict(data.get("meta", {})),
            requirements=[
                Requirement.from_dict(item) for item in data.get("requirements", [])
            ],
            document_control=DocumentControlMeta.from_dict(data.get("document_control", {})),
            release_history=[
                ReleaseHistoryEntry.from_dict(item) for item in data.get("release_history", [])
            ],
        )
