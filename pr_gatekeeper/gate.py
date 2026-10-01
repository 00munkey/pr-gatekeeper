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
