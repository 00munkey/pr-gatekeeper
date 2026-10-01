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
