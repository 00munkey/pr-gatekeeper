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
