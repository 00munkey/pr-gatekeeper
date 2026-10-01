import sqlite3
from pr_gatekeeper.models import Finding, TestResult, GateVerdict, ReportSummary

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pr_number INTEGER NOT NULL,
    repo TEXT NOT NULL,
    status TEXT NOT NULL,
    reason TEXT NOT NULL,
    tests_ran INTEGER NOT NULL,
    tests_passed INTEGER NOT NULL,
    duration_s REAL NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(id),
    repo TEXT NOT NULL,
    file TEXT NOT NULL,
    severity TEXT NOT NULL,
    description TEXT NOT NULL
);
"""


class MemoryStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        conn = sqlite3.connect(self.db_path)
        conn.executescript(SCHEMA)
        conn.commit()
        conn.close()

    def record_run(
        self,
        pr_number: int,
        repo: str,
        verdict: GateVerdict,
        findings: list[Finding],
        test_result: TestResult,
        duration_s: float,
    ) -> None:
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute(
            "INSERT INTO runs (pr_number, repo, status, reason, tests_ran, tests_passed, duration_s) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (pr_number, repo, verdict.status, verdict.reason, int(test_result.ran), int(test_result.passed), duration_s),
        )
        run_id = cur.lastrowid
        for f in findings:
            conn.execute(
                "INSERT INTO findings (run_id, repo, file, severity, description) VALUES (?, ?, ?, ?, ?)",
                (run_id, repo, f.file, f.severity, f.description),
            )
        conn.commit()
        conn.close()

    def past_findings_for_file(self, repo: str, file: str) -> list[Finding]:
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT file, severity, description FROM findings WHERE repo = ? AND file = ?",
            (repo, file),
        ).fetchall()
        conn.close()
        return [Finding(file=r[0], severity=r[1], description=r[2]) for r in rows]

    def report(self) -> ReportSummary:
        conn = sqlite3.connect(self.db_path)
        total, blocked, warned, clear, avg_dur = conn.execute(
            "SELECT COUNT(*), "
            "SUM(CASE WHEN status = 'blocked' THEN 1 ELSE 0 END), "
            "SUM(CASE WHEN status = 'warned' THEN 1 ELSE 0 END), "
            "SUM(CASE WHEN status = 'clear' THEN 1 ELSE 0 END), "
            "AVG(duration_s) FROM runs"
        ).fetchone()
        total_findings = conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
        conn.close()
        return ReportSummary(
            total_runs=total or 0,
            blocked_count=blocked or 0,
            warned_count=warned or 0,
            clear_count=clear or 0,
            avg_duration_s=avg_dur or 0.0,
            total_findings=total_findings or 0,
        )
