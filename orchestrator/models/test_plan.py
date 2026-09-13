"""Shared data structures for test plan generation. No logic lives here."""

from dataclasses import dataclass, field


@dataclass
class DocumentMeta:
    title: str
    project_id: str
    document_id: str
    description: str
    approved_date: str
    master_template_id: str
    prepared_by: str
    prepared_date: str
    version: str


# The Document Release History table has eight columns, so its free-text
# `reasons` cell is only ~1.5in wide. A long reason there does not merely look
# cramped -- it makes a single row taller than the page, which pushes the row's
# text over the footer and squeezes the neighbouring columns until words break
# mid-word. One observed entry ran to 1084 characters and turned a two-row table
# into three pages.
#
# So `reasons` is a one-line summary, not a changelog: name what changed, and
# leave the detail to the sections that actually changed. QA can expand it by
# hand in Word afterwards if a particular revision warrants more.
MAX_RELEASE_REASON_CHARS = 120


@dataclass
class ReleaseHistoryEntry:
    version: str
    date: str
    author: str
    reviewed_by: str
    reviewed_on: str
    approved_by: str
    approved_on: str
    # Short and concise -- see MAX_RELEASE_REASON_CHARS above.
    reasons: str


@dataclass
class ScopeArea:
    area: str
    items: list[str] = field(default_factory=list)
    # Requirement IDs this area covers (JSON-only traceability — not
    # rendered in the docx). Lets validation prove every analyzed
    # requirement landed in scope somewhere.
    req_ids: list[str] = field(default_factory=list)


@dataclass
class ReferenceDocument:
    process_element: str
    reference: str


@dataclass
class Introduction:
    purpose: str
    project_overview: str
    scope_in_areas: list[ScopeArea] = field(default_factory=list)
    scope_in_non_functional: list[str] = field(default_factory=list)
    scope_out: list[str] = field(default_factory=list)
    reference_documents: list[ReferenceDocument] = field(default_factory=list)


@dataclass
class TeamMember:
    resource_name: str
    designation_role: str


@dataclass
class RoleAssignment:
    element: str
    resource_name: str
    designation_role: str


@dataclass
class EnvironmentItem:
    sno: str
    name: str
    purpose: str


@dataclass
class ResourceRequirements:
    team_members: list[TeamMember] = field(default_factory=list)
    role_assignments: list[RoleAssignment] = field(default_factory=list)
    orientation_intro: str = ""
    orientation_topics: list[str] = field(default_factory=list)
    inputs_needed: list[str] = field(default_factory=list)
    environment_software: list[EnvironmentItem] = field(default_factory=list)
    environment_hardware: list[EnvironmentItem] = field(default_factory=list)


@dataclass
class AssumptionsDependenciesRisks:
    assumptions: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)


@dataclass
class IntegrationArea:
    area: str
    items: list[str] = field(default_factory=list)


@dataclass
class TestStrategy:
    overall_strategy: list[str] = field(default_factory=list)
    integration_strategy: list[str] = field(default_factory=list)
    integration_key_areas: list[str] = field(default_factory=list)
    integration_sequence: list[IntegrationArea] = field(default_factory=list)
    entry_criteria: list[str] = field(default_factory=list)
    exit_criteria: list[str] = field(default_factory=list)
    integration_acceptance_criteria: list[str] = field(default_factory=list)


@dataclass
class ScheduleEntry:
    release: str
    sprint: str
    iteration: str
    start_date: str
    end_date: str


@dataclass
class DeliverableDoc:
    document: str
    location: str


@dataclass
class TestDeliverables:
    test_plan_note: str = ""
    test_cases_logs: list[DeliverableDoc] = field(default_factory=list)
    acceptance_exit_note: str = ""
    acceptance_exit_docs: list[DeliverableDoc] = field(default_factory=list)
    bug_analysis_note: str = ""
    bug_analysis_docs: list[DeliverableDoc] = field(default_factory=list)
    release_notes_note: str = ""
    release_notes_docs: list[DeliverableDoc] = field(default_factory=list)
    non_functional_note: str = ""
    non_functional_docs: list[DeliverableDoc] = field(default_factory=list)


@dataclass
class TestClosure:
    sprint_closure_criteria: list[str] = field(default_factory=list)
    release_closure_criteria: list[str] = field(default_factory=list)


def _deliverables_from_dict(data: dict) -> "TestDeliverables":
    return TestDeliverables(
        test_plan_note=data.get("test_plan_note", ""),
        test_cases_logs=[DeliverableDoc(**d) for d in data.get("test_cases_logs", [])],
        acceptance_exit_note=data.get("acceptance_exit_note", ""),
        acceptance_exit_docs=[DeliverableDoc(**d) for d in data.get("acceptance_exit_docs", [])],
        bug_analysis_note=data.get("bug_analysis_note", ""),
        bug_analysis_docs=[DeliverableDoc(**d) for d in data.get("bug_analysis_docs", [])],
        release_notes_note=data.get("release_notes_note", ""),
        release_notes_docs=[DeliverableDoc(**d) for d in data.get("release_notes_docs", [])],
        non_functional_note=data.get("non_functional_note", ""),
        non_functional_docs=[DeliverableDoc(**d) for d in data.get("non_functional_docs", [])],
    )


@dataclass
class TestPlan:
    meta: DocumentMeta
    release_history: list[ReleaseHistoryEntry]
    introduction: Introduction
    resources: ResourceRequirements
    assumptions_dependencies_risks: AssumptionsDependenciesRisks
    strategy: TestStrategy
    schedule: list[ScheduleEntry]
    deliverables: TestDeliverables
    closure: TestClosure

    def to_dict(self) -> dict:
        return {
            "meta": vars(self.meta),
            "release_history": [vars(entry) for entry in self.release_history],
            "introduction": {
                "purpose": self.introduction.purpose,
                "project_overview": self.introduction.project_overview,
                "scope_in_areas": [vars(area) for area in self.introduction.scope_in_areas],
                "scope_in_non_functional": list(self.introduction.scope_in_non_functional),
                "scope_out": list(self.introduction.scope_out),
                "reference_documents": [
                    vars(doc) for doc in self.introduction.reference_documents
                ],
            },
            "resources": {
                "team_members": [vars(m) for m in self.resources.team_members],
                "role_assignments": [vars(r) for r in self.resources.role_assignments],
                "orientation_intro": self.resources.orientation_intro,
                "orientation_topics": list(self.resources.orientation_topics),
                "inputs_needed": list(self.resources.inputs_needed),
                "environment_software": [vars(i) for i in self.resources.environment_software],
                "environment_hardware": [vars(i) for i in self.resources.environment_hardware],
            },
            "assumptions_dependencies_risks": vars(self.assumptions_dependencies_risks),
            "strategy": {
                "overall_strategy": list(self.strategy.overall_strategy),
                "integration_strategy": list(self.strategy.integration_strategy),
                "integration_key_areas": list(self.strategy.integration_key_areas),
                "integration_sequence": [vars(a) for a in self.strategy.integration_sequence],
                "entry_criteria": list(self.strategy.entry_criteria),
                "exit_criteria": list(self.strategy.exit_criteria),
                "integration_acceptance_criteria": list(
                    self.strategy.integration_acceptance_criteria
                ),
            },
            "schedule": [vars(entry) for entry in self.schedule],
            "deliverables": {
                "test_plan_note": self.deliverables.test_plan_note,
                "test_cases_logs": [vars(d) for d in self.deliverables.test_cases_logs],
                "acceptance_exit_note": self.deliverables.acceptance_exit_note,
                "acceptance_exit_docs": [vars(d) for d in self.deliverables.acceptance_exit_docs],
                "bug_analysis_note": self.deliverables.bug_analysis_note,
                "bug_analysis_docs": [vars(d) for d in self.deliverables.bug_analysis_docs],
                "release_notes_note": self.deliverables.release_notes_note,
                "release_notes_docs": [vars(d) for d in self.deliverables.release_notes_docs],
                "non_functional_note": self.deliverables.non_functional_note,
                "non_functional_docs": [vars(d) for d in self.deliverables.non_functional_docs],
            },
            "closure": vars(self.closure),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TestPlan":
        intro = data.get("introduction", {})
        resources = data.get("resources", {})
        strategy = data.get("strategy", {})

        return cls(
            meta=DocumentMeta(**data["meta"]),
            release_history=[
                ReleaseHistoryEntry(**entry) for entry in data.get("release_history", [])
            ],
            introduction=Introduction(
                purpose=intro.get("purpose", ""),
                project_overview=intro.get("project_overview", ""),
                scope_in_areas=[
                    ScopeArea(**area) for area in intro.get("scope_in_areas", [])
                ],
                scope_in_non_functional=list(intro.get("scope_in_non_functional", [])),
                scope_out=list(intro.get("scope_out", [])),
                reference_documents=[
                    ReferenceDocument(**doc) for doc in intro.get("reference_documents", [])
                ],
            ),
            resources=ResourceRequirements(
                team_members=[TeamMember(**m) for m in resources.get("team_members", [])],
                role_assignments=[
                    RoleAssignment(**r) for r in resources.get("role_assignments", [])
                ],
                orientation_intro=resources.get("orientation_intro", ""),
                orientation_topics=list(resources.get("orientation_topics", [])),
                inputs_needed=list(resources.get("inputs_needed", [])),
                environment_software=[
                    EnvironmentItem(**i) for i in resources.get("environment_software", [])
                ],
                environment_hardware=[
                    EnvironmentItem(**i) for i in resources.get("environment_hardware", [])
                ],
            ),
            assumptions_dependencies_risks=AssumptionsDependenciesRisks(
                **data.get("assumptions_dependencies_risks", {})
            ),
            strategy=TestStrategy(
                overall_strategy=list(strategy.get("overall_strategy", [])),
                integration_strategy=list(strategy.get("integration_strategy", [])),
                integration_key_areas=list(strategy.get("integration_key_areas", [])),
                integration_sequence=[
                    IntegrationArea(**a) for a in strategy.get("integration_sequence", [])
                ],
                entry_criteria=list(strategy.get("entry_criteria", [])),
                exit_criteria=list(strategy.get("exit_criteria", [])),
                integration_acceptance_criteria=list(
                    strategy.get("integration_acceptance_criteria", [])
                ),
            ),
            schedule=[ScheduleEntry(**entry) for entry in data.get("schedule", [])],
            deliverables=_deliverables_from_dict(data.get("deliverables", {})),
            closure=TestClosure(**data.get("closure", {})),
        )
