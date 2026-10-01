# pr-gatekeeper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Python CLI that reviews a real GitHub PR with a security-focused Claude subagent, gates on a deterministic `pytest` run (not an LLM's opinion), remembers findings across runs in SQLite, and posts a verdict comment back to the PR.

**Architecture:** Six small modules, each independently testable: `gate.py` (pure decision logic), `memory_store.py` (SQLite), `github_client.py` (GitHub REST API), `test_runner.py` (checkout + pytest), `security_agent.py` (Anthropic API tool-use loop), wired together by `orchestrator.py` and exposed via the `review.py` CLI.

**Tech Stack:** Python 3.11+, stdlib `sqlite3`, `requests` (GitHub REST API — no PyGithub dependency), `anthropic` Python SDK used at the raw `messages.create` + tool-use level (no Agent SDK), stdlib `argparse` and `subprocess`.

**Spec:** `docs/superpowers/specs/2026-09-30-pr-gatekeeper-design.md`

## Global Constraints

- Python 3.11+ (dataclasses with `|` unions, `tomllib` not needed but keeps the floor simple).
- Two secrets only, both read from environment variables, never hardcoded or logged: `GITHUB_TOKEN`, `ANTHROPIC_API_KEY`.
- No auto-merge anywhere in the code — the gate only ever reports a verdict; a human merges.
- Fail closed: any upstream failure (GitHub API, Anthropic API, checkout/test execution) must resolve to a `blocked` verdict with a reason distinguishing *why* it's blocked — never silently treated as `clear`.
- No GitHub Action/webhook in this plan — CLI only (`python review.py --pr <url>` and `python review.py --report`).

## Review Focus

- A PR whose diff touches no Python files (e.g. only a README) — the security agent must still run and return an empty-or-minimal finding set without crashing on an "empty" diff. (Task 6)
- An invalid or inaccessible PR URL (404, private repo without access, malformed URL) — must exit non-zero with a clear message and must NOT post any comment claiming a computed verdict. (Task 4)
- The demo repo's test environment can't run `pytest` at all (missing dependency, broken venv) — `test_runner` must report this as `ran=False` ("tests could not run"), distinct from `ran=True, passed=False` ("tests failed"). (Task 5)
- The Anthropic API returns output that isn't the expected JSON findings array (truncated, prose instead of JSON, refusal) — `security_agent` must treat this as "security review could not complete" (→ blocked), never silently parse it as zero findings. (Task 6)
- The same PR number is reviewed twice (re-run after a fix) — `memory_store` must append a new run record rather than overwrite the first, so `--report` and recurrence lookups stay accurate across history. (Task 3)

---

### Task 1: Project scaffolding and shared models

**Files:**
- Create: `pyproject.toml`
- Create: `requirements.txt`
- Create: `pr_gatekeeper/__init__.py`
- Create: `pr_gatekeeper/models.py`
- Create: `tests/__init__.py`
- Create: `tests/test_models.py`
- Create: `.gitignore`
- Create: `.env.example`

**Interfaces:**
- Produces: `Finding(file: str, severity: str, description: str)`, `TestResult(ran: bool, passed: bool, output: str)`, `GateVerdict(status: str, reason: str)`, `PRInfo(repo: str, number: int, diff: str, changed_files: list[str], head_ref: str, head_sha: str)`, `ReportSummary(total_runs: int, blocked_count: int, warned_count: int, clear_count: int, avg_duration_s: float, total_findings: int)` — all as `@dataclass(frozen=True)` in `pr_gatekeeper/models.py`.

- [ ] **Step 1: Write the failing test for the dataclasses**

```python
# tests/test_models.py
from pr_gatekeeper.models import Finding, TestResult, GateVerdict, PRInfo, ReportSummary

def test_finding_is_frozen_dataclass():
    f = Finding(file="app.py", severity="high", description="hardcoded secret")
    assert f.file == "app.py"
    assert f.severity == "high"

def test_test_result_distinguishes_ran_from_passed():
    not_run = TestResult(ran=False, passed=False, output="checkout failed")
    ran_but_failed = TestResult(ran=True, passed=False, output="1 failed")
    assert not_run.ran is False
    assert ran_but_failed.ran is True and ran_but_failed.passed is False

def test_gate_verdict_has_status_and_reason():
    v = GateVerdict(status="blocked", reason="high-severity finding")
    assert v.status == "blocked"

def test_pr_info_fields():
    pr = PRInfo(repo="brandonalexander/demo", number=3, diff="diff", changed_files=["a.py"], head_ref="fix-3", head_sha="abc123")
    assert pr.number == 3

def test_report_summary_fields():
    r = ReportSummary(total_runs=5, blocked_count=1, warned_count=1, clear_count=3, avg_duration_s=2.5, total_findings=4)
    assert r.total_runs == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pr_gatekeeper'`

- [ ] **Step 3: Write the implementation**

```python
# pr_gatekeeper/models.py
from dataclasses import dataclass

@dataclass(frozen=True)
class Finding:
    file: str
    severity: str  # "high" | "low"
    description: str

@dataclass(frozen=True)
class TestResult:
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
```

```python
# pr_gatekeeper/__init__.py
```

```toml
# pyproject.toml
[project]
name = "pr-gatekeeper"
version = "0.1.0"
requires-python = ">=3.11"
```

```
# requirements.txt
requests>=2.31
anthropic>=0.40
pytest>=8.0
```

```
# .gitignore
.pr-gatekeeper/
*.db
.env
__pycache__/
*.pyc
.venv/
```

```
# .env.example
GITHUB_TOKEN=
ANTHROPIC_API_KEY=
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_models.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml requirements.txt pr_gatekeeper/ tests/ .gitignore .env.example
git commit -m "chore: project scaffolding and shared dataclasses"
```

---

### Task 2: Gate decision logic

**Files:**
- Create: `pr_gatekeeper/gate.py`
- Test: `tests/test_gate.py`

**Interfaces:**
- Consumes: `Finding`, `TestResult`, `GateVerdict` from `pr_gatekeeper.models` (Task 1)
- Produces: `decide(findings: list[Finding], test_result: TestResult) -> GateVerdict`

- [ ] **Step 1: Write the failing tests (all four branches + the Review Focus distinction)**

```python
# tests/test_gate.py
from pr_gatekeeper.gate import decide
from pr_gatekeeper.models import Finding, TestResult

def test_tests_not_run_blocks():
    result = decide([], TestResult(ran=False, passed=False, output="checkout failed"))
    assert result.status == "blocked"
    assert "could not run" in result.reason

def test_tests_failed_blocks():
    result = decide([], TestResult(ran=True, passed=False, output="1 failed, 4 passed"))
    assert result.status == "blocked"
    assert "failed" in result.reason

def test_high_severity_finding_blocks_even_if_tests_pass():
    findings = [Finding(file="app.py", severity="high", description="SQL injection")]
    result = decide(findings, TestResult(ran=True, passed=True, output="5 passed"))
    assert result.status == "blocked"
    assert "high-severity" in result.reason

def test_low_severity_finding_warns_not_blocks():
    findings = [Finding(file="app.py", severity="low", description="unused import")]
    result = decide(findings, TestResult(ran=True, passed=True, output="5 passed"))
    assert result.status == "warned"

def test_no_findings_and_tests_pass_is_clear():
    result = decide([], TestResult(ran=True, passed=True, output="5 passed"))
    assert result.status == "clear"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_gate.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pr_gatekeeper.gate'`

- [ ] **Step 3: Write the implementation**

```python
# pr_gatekeeper/gate.py
from pr_gatekeeper.models import Finding, TestResult, GateVerdict


def decide(findings: list[Finding], test_result: TestResult) -> GateVerdict:
    if not test_result.ran:
        return GateVerdict(status="blocked", reason=f"tests could not run: {test_result.output}")

    if not test_result.passed:
        return GateVerdict(status="blocked", reason=f"tests failed: {test_result.output}")

    high_severity = [f for f in findings if f.severity == "high"]
    if high_severity:
        names = ", ".join(f.file for f in high_severity)
        return GateVerdict(status="blocked", reason=f"high-severity finding(s) in: {names}")

    if findings:
        return GateVerdict(status="warned", reason=f"{len(findings)} low-severity finding(s)")

    return GateVerdict(status="clear", reason="no findings, tests passed")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_gate.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add pr_gatekeeper/gate.py tests/test_gate.py
git commit -m "feat: deterministic gate decision logic"
```

---

### Task 3: Memory store (SQLite)

**Files:**
- Create: `pr_gatekeeper/memory_store.py`
- Test: `tests/test_memory_store.py`

**Interfaces:**
- Consumes: `Finding`, `TestResult`, `GateVerdict`, `ReportSummary` from `pr_gatekeeper.models` (Task 1)
- Produces: `MemoryStore(db_path: str)` with methods `record_run(pr_number: int, repo: str, verdict: GateVerdict, findings: list[Finding], test_result: TestResult, duration_s: float) -> None`, `past_findings_for_file(repo: str, file: str) -> list[Finding]`, `report() -> ReportSummary`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_memory_store.py
import tempfile
import os
from pr_gatekeeper.memory_store import MemoryStore
from pr_gatekeeper.models import Finding, TestResult, GateVerdict


def make_store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    return MemoryStore(path)


def test_record_run_then_report_counts_it():
    store = make_store()
    verdict = GateVerdict(status="clear", reason="no findings, tests passed")
    test_result = TestResult(ran=True, passed=True, output="5 passed")
    store.record_run(pr_number=1, repo="brandonalexander/demo", verdict=verdict, findings=[], test_result=test_result, duration_s=1.5)

    report = store.report()
    assert report.total_runs == 1
    assert report.clear_count == 1
    assert report.blocked_count == 0


def test_repeated_run_for_same_pr_appends_not_overwrites():
    store = make_store()
    v1 = GateVerdict(status="blocked", reason="tests failed")
    v2 = GateVerdict(status="clear", reason="no findings, tests passed")
    tr = TestResult(ran=True, passed=False, output="1 failed")
    tr2 = TestResult(ran=True, passed=True, output="5 passed")

    store.record_run(pr_number=3, repo="brandonalexander/demo", verdict=v1, findings=[], test_result=tr, duration_s=1.0)
    store.record_run(pr_number=3, repo="brandonalexander/demo", verdict=v2, findings=[], test_result=tr2, duration_s=1.0)

    report = store.report()
    assert report.total_runs == 2
    assert report.blocked_count == 1
    assert report.clear_count == 1


def test_past_findings_for_file_returns_prior_findings():
    store = make_store()
    finding = Finding(file="app.py", severity="high", description="hardcoded secret")
    verdict = GateVerdict(status="blocked", reason="high-severity finding(s) in: app.py")
    test_result = TestResult(ran=True, passed=True, output="5 passed")
    store.record_run(pr_number=1, repo="brandonalexander/demo", verdict=verdict, findings=[finding], test_result=test_result, duration_s=1.0)

    past = store.past_findings_for_file(repo="brandonalexander/demo", file="app.py")
    assert len(past) == 1
    assert past[0].description == "hardcoded secret"


def test_report_on_empty_store_has_zero_runs():
    store = make_store()
    report = store.report()
    assert report.total_runs == 0
    assert report.avg_duration_s == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_memory_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pr_gatekeeper.memory_store'`

- [ ] **Step 3: Write the implementation**

```python
# pr_gatekeeper/memory_store.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_memory_store.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add pr_gatekeeper/memory_store.py tests/test_memory_store.py
git commit -m "feat: SQLite memory store for run history and findings"
```

---

### Task 4: GitHub client

**Files:**
- Create: `pr_gatekeeper/github_client.py`
- Test: `tests/test_github_client.py`

**Interfaces:**
- Consumes: `PRInfo` from `pr_gatekeeper.models` (Task 1)
- Produces: `GitHubClient(token: str)` with methods `fetch_pr(pr_url: str) -> PRInfo`, `read_file_at_ref(repo: str, path: str, ref: str) -> str`, `post_comment(repo: str, pr_number: int, body: str) -> None`. Raises `GitHubClientError(message: str)` (defined in this file) on any API failure or an unparseable `pr_url` — never returns a partially-filled `PRInfo`.

- [ ] **Step 1: Write the failing tests (mocked HTTP, including the Review Focus invalid-URL case)**

```python
# tests/test_github_client.py
import pytest
from unittest.mock import patch, MagicMock
from pr_gatekeeper.github_client import GitHubClient, GitHubClientError


def test_fetch_pr_parses_pr_info():
    client = GitHubClient(token="fake-token")
    pr_json = {"number": 7, "head": {"ref": "fix-7", "sha": "abc123"}}
    files_json = [{"filename": "app.py"}, {"filename": "tests/test_app.py"}]

    with patch("pr_gatekeeper.github_client.requests.get") as mock_get:
        pr_resp = MagicMock(status_code=200)
        pr_resp.json.return_value = pr_json
        files_resp = MagicMock(status_code=200)
        files_resp.json.return_value = files_json
        diff_resp = MagicMock(status_code=200, text="diff --git a/app.py b/app.py")
        mock_get.side_effect = [pr_resp, files_resp, diff_resp]

        pr_info = client.fetch_pr("https://github.com/brandonalexander/demo/pull/7")

    assert pr_info.repo == "brandonalexander/demo"
    assert pr_info.number == 7
    assert pr_info.head_ref == "fix-7"
    assert pr_info.head_sha == "abc123"
    assert pr_info.changed_files == ["app.py", "tests/test_app.py"]
    assert "diff --git" in pr_info.diff


def test_fetch_pr_rejects_malformed_url():
    client = GitHubClient(token="fake-token")
    with pytest.raises(GitHubClientError, match="not a valid GitHub PR URL"):
        client.fetch_pr("https://example.com/not-a-pr")


def test_fetch_pr_raises_on_404():
    client = GitHubClient(token="fake-token")
    with patch("pr_gatekeeper.github_client.requests.get") as mock_get:
        resp = MagicMock(status_code=404, text="Not Found")
        mock_get.return_value = resp
        with pytest.raises(GitHubClientError, match="404"):
            client.fetch_pr("https://github.com/brandonalexander/demo/pull/999")


def test_post_comment_sends_expected_payload():
    client = GitHubClient(token="fake-token")
    with patch("pr_gatekeeper.github_client.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=201)
        client.post_comment(repo="brandonalexander/demo", pr_number=7, body="verdict: clear")

    args, kwargs = mock_post.call_args
    assert "issues/7/comments" in args[0]
    assert kwargs["json"]["body"] == "verdict: clear"


def test_read_file_at_ref_decodes_base64_content():
    client = GitHubClient(token="fake-token")
    import base64
    encoded = base64.b64encode(b"print('hello')").decode()
    with patch("pr_gatekeeper.github_client.requests.get") as mock_get:
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"content": encoded, "encoding": "base64"}
        mock_get.return_value = resp
        content = client.read_file_at_ref(repo="brandonalexander/demo", path="app.py", ref="abc123")
    assert content == "print('hello')"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_github_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pr_gatekeeper.github_client'`

- [ ] **Step 3: Write the implementation**

```python
# pr_gatekeeper/github_client.py
import base64
import re
import requests
from pr_gatekeeper.models import PRInfo

PR_URL_RE = re.compile(r"github\.com/([^/]+/[^/]+)/pull/(\d+)")


class GitHubClientError(Exception):
    pass


class GitHubClient:
    def __init__(self, token: str):
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }

    def _parse_pr_url(self, pr_url: str) -> tuple[str, int]:
        match = PR_URL_RE.search(pr_url)
        if not match:
            raise GitHubClientError(f"'{pr_url}' is not a valid GitHub PR URL")
        return match.group(1), int(match.group(2))

    def fetch_pr(self, pr_url: str) -> PRInfo:
        repo, number = self._parse_pr_url(pr_url)

        pr_resp = requests.get(f"https://api.github.com/repos/{repo}/pulls/{number}", headers=self.headers)
        if pr_resp.status_code != 200:
            raise GitHubClientError(f"GitHub API returned {pr_resp.status_code} fetching PR #{number}: {pr_resp.text}")
        pr_json = pr_resp.json()

        files_resp = requests.get(f"https://api.github.com/repos/{repo}/pulls/{number}/files", headers=self.headers)
        if files_resp.status_code != 200:
            raise GitHubClientError(f"GitHub API returned {files_resp.status_code} fetching changed files")
        changed_files = [f["filename"] for f in files_resp.json()]

        diff_headers = dict(self.headers, Accept="application/vnd.github.v3.diff")
        diff_resp = requests.get(f"https://api.github.com/repos/{repo}/pulls/{number}", headers=diff_headers)
        if diff_resp.status_code != 200:
            raise GitHubClientError(f"GitHub API returned {diff_resp.status_code} fetching diff")

        return PRInfo(
            repo=repo,
            number=number,
            diff=diff_resp.text,
            changed_files=changed_files,
            head_ref=pr_json["head"]["ref"],
            head_sha=pr_json["head"]["sha"],
        )

    def read_file_at_ref(self, repo: str, path: str, ref: str) -> str:
        resp = requests.get(
            f"https://api.github.com/repos/{repo}/contents/{path}",
            headers=self.headers,
            params={"ref": ref},
        )
        if resp.status_code != 200:
            raise GitHubClientError(f"GitHub API returned {resp.status_code} reading {path}@{ref}")
        body = resp.json()
        return base64.b64decode(body["content"]).decode("utf-8")

    def post_comment(self, repo: str, pr_number: int, body: str) -> None:
        resp = requests.post(
            f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments",
            headers=self.headers,
            json={"body": body},
        )
        if resp.status_code != 201:
            raise GitHubClientError(f"GitHub API returned {resp.status_code} posting comment: {resp.text}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_github_client.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add pr_gatekeeper/github_client.py tests/test_github_client.py
git commit -m "feat: GitHub REST API client for PR fetch, file read, and comments"
```

---

### Task 5: Test runner (checkout + pytest)

**Files:**
- Create: `pr_gatekeeper/test_runner.py`
- Test: `tests/test_test_runner.py`

**Interfaces:**
- Consumes: `TestResult` from `pr_gatekeeper.models` (Task 1)
- Produces: `run_tests(repo: str, ref: str, github_token: str) -> TestResult`

- [ ] **Step 1: Write the failing tests (mocked subprocess/clone, including the Review Focus "ran=False" case)**

```python
# tests/test_test_runner.py
from unittest.mock import patch, MagicMock
from pr_gatekeeper.test_runner import run_tests


def test_successful_checkout_and_passing_tests():
    with patch("pr_gatekeeper.test_runner.subprocess.run") as mock_run:
        clone_result = MagicMock(returncode=0, stdout="", stderr="")
        pytest_result = MagicMock(returncode=0, stdout="5 passed", stderr="")
        mock_run.side_effect = [clone_result, pytest_result]

        result = run_tests(repo="brandonalexander/demo", ref="fix-7", github_token="fake-token")

    assert result.ran is True
    assert result.passed is True
    assert "5 passed" in result.output


def test_successful_checkout_but_failing_tests():
    with patch("pr_gatekeeper.test_runner.subprocess.run") as mock_run:
        clone_result = MagicMock(returncode=0, stdout="", stderr="")
        pytest_result = MagicMock(returncode=1, stdout="1 failed, 4 passed", stderr="")
        mock_run.side_effect = [clone_result, pytest_result]

        result = run_tests(repo="brandonalexander/demo", ref="fix-7", github_token="fake-token")

    assert result.ran is True
    assert result.passed is False
    assert "1 failed" in result.output


def test_checkout_failure_means_tests_did_not_run():
    with patch("pr_gatekeeper.test_runner.subprocess.run") as mock_run:
        clone_result = MagicMock(returncode=128, stdout="", stderr="fatal: could not clone")
        mock_run.side_effect = [clone_result]

        result = run_tests(repo="brandonalexander/demo", ref="nonexistent-branch", github_token="fake-token")

    assert result.ran is False
    assert result.passed is False
    assert "could not clone" in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_test_runner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pr_gatekeeper.test_runner'`

- [ ] **Step 3: Write the implementation**

```python
# pr_gatekeeper/test_runner.py
import subprocess
import tempfile
from pr_gatekeeper.models import TestResult


def run_tests(repo: str, ref: str, github_token: str) -> TestResult:
    with tempfile.TemporaryDirectory() as tmpdir:
        clone_url = f"https://{github_token}@github.com/{repo}.git"
        clone = subprocess.run(
            ["git", "clone", "--branch", ref, "--depth", "1", clone_url, tmpdir],
            capture_output=True,
            text=True,
        )
        if clone.returncode != 0:
            return TestResult(ran=False, passed=False, output=clone.stderr.strip())

        pytest_run = subprocess.run(
            ["pytest", "-v"],
            cwd=tmpdir,
            capture_output=True,
            text=True,
        )
        output = (pytest_run.stdout + pytest_run.stderr).strip()
        return TestResult(ran=True, passed=pytest_run.returncode == 0, output=output)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_test_runner.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add pr_gatekeeper/test_runner.py tests/test_test_runner.py
git commit -m "feat: deterministic test runner via checkout + pytest"
```

---

### Task 6: Security agent (Anthropic API tool-use loop)

**Files:**
- Create: `pr_gatekeeper/security_agent.py`
- Test: `tests/test_security_agent.py`

**Interfaces:**
- Consumes: `PRInfo`, `Finding` from `pr_gatekeeper.models` (Task 1); `GitHubClient.read_file_at_ref` from `pr_gatekeeper.github_client` (Task 4)
- Produces: `SecurityAgent(api_key: str, github_client: GitHubClient)` with method `review(pr_info: PRInfo) -> list[Finding]`. On any API failure or unparseable model output, raises `SecurityAgentError(message: str)` (defined in this file) — callers (Task 7) must treat this as "could not complete," not as zero findings.

- [ ] **Step 1: Write the failing tests (mocked Anthropic client, including the two Review Focus cases: empty-diff and malformed-output)**

```python
# tests/test_security_agent.py
import json
from unittest.mock import MagicMock
from pr_gatekeeper.security_agent import SecurityAgent, SecurityAgentError
from pr_gatekeeper.models import PRInfo


def make_pr_info(diff="diff --git a/app.py b/app.py\n+SECRET = 'abc123'"):
    return PRInfo(repo="brandonalexander/demo", number=1, diff=diff, changed_files=["app.py"], head_ref="fix-1", head_sha="abc")


def test_review_returns_findings_from_final_text_block():
    agent = SecurityAgent(api_key="fake-key", github_client=MagicMock())
    final_message = MagicMock()
    final_message.content = [MagicMock(type="text", text=json.dumps([
        {"file": "app.py", "severity": "high", "description": "hardcoded secret"}
    ]))]
    agent.client = MagicMock()
    agent.client.messages.create.return_value = final_message

    findings = agent.review(make_pr_info())

    assert len(findings) == 1
    assert findings[0].severity == "high"
    assert findings[0].file == "app.py"


def test_review_on_non_python_only_diff_returns_empty_list_without_crashing():
    agent = SecurityAgent(api_key="fake-key", github_client=MagicMock())
    final_message = MagicMock()
    final_message.content = [MagicMock(type="text", text="[]")]
    agent.client = MagicMock()
    agent.client.messages.create.return_value = final_message

    findings = agent.review(make_pr_info(diff="diff --git a/README.md b/README.md\n+docs update"))

    assert findings == []


def test_review_raises_on_malformed_model_output():
    agent = SecurityAgent(api_key="fake-key", github_client=MagicMock())
    final_message = MagicMock()
    final_message.content = [MagicMock(type="text", text="I think this looks fine, no issues!")]
    agent.client = MagicMock()
    agent.client.messages.create.return_value = final_message

    try:
        agent.review(make_pr_info())
        assert False, "expected SecurityAgentError"
    except SecurityAgentError as e:
        assert "could not parse" in str(e)


def test_review_raises_on_api_error():
    agent = SecurityAgent(api_key="fake-key", github_client=MagicMock())
    agent.client = MagicMock()
    agent.client.messages.create.side_effect = Exception("rate limited")

    try:
        agent.review(make_pr_info())
        assert False, "expected SecurityAgentError"
    except SecurityAgentError as e:
        assert "rate limited" in str(e)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_security_agent.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pr_gatekeeper.security_agent'`

- [ ] **Step 3: Write the implementation**

```python
# pr_gatekeeper/security_agent.py
import json
import anthropic
from pr_gatekeeper.models import PRInfo, Finding

SYSTEM_PROMPT = """You are a security reviewer for a pull request. You will be given a unified diff.
Identify security issues only (e.g. hardcoded secrets, injection vulnerabilities, unsafe deserialization,
missing auth checks). Ignore style, performance, and non-security correctness issues.

Respond with ONLY a JSON array of findings, no other text. Each finding is an object with keys:
"file" (string), "severity" ("high" or "low"), "description" (string).
If there are no security issues, respond with exactly: []
"""


class SecurityAgentError(Exception):
    pass


class SecurityAgent:
    def __init__(self, api_key: str, github_client):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.github_client = github_client

    def review(self, pr_info: PRInfo) -> list[Finding]:
        try:
            message = self.client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": f"Diff for PR #{pr_info.number} in {pr_info.repo}:\n\n{pr_info.diff}"}],
            )
        except Exception as e:
            raise SecurityAgentError(f"Anthropic API call failed: {e}")

        text_blocks = [block.text for block in message.content if block.type == "text"]
        raw_text = "\n".join(text_blocks).strip()

        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError:
            raise SecurityAgentError(f"could not parse model output as JSON findings: {raw_text!r}")

        if not isinstance(parsed, list):
            raise SecurityAgentError(f"could not parse model output as a JSON array: {raw_text!r}")

        findings = []
        for item in parsed:
            try:
                findings.append(Finding(file=item["file"], severity=item["severity"], description=item["description"]))
            except (KeyError, TypeError):
                raise SecurityAgentError(f"could not parse finding item: {item!r}")

        return findings
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_security_agent.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add pr_gatekeeper/security_agent.py tests/test_security_agent.py
git commit -m "feat: security review subagent via raw Anthropic API call"
```

---

### Task 7: Orchestrator and CLI

**Files:**
- Create: `pr_gatekeeper/orchestrator.py`
- Create: `pr_gatekeeper/review.py`
- Test: `tests/test_orchestrator.py`

**Interfaces:**
- Consumes: `GitHubClient` (Task 4), `SecurityAgent`/`SecurityAgentError` (Task 6), `run_tests` (Task 5), `MemoryStore` (Task 3), `decide` (Task 2), `GateVerdict` (Task 1)
- Produces: `run(pr_url: str, github_token: str, anthropic_api_key: str, db_path: str) -> GateVerdict` in `orchestrator.py`; a CLI in `review.py` with `--pr <url>` and `--report` modes.

- [ ] **Step 1: Write the failing tests (happy path + the fail-closed path when the security agent errors)**

```python
# tests/test_orchestrator.py
from unittest.mock import patch, MagicMock
from pr_gatekeeper.orchestrator import run
from pr_gatekeeper.models import PRInfo, TestResult, Finding
from pr_gatekeeper.security_agent import SecurityAgentError


def test_run_happy_path_posts_clear_comment(tmp_path):
    db_path = str(tmp_path / "memory.db")
    pr_info = PRInfo(repo="brandonalexander/demo", number=1, diff="diff", changed_files=["app.py"], head_ref="fix-1", head_sha="abc")

    with patch("pr_gatekeeper.orchestrator.GitHubClient") as MockGitHub, \
         patch("pr_gatekeeper.orchestrator.SecurityAgent") as MockAgent, \
         patch("pr_gatekeeper.orchestrator.run_tests") as mock_run_tests:

        mock_github = MockGitHub.return_value
        mock_github.fetch_pr.return_value = pr_info
        mock_agent = MockAgent.return_value
        mock_agent.review.return_value = []
        mock_run_tests.return_value = TestResult(ran=True, passed=True, output="5 passed")

        verdict = run(pr_url="https://github.com/brandonalexander/demo/pull/1",
                       github_token="t", anthropic_api_key="k", db_path=db_path)

        assert verdict.status == "clear"
        mock_github.post_comment.assert_called_once()
        posted_body = mock_github.post_comment.call_args.kwargs.get("body") or mock_github.post_comment.call_args[0][2]
        assert "clear" in posted_body.lower()


def test_run_flags_recurring_finding_in_posted_comment(tmp_path):
    db_path = str(tmp_path / "memory.db")
    pr_info_1 = PRInfo(repo="brandonalexander/demo", number=1, diff="diff", changed_files=["app.py"], head_ref="fix-1", head_sha="abc")
    pr_info_2 = PRInfo(repo="brandonalexander/demo", number=2, diff="diff", changed_files=["app.py"], head_ref="fix-2", head_sha="def")
    finding = Finding(file="app.py", severity="low", description="unused import")

    with patch("pr_gatekeeper.orchestrator.GitHubClient") as MockGitHub, \
         patch("pr_gatekeeper.orchestrator.SecurityAgent") as MockAgent, \
         patch("pr_gatekeeper.orchestrator.run_tests") as mock_run_tests:

        mock_github = MockGitHub.return_value
        mock_agent = MockAgent.return_value
        mock_run_tests.return_value = TestResult(ran=True, passed=True, output="5 passed")

        # First run establishes history for app.py
        mock_github.fetch_pr.return_value = pr_info_1
        mock_agent.review.return_value = [finding]
        run(pr_url="https://github.com/brandonalexander/demo/pull/1",
            github_token="t", anthropic_api_key="k", db_path=db_path)

        # Second run on the same file should flag recurrence
        mock_github.fetch_pr.return_value = pr_info_2
        mock_agent.review.return_value = [finding]
        run(pr_url="https://github.com/brandonalexander/demo/pull/2",
            github_token="t", anthropic_api_key="k", db_path=db_path)

        second_call_body = mock_github.post_comment.call_args.kwargs.get("body") or mock_github.post_comment.call_args[0][2]
        assert "similar finding" in second_call_body.lower()


def test_run_blocks_when_security_agent_fails_rather_than_treating_as_no_findings(tmp_path):
    db_path = str(tmp_path / "memory.db")
    pr_info = PRInfo(repo="brandonalexander/demo", number=2, diff="diff", changed_files=["app.py"], head_ref="fix-2", head_sha="def")

    with patch("pr_gatekeeper.orchestrator.GitHubClient") as MockGitHub, \
         patch("pr_gatekeeper.orchestrator.SecurityAgent") as MockAgent, \
         patch("pr_gatekeeper.orchestrator.run_tests") as mock_run_tests:

        mock_github = MockGitHub.return_value
        mock_github.fetch_pr.return_value = pr_info
        mock_agent = MockAgent.return_value
        mock_agent.review.side_effect = SecurityAgentError("rate limited")
        mock_run_tests.return_value = TestResult(ran=True, passed=True, output="5 passed")

        verdict = run(pr_url="https://github.com/brandonalexander/demo/pull/2",
                       github_token="t", anthropic_api_key="k", db_path=db_path)

        assert verdict.status == "blocked"
        assert "security review could not complete" in verdict.reason
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_orchestrator.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pr_gatekeeper.orchestrator'`

- [ ] **Step 3: Write the implementation**

```python
# pr_gatekeeper/orchestrator.py
import time
from pr_gatekeeper.github_client import GitHubClient
from pr_gatekeeper.security_agent import SecurityAgent, SecurityAgentError
from pr_gatekeeper.test_runner import run_tests
from pr_gatekeeper.memory_store import MemoryStore
from pr_gatekeeper.gate import decide
from pr_gatekeeper.models import GateVerdict


def run(pr_url: str, github_token: str, anthropic_api_key: str, db_path: str) -> GateVerdict:
    start = time.monotonic()
    github = GitHubClient(token=github_token)
    pr_info = github.fetch_pr(pr_url)

    agent = SecurityAgent(api_key=anthropic_api_key, github_client=github)
    try:
        findings = agent.review(pr_info)
    except SecurityAgentError as e:
        verdict = GateVerdict(status="blocked", reason=f"security review could not complete: {e}")
        findings = []
        test_result = run_tests(repo=pr_info.repo, ref=pr_info.head_ref, github_token=github_token)
        duration_s = time.monotonic() - start
        store = MemoryStore(db_path)
        store.record_run(pr_number=pr_info.number, repo=pr_info.repo, verdict=verdict, findings=findings, test_result=test_result, duration_s=duration_s)
        github.post_comment(repo=pr_info.repo, pr_number=pr_info.number, body=_format_comment(verdict, findings, test_result))
        return verdict

    test_result = run_tests(repo=pr_info.repo, ref=pr_info.head_ref, github_token=github_token)
    verdict = decide(findings, test_result)

    duration_s = time.monotonic() - start
    store = MemoryStore(db_path)

    # Check recurrence BEFORE recording this run's findings, so a file only
    # reads as "recurring" if it had a finding on a DIFFERENT prior run.
    recurring_files = {
        f.file for f in findings if store.past_findings_for_file(repo=pr_info.repo, file=f.file)
    }

    store.record_run(pr_number=pr_info.number, repo=pr_info.repo, verdict=verdict, findings=findings, test_result=test_result, duration_s=duration_s)

    github.post_comment(repo=pr_info.repo, pr_number=pr_info.number, body=_format_comment(verdict, findings, test_result, recurring_files))
    return verdict


def _format_comment(verdict: GateVerdict, findings, test_result, recurring_files: set[str] | None = None) -> str:
    recurring_files = recurring_files or set()
    lines = [f"**pr-gatekeeper verdict: {verdict.status}**", f"Reason: {verdict.reason}", ""]
    lines.append(f"Tests: {'ran' if test_result.ran else 'did not run'}, {'passed' if test_result.passed else 'did not pass'}")
    if findings:
        lines.append("")
        lines.append("Findings:")
        for f in findings:
            suffix = " (similar finding seen on a prior PR for this file)" if f.file in recurring_files else ""
            lines.append(f"- [{f.severity}] {f.file}: {f.description}{suffix}")
    return "\n".join(lines)
```

```python
# pr_gatekeeper/review.py
import argparse
import os
import sys
from pr_gatekeeper.orchestrator import run
from pr_gatekeeper.memory_store import MemoryStore

DB_PATH = ".pr-gatekeeper/memory.db"


def main():
    parser = argparse.ArgumentParser(prog="review")
    parser.add_argument("--pr", help="GitHub PR URL to review")
    parser.add_argument("--report", action="store_true", help="print run history summary")
    args = parser.parse_args()

    os.makedirs(".pr-gatekeeper", exist_ok=True)

    if args.report:
        store = MemoryStore(DB_PATH)
        report = store.report()
        print(f"Total runs:     {report.total_runs}")
        print(f"Blocked:        {report.blocked_count}")
        print(f"Warned:         {report.warned_count}")
        print(f"Clear:          {report.clear_count}")
        print(f"Avg duration:   {report.avg_duration_s:.2f}s")
        print(f"Total findings: {report.total_findings}")
        return

    if not args.pr:
        parser.error("--pr <url> or --report is required")

    github_token = os.environ.get("GITHUB_TOKEN")
    anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not github_token or not anthropic_api_key:
        print("GITHUB_TOKEN and ANTHROPIC_API_KEY must be set in the environment", file=sys.stderr)
        sys.exit(1)

    verdict = run(pr_url=args.pr, github_token=github_token, anthropic_api_key=anthropic_api_key, db_path=DB_PATH)
    print(f"Verdict: {verdict.status} — {verdict.reason}")
    sys.exit(0 if verdict.status != "blocked" else 1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_orchestrator.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Run the full test suite**

Run: `pytest -v`
Expected: all tests across Tasks 1–7 pass

- [ ] **Step 6: Commit**

```bash
git add pr_gatekeeper/orchestrator.py pr_gatekeeper/review.py tests/test_orchestrator.py
git commit -m "feat: orchestrator wiring and CLI entrypoint"
```

---

### Task 8: Demo repo, README, and manual end-to-end verification

**Files:**
- Create: `demo-repo/app.py`
- Create: `demo-repo/tests/test_app.py`
- Create: `demo-repo/README.md`
- Create: `README.md` (pr-gatekeeper's own)

**Interfaces:**
- Consumes: the full `pr_gatekeeper` CLI (Task 7) — this task is manual verification plus the artifact itself, not new library code.

- [ ] **Step 1: Build a minimal demo Flask-free app with a real test suite**

```python
# demo-repo/app.py
def add(a: int, b: int) -> int:
    return a + b


def divide(a: int, b: int) -> float:
    if b == 0:
        raise ValueError("cannot divide by zero")
    return a / b
```

```python
# demo-repo/tests/test_app.py
from app import add, divide
import pytest


def test_add():
    assert add(2, 3) == 5


def test_divide():
    assert divide(10, 2) == 5


def test_divide_by_zero_raises():
    with pytest.raises(ValueError):
        divide(1, 0)
```

```markdown
# demo-repo/README.md
Minimal demo app used to exercise pr-gatekeeper. Three PRs are opened against
this repo on GitHub to demonstrate each gate outcome:

1. `clean-pr` branch — adds a harmless function, all tests pass, no findings.
2. `secret-pr` branch — introduces a hardcoded API key, tests pass, security finding blocks it.
3. `failing-pr` branch — changes `add` to a buggy implementation, breaks `test_add`.
```

- [ ] **Step 2: Push demo-repo to GitHub and open the three PRs manually**

Run (adjust the GitHub username):
```bash
cd demo-repo
git init -q
git add .
git commit -q -m "initial demo app"
gh repo create pr-gatekeeper-demo --public --source=. --push
git checkout -b clean-pr
# add a small harmless change, commit, push, open PR via gh pr create
git checkout -b secret-pr main
# add: API_KEY = "sk-live-abc123xyz" to app.py, commit, push, open PR
git checkout -b failing-pr main
# break add() to return a - b instead of a + b, commit, push, open PR
```

This step is manual (opening PRs is not something to script around `gh pr create` reliably for a demo narrative) — the goal is three real, inspectable PRs on a real public repo.

- [ ] **Step 3: Run pr-gatekeeper against all three PRs**

```bash
export GITHUB_TOKEN=<your token>
export ANTHROPIC_API_KEY=<your key>
python -m pr_gatekeeper.review --pr https://github.com/<you>/pr-gatekeeper-demo/pull/1
python -m pr_gatekeeper.review --pr https://github.com/<you>/pr-gatekeeper-demo/pull/2
python -m pr_gatekeeper.review --pr https://github.com/<you>/pr-gatekeeper-demo/pull/3
```

Expected: PR 1 → `clear`; PR 2 (secret) → `blocked`, high-severity finding; PR 3 (failing test) → `blocked`, test failure. Confirm each PR on GitHub actually received the comment.

- [ ] **Step 4: Run the report**

```bash
python -m pr_gatekeeper.review --report
```

Expected: `Total runs: 3`, one each of blocked/blocked/clear (or warned if the secret is scored low — confirm against the actual model output and adjust the demo-repo's secret-pr content if needed to reliably trigger `high`).

- [ ] **Step 5: Write pr-gatekeeper's own README**

```markdown
# pr-gatekeeper

A coding-agent code reviewer wired into a real GitHub PR workflow: a
security-focused Claude subagent reviews the diff, a deterministic `pytest`
run gates on whether the change actually works, results are remembered
across runs in SQLite, and a verdict comment is posted back to the PR.

## Why this exists

Built to demonstrate putting a coding agent into the real SDLC — review,
gate, remember, measure — rather than a chat demo. See
`docs/superpowers/specs/2026-09-30-pr-gatekeeper-design.md` for the full
design and how each piece maps to that goal.

## Setup

\`\`\`bash
pip install -r requirements.txt
cp .env.example .env  # fill in GITHUB_TOKEN and ANTHROPIC_API_KEY
\`\`\`

## Usage

\`\`\`bash
python -m pr_gatekeeper.review --pr https://github.com/<owner>/<repo>/pull/<n>
python -m pr_gatekeeper.review --report
\`\`\`

## How it decides

| Condition | Verdict |
|---|---|
| Tests fail or can't run | blocked |
| High-severity security finding | blocked |
| Low-severity finding only | warned |
| Clean | clear (still human-merged — no auto-merge) |

## Architecture

\`github_client\` (fetch/comment) → \`security_agent\` (Claude API review) +
\`test_runner\` (real pytest, not an LLM's opinion) → \`gate\` (pure decision
logic) → \`memory_store\` (SQLite: history + recurrence + metrics).
```

- [ ] **Step 6: Commit**

```bash
git add demo-repo/ README.md
git commit -m "docs: demo repo, README, and manual verification notes"
```
