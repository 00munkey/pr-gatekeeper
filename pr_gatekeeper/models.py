from dataclasses import dataclass

@dataclass(frozen=True)
class Finding:
    file: str
    severity: str  # "high" | "low"
    description: str

@dataclass(frozen=True)
class TestResult:
    __test__ = False  # stop pytest from trying to collect this as a test class
    ran: bool
    passed: bool
    output: str

@dataclass(frozen=True)
class GateVerdict:
    status: str  # "blocked" | "warned" | "clear"
    reason: str

@dataclass(frozen=True)
class PRInfo:
    repo: str
    number: int
    diff: str
    changed_files: list[str]
    head_ref: str
    head_sha: str

@dataclass(frozen=True)
class ReportSummary:
    total_runs: int
    blocked_count: int
    warned_count: int
    clear_count: int
    avg_duration_s: float
    total_findings: int
