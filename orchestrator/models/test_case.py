"""Shared data structures for test-case generation. No logic lives here."""

from dataclasses import dataclass, field

# Priority is derived from the requirement's stated `priority` field (MoSCoW /
# P1-P4 / etc. — see skills/test-case-generation-framework/SKILL.md's
# Priority derivation section). There is no `overall_risk` field anywhere in
# this codebase — risk ratings were retired from the requirement-analyzer's
# output (see .claude/rules/output-structure.md) — so Priority is derived
# from stated priority, not re-deriving a retired risk score.
VALID_PRIORITIES = ("High", "Medium", "Low")

# Not a closed list enforced as an error — domain reasoning may surface a
# type this list doesn't anticipate — but these are the ones the framework
# skill actively asks for, so anything else is worth a validation warning.
# See skills/test-case-generation-framework/SKILL.md's "How many
# test cases a requirement needs" section for exactly when each applies —
# Integration/Security/Database/API are conditional ("if applicable"), never
# padded onto a requirement that doesn't genuinely call for them.
KNOWN_TEST_TYPES = (
    "Positive",
    "Negative",
    "Boundary",
    "Edge",
    "Permission",
    "Integration",
    "Security",
    "Database",
    "API",
)


@dataclass
class TestStep:
    step_number: int
    action: str
    expected_result: str
    test_data: str = ""

    def to_dict(self) -> dict:
        return {
            "step_number": self.step_number,
            "action": self.action,
            "expected_result": self.expected_result,
            "test_data": self.test_data,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TestStep":
        return cls(
            step_number=data["step_number"],
            action=data["action"],
            expected_result=data["expected_result"],
            test_data=data.get("test_data", ""),
        )


@dataclass
class TestCase:
    tc_id: str
    req_id: str
    title: str
    objective: str
    test_type: str
    priority: str
    preconditions: str = ""
    steps: list[TestStep] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "tc_id": self.tc_id,
            "req_id": self.req_id,
            "title": self.title,
            "objective": self.objective,
            "test_type": self.test_type,
            "priority": self.priority,
            "preconditions": self.preconditions,
            "steps": [step.to_dict() for step in self.steps],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TestCase":
        return cls(
            tc_id=data["tc_id"],
            req_id=data["req_id"],
            title=data["title"],
            objective=data.get("objective", ""),
            test_type=data.get("test_type", ""),
            priority=data.get("priority", ""),
            preconditions=data.get("preconditions", ""),
            steps=[TestStep.from_dict(step) for step in data.get("steps", [])],
        )


# The Document Release History table has eight columns, so its free-text
# `reasons` cell is only ~1.5in wide -- identical constraint to
# orchestrator/models/test_plan.py's own MAX_RELEASE_REASON_CHARS, and for
# the same reason (a long value there makes the row taller than the page and
# squeezes the other columns into mid-word breaks). Kept as its own constant
# here rather than imported from test_plan.py so the two deliverables' models
# stay independent of each other.
MAX_RELEASE_REASON_CHARS = 120


@dataclass
class DocumentControlMeta:
    """Controlled-document identification fields for the test-case
    workbook's Document Version Control sheet — mirrors DocumentMeta in
    orchestrator/models/test_plan.py's shape (a test-case suite is just as
    much an ISO-audit-relevant controlled document as the Test Plan).
    `version` mirrors TestCaseMeta.version; kept as its own field here (not
    a shared reference) because DocumentControlMeta/ReleaseHistoryEntry can
    be entirely absent on a legacy (pre-controlled-document) file while
    TestCaseMeta.version always exists."""

    title: str = ""
    project_id: str = ""
    document_id: str = ""
    description: str = ""
    prepared_by: str = ""
    prepared_date: str = ""
    approved_date: str = ""
    master_template_id: str = ""
    version: str = ""

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
        )


@dataclass
class ReleaseHistoryEntry:
    """One formal sign-off record for the Document Release History sheet —
    same eight fields as orchestrator/models/test_plan.py's own
    ReleaseHistoryEntry. Distinct from TestCaseMeta.changelog: `changelog`
    is the informal content-delta narrative already used internally by
    validation/regeneration; `release_history` is the audit-facing
    sign-off table (who authored/reviewed/approved each version)."""

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
class NotCoveredEntry:
    """A requirement deliberately skipped instead of having test cases
    fabricated for it — always because Acceptance Criteria weren't
    generated for it (blocked on a client clarification), never a silent
    omission."""

    req_id: str
    reason: str

    def to_dict(self) -> dict:
        return {"req_id": self.req_id, "reason": self.reason}

    @classmethod
    def from_dict(cls, data: dict) -> "NotCoveredEntry":
        return cls(req_id=data["req_id"], reason=data.get("reason", ""))


@dataclass
class TestCaseMeta:
    """Document-level facts about one test-case generation run. No `project`
    field -- a plugin install is exactly one project, so there's nothing
    left to name here (same as every other deliverable's own meta)."""

    source_doc: str
    version: str = "1.0"
    generated_date: str = ""
    # [{"version": "1.0", "date": "...", "changes": "Initial generation."}, ...]
    changelog: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "source_doc": self.source_doc,
            "version": self.version,
            "generated_date": self.generated_date,
            "changelog": list(self.changelog),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TestCaseMeta":
        return cls(
            source_doc=data.get("source_doc", ""),
            version=data.get("version", "1.0"),
            generated_date=data.get("generated_date", ""),
            changelog=list(data.get("changelog", [])),
        )


@dataclass
class TestCaseDocument:
    """The full *-test-cases.json payload: meta block + test case list +
    the Not Covered summary + the controlled-document fields.

    `document_control`/`release_history` default to empty — a file written
    before these fields existed reads back fine (legacy shape, same
    tolerance the analysis JSON gives a pre-meta bare list); the next
    regeneration populates them for real."""

    meta: TestCaseMeta
    test_cases: list[TestCase]
    not_covered: list[NotCoveredEntry] = field(default_factory=list)
    document_control: DocumentControlMeta = field(default_factory=DocumentControlMeta)
    release_history: list[ReleaseHistoryEntry] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "meta": self.meta.to_dict(),
            "test_cases": [tc.to_dict() for tc in self.test_cases],
            "not_covered": [entry.to_dict() for entry in self.not_covered],
            "document_control": self.document_control.to_dict(),
            "release_history": [entry.to_dict() for entry in self.release_history],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TestCaseDocument":
        return cls(
            meta=TestCaseMeta.from_dict(data.get("meta", {})),
            test_cases=[TestCase.from_dict(item) for item in data.get("test_cases", [])],
            not_covered=[
                NotCoveredEntry.from_dict(item) for item in data.get("not_covered", [])
            ],
            document_control=DocumentControlMeta.from_dict(data.get("document_control", {})),
            release_history=[
                ReleaseHistoryEntry.from_dict(item) for item in data.get("release_history", [])
            ],
        )
