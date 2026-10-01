import json
from unittest.mock import MagicMock
from pr_gatekeeper.security_agent import SecurityAgent, SecurityAgentError
from pr_gatekeeper.models import PRInfo


def make_pr_info(diff="diff --git a/app.py b/app.py\n+SECRET = 'abc123'"):
    return PRInfo(repo="brandonalexander/demo", number=1, diff=diff, changed_files=["app.py"], head_ref="fix-1", head_sha="abc")


def test_review_returns_findings_from_final_text_block():
    agent = SecurityAgent(api_key="fake-key", github_client=MagicMock())
    final_message = MagicMock()
    final_message.content = [MagicMock(type="text", text=json.dumps([
        {"file": "app.py", "severity": "high", "description": "hardcoded secret"}
    ]))]
    agent.client = MagicMock()
    agent.client.messages.create.return_value = final_message

    findings = agent.review(make_pr_info())

    assert len(findings) == 1
    assert findings[0].severity == "high"
    assert findings[0].file == "app.py"


def test_review_on_non_python_only_diff_returns_empty_list_without_crashing():
    agent = SecurityAgent(api_key="fake-key", github_client=MagicMock())
    final_message = MagicMock()
    final_message.content = [MagicMock(type="text", text="[]")]
    agent.client = MagicMock()
    agent.client.messages.create.return_value = final_message

    findings = agent.review(make_pr_info(diff="diff --git a/README.md b/README.md\n+docs update"))

    assert findings == []


def test_review_raises_on_malformed_model_output():
    agent = SecurityAgent(api_key="fake-key", github_client=MagicMock())
    final_message = MagicMock()
    final_message.content = [MagicMock(type="text", text="I think this looks fine, no issues!")]
    agent.client = MagicMock()
    agent.client.messages.create.return_value = final_message

    try:
        agent.review(make_pr_info())
        assert False, "expected SecurityAgentError"
    except SecurityAgentError as e:
        assert "could not parse" in str(e)


def test_review_raises_on_api_error():
    agent = SecurityAgent(api_key="fake-key", github_client=MagicMock())
    agent.client = MagicMock()
    agent.client.messages.create.side_effect = Exception("rate limited")

    try:
        agent.review(make_pr_info())
        assert False, "expected SecurityAgentError"
    except SecurityAgentError as e:
        assert "rate limited" in str(e)
