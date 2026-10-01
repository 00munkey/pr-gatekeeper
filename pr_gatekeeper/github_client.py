import base64
import re
import requests
from pr_gatekeeper.models import PRInfo

PR_URL_RE = re.compile(r"github\.com/([^/]+/[^/]+)/pull/(\d+)")


class GitHubClientError(Exception):
    pass


class GitHubClient:
    def __init__(self, token: str):
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }

    def _parse_pr_url(self, pr_url: str) -> tuple[str, int]:
        match = PR_URL_RE.search(pr_url)
        if not match:
            raise GitHubClientError(f"'{pr_url}' is not a valid GitHub PR URL")
        return match.group(1), int(match.group(2))

    def fetch_pr(self, pr_url: str) -> PRInfo:
        repo, number = self._parse_pr_url(pr_url)

        pr_resp = requests.get(f"https://api.github.com/repos/{repo}/pulls/{number}", headers=self.headers)
        if pr_resp.status_code != 200:
            raise GitHubClientError(f"GitHub API returned {pr_resp.status_code} fetching PR #{number}: {pr_resp.text}")
        pr_json = pr_resp.json()

        files_resp = requests.get(f"https://api.github.com/repos/{repo}/pulls/{number}/files", headers=self.headers)
        if files_resp.status_code != 200:
            raise GitHubClientError(f"GitHub API returned {files_resp.status_code} fetching changed files")
        changed_files = [f["filename"] for f in files_resp.json()]

        diff_headers = dict(self.headers, Accept="application/vnd.github.v3.diff")
        diff_resp = requests.get(f"https://api.github.com/repos/{repo}/pulls/{number}", headers=diff_headers)
        if diff_resp.status_code != 200:
            raise GitHubClientError(f"GitHub API returned {diff_resp.status_code} fetching diff")

        return PRInfo(
            repo=repo,
            number=number,
            diff=diff_resp.text,
            changed_files=changed_files,
            head_ref=pr_json["head"]["ref"],
            head_sha=pr_json["head"]["sha"],
        )

    def read_file_at_ref(self, repo: str, path: str, ref: str) -> str:
        resp = requests.get(
            f"https://api.github.com/repos/{repo}/contents/{path}",
            headers=self.headers,
            params={"ref": ref},
        )
        if resp.status_code != 200:
            raise GitHubClientError(f"GitHub API returned {resp.status_code} reading {path}@{ref}")
        body = resp.json()
        return base64.b64decode(body["content"]).decode("utf-8")

    def post_comment(self, repo: str, pr_number: int, body: str) -> None:
        resp = requests.post(
            f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments",
            headers=self.headers,
            json={"body": body},
        )
        if resp.status_code != 201:
            raise GitHubClientError(f"GitHub API returned {resp.status_code} posting comment: {resp.text}")
