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
