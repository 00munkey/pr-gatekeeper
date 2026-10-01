import json
from unittest.mock import MagicMock
from pr_gatekeeper.security_agent import SecurityAgent, SecurityAgentError, SYSTEM_PROMPT
from pr_gatekeeper.models import PRInfo


def make_pr_info(diff="diff --git a/app.py b/app.py\n+SECRET = 'abc123'"):
    return PRInfo(repo="brandonalexander/demo", number=1, diff=diff, changed_files=["app.py"], head_ref="fix-1", head_sha="abc")


def _text_message(text):
    msg = MagicMock()
    msg.stop_reason = "end_turn"
    msg.content = [MagicMock(type="text", text=text)]
    return msg


def test_review_returns_findings_from_final_text_block():
    agent = SecurityAgent(api_key="fake-key", github_client=MagicMock())
    agent.client = MagicMock()
    agent.client.messages.create.return_value = _text_message(json.dumps([
        {"file": "app.py", "severity": "high", "description": "hardcoded secret"}
    ]))

    findings = agent.review(make_pr_info())

    assert len(findings) == 1
    assert findings[0].severity == "high"
    assert findings[0].file == "app.py"


def test_review_on_non_python_only_diff_returns_empty_list_without_crashing():
    agent = SecurityAgent(api_key="fake-key", github_client=MagicMock())
    agent.client = MagicMock()
    agent.client.messages.create.return_value = _text_message("[]")

    findings = agent.review(make_pr_info(diff="diff --git a/README.md b/README.md\n+docs update"))

    assert findings == []


def test_review_raises_on_malformed_model_output():
    agent = SecurityAgent(api_key="fake-key", github_client=MagicMock())
    agent.client = MagicMock()
    agent.client.messages.create.return_value = _text_message("I think this looks fine, no issues!")

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


def test_review_sends_diff_wrapped_in_untrusted_delimiters():
    agent = SecurityAgent(api_key="fake-key", github_client=MagicMock())
    agent.client = MagicMock()
    agent.client.messages.create.return_value = _text_message("[]")

    agent.review(make_pr_info(diff="+ some diff content"))

    sent_messages = agent.client.messages.create.call_args.kwargs["messages"]
    sent_text = sent_messages[0]["content"]
    assert "<diff>" in sent_text and "</diff>" in sent_text
    assert "some diff content" in sent_text


def test_system_prompt_instructs_model_to_treat_diff_as_untrusted_data():
    assert "untrusted" in SYSTEM_PROMPT.lower()
    assert "not" in SYSTEM_PROMPT.lower() and "instructions" in SYSTEM_PROMPT.lower()


def test_review_calls_read_file_tool_and_feeds_result_back():
    github_client = MagicMock()
    github_client.read_file_at_ref.return_value = "def handler():\n    pass\n"
    agent = SecurityAgent(api_key="fake-key", github_client=github_client)
    agent.client = MagicMock()

    # MagicMock(name=...) sets the mock's repr, not a `.name` attribute - set it after construction.
    tool_use_block = MagicMock(type="tool_use", id="tool_1", input={"path": "app.py"})
    tool_use_block.name = "read_file"
    tool_use_message = MagicMock()
    tool_use_message.stop_reason = "tool_use"
    tool_use_message.content = [tool_use_block]

    final_message = _text_message(json.dumps([]))

    agent.client.messages.create.side_effect = [tool_use_message, final_message]

    findings = agent.review(make_pr_info())

    assert findings == []
    github_client.read_file_at_ref.assert_called_once_with(repo="brandonalexander/demo", path="app.py", ref="abc")

    second_call_messages = agent.client.messages.create.call_args.kwargs["messages"]
    tool_result_message = second_call_messages[-1]
    assert tool_result_message["role"] == "user"
    assert tool_result_message["content"][0]["type"] == "tool_result"
    assert tool_result_message["content"][0]["tool_use_id"] == "tool_1"
    assert "def handler" in tool_result_message["content"][0]["content"]


def test_review_raises_if_tool_loop_never_converges():
    agent = SecurityAgent(api_key="fake-key", github_client=MagicMock())
    agent.client = MagicMock()

    tool_use_block = MagicMock(type="tool_use", id="tool_1", input={"path": "app.py"})
    tool_use_block.name = "read_file"
    looping_message = MagicMock()
    looping_message.stop_reason = "tool_use"
    looping_message.content = [tool_use_block]
    agent.client.messages.create.return_value = looping_message

    try:
        agent.review(make_pr_info())
        assert False, "expected SecurityAgentError"
    except SecurityAgentError as e:
        assert "did not converge" in str(e)
