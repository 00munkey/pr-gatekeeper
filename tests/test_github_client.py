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
