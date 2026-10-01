import subprocess
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


def test_clone_does_not_embed_token_in_url():
    with patch("pr_gatekeeper.test_runner.subprocess.run") as mock_run:
        clone_result = MagicMock(returncode=0, stdout="", stderr="")
        pytest_result = MagicMock(returncode=0, stdout="5 passed", stderr="")
        mock_run.side_effect = [clone_result, pytest_result]

        run_tests(repo="brandonalexander/demo", ref="fix-7", github_token="super-secret-token")

    clone_call_args = mock_run.call_args_list[0].args[0]
    assert not any("super-secret-token" in str(arg) for arg in clone_call_args)
    assert any("AUTHORIZATION: basic" in str(arg) for arg in clone_call_args)


def test_output_scrubs_leaked_token():
    with patch("pr_gatekeeper.test_runner.subprocess.run") as mock_run:
        clone_result = MagicMock(returncode=128, stdout="", stderr="fatal: could not read Password for 'https://super-secret-token@github.com'")
        mock_run.side_effect = [clone_result]

        result = run_tests(repo="brandonalexander/demo", ref="fix-7", github_token="super-secret-token")

    assert "super-secret-token" not in result.output
    assert "***" in result.output


def test_pytest_missing_reports_could_not_run():
    with patch("pr_gatekeeper.test_runner.subprocess.run") as mock_run:
        clone_result = MagicMock(returncode=0, stdout="", stderr="")
        mock_run.side_effect = [clone_result, FileNotFoundError("No such file or directory: 'pytest'")]

        result = run_tests(repo="brandonalexander/demo", ref="fix-7", github_token="fake-token")

    assert result.ran is False
    assert result.passed is False
    assert "could not run pytest" in result.output


def test_pytest_internal_error_exit_code_reports_could_not_run():
    with patch("pr_gatekeeper.test_runner.subprocess.run") as mock_run:
        clone_result = MagicMock(returncode=0, stdout="", stderr="")
        pytest_result = MagicMock(returncode=5, stdout="no tests ran", stderr="")
        mock_run.side_effect = [clone_result, pytest_result]

        result = run_tests(repo="brandonalexander/demo", ref="fix-7", github_token="fake-token")

    assert result.ran is False
    assert result.passed is False


def test_clone_timeout_reports_could_not_run():
    with patch("pr_gatekeeper.test_runner.subprocess.run") as mock_run:
        mock_run.side_effect = [subprocess.TimeoutExpired(cmd="git clone", timeout=60)]

        result = run_tests(repo="brandonalexander/demo", ref="fix-7", github_token="fake-token")

    assert result.ran is False
    assert "timed out" in result.output


def test_pytest_timeout_reports_could_not_run():
    with patch("pr_gatekeeper.test_runner.subprocess.run") as mock_run:
        clone_result = MagicMock(returncode=0, stdout="", stderr="")
        mock_run.side_effect = [clone_result, subprocess.TimeoutExpired(cmd="pytest", timeout=300)]

        result = run_tests(repo="brandonalexander/demo", ref="fix-7", github_token="fake-token")

    assert result.ran is False
    assert "timed out" in result.output
