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
