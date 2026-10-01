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
