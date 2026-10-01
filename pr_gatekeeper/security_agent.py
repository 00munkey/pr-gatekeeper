import json
import anthropic
from pr_gatekeeper.models import PRInfo, Finding

SYSTEM_PROMPT = """You are a security reviewer for a pull request. You will be given a unified diff.
Identify security issues only (e.g. hardcoded secrets, injection vulnerabilities, unsafe deserialization,
missing auth checks). Ignore style, performance, and non-security correctness issues.

Respond with ONLY a JSON array of findings, no other text. Each finding is an object with keys:
"file" (string), "severity" ("high" or "low"), "description" (string).
If there are no security issues, respond with exactly: []
"""


class SecurityAgentError(Exception):
    pass


class SecurityAgent:
    def __init__(self, api_key: str, github_client):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.github_client = github_client

    def review(self, pr_info: PRInfo) -> list[Finding]:
        try:
            message = self.client.messages.create(
                model="claude-opus-5",
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": f"Diff for PR #{pr_info.number} in {pr_info.repo}:\n\n{pr_info.diff}"}],
            )
        except anthropic.RateLimitError as e:
            raise SecurityAgentError(f"Anthropic API rate limited: {e}")
        except anthropic.APIConnectionError as e:
            raise SecurityAgentError(f"Anthropic API connection error: {e}")
        except anthropic.APIStatusError as e:
            raise SecurityAgentError(f"Anthropic API returned {e.status_code}: {e.message}")
        except Exception as e:
            # Fail closed on anything unexpected too - never silently treat as "no findings".
            raise SecurityAgentError(f"Anthropic API call failed: {e}")

        text_blocks = [block.text for block in message.content if block.type == "text"]
        raw_text = "\n".join(text_blocks).strip()

        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError:
            raise SecurityAgentError(f"could not parse model output as JSON findings: {raw_text!r}")

        if not isinstance(parsed, list):
            raise SecurityAgentError(f"could not parse model output as a JSON array: {raw_text!r}")

        findings = []
        for item in parsed:
            try:
                findings.append(Finding(file=item["file"], severity=item["severity"], description=item["description"]))
            except (KeyError, TypeError):
                raise SecurityAgentError(f"could not parse finding item: {item!r}")

        return findings
