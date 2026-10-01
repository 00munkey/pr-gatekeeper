import sys
from unittest.mock import patch
import pytest
from pr_gatekeeper.github_client import GitHubClientError
from pr_gatekeeper.review import main


def test_main_exits_cleanly_on_github_client_error(capsys, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setattr(sys, "argv", ["review", "--pr", "https://example.com/not-a-pr"])

    with patch("pr_gatekeeper.review.run") as mock_run:
        mock_run.side_effect = GitHubClientError("'https://example.com/not-a-pr' is not a valid GitHub PR URL")
        with pytest.raises(SystemExit) as exc_info:
            main()

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "not a valid GitHub PR URL" in captured.err
    assert "Traceback" not in captured.err
