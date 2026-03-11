from dataclasses import dataclass, field
from typing import Optional
from models.VueElement import VueElement
from models.RobotLocator import RobotLocator


# ─── Çapraz Analiz ──────────────────────────────────────────────

@dataclass
class MatchResult:
    locator: RobotLocator
    matched_element: Optional[VueElement] = None
    match_confidence: float = 0.0
    is_broken: bool = False
    is_risky: bool = False
    break_reason: Optional[str] = None


@dataclass
class CrossAnalysisResult:
    matches: list = field(default_factory=list)
    broken: list = field(default_factory=list)
    risky: list = field(default_factory=list)
    healthy: list = field(default_factory=list)
    unmatched_vue: list = field(default_factory=list)
    summary: dict = field(default_factory=dict)


# ─── Audit ──────────────────────────────────────────────────────

@dataclass
class AuditIssue:
    severity: str           # "critical" | "warning" | "info"
    element: VueElement
    message: str
    suggestion: str
    suggested_data_test: Optional[str] = None


@dataclass
class AuditReport:
    total_elements: int = 0
    total_interactive: int = 0
    covered: int = 0
    issues: list = field(default_factory=list)
    files_scanned: int = 0
    coverage_percent: float = 0.0

    @property
    def missing_count(self) -> int:
        return self.total_interactive - self.covered

    @property
    def critical_issues(self) -> list:
        return [i for i in self.issues if i.severity == "critical"]

    @property
    def warning_issues(self) -> list:
        return [i for i in self.issues if i.severity == "warning"]

    def by_file(self) -> dict:
        result = {}
        for issue in self.issues:
            result.setdefault(issue.element.file, []).append(issue)
        return result


# ─── Vue Diff ───────────────────────────────────────────────────

@dataclass
class ElementChange:
    change_type: str            # "removed" | "renamed" | "added"
    selector_type: str          # "data-test" | "id"
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    old_element: Optional[VueElement] = None
    new_element: Optional[VueElement] = None
    affected_locators: list = field(default_factory=list)


@dataclass
class VueDiffResult:
    removed: list = field(default_factory=list)
    renamed: list = field(default_factory=list)
    added: list = field(default_factory=list)
    affected_robot_locators: list = field(default_factory=list)
    summary: dict = field(default_factory=dict)


# ─── Heal ───────────────────────────────────────────────────────

@dataclass
class HealSuggestion:
    locator: RobotLocator
    original_value: str
    suggested_value: str
    suggested_type: str
    confidence: str             # "high" | "medium" | "low"
    confidence_score: float
    reason: str
    patch_ready: bool = False
    vue_element_hint: Optional[str] = None


@dataclass
class PatchFile:
    robot_file: str
    original_line: int
    original_content: str
    patched_content: str
    suggestion: HealSuggestion


@dataclass
class HealReport:
    suggestions: list = field(default_factory=list)
    patch_files: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    @property
    def high_confidence(self) -> list:
        return [s for s in self.suggestions if s.confidence == "high"]

    @property
    def medium_confidence(self) -> list:
        return [s for s in self.suggestions if s.confidence == "medium"]

    @property
    def low_confidence(self) -> list:
        return [s for s in self.suggestions if s.confidence == "low"]
