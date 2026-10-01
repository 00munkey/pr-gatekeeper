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
