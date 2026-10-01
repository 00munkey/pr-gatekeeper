import subprocess
import tempfile
from pr_gatekeeper.models import TestResult


def run_tests(repo: str, ref: str, github_token: str) -> TestResult:
    with tempfile.TemporaryDirectory() as tmpdir:
        clone_url = f"https://{github_token}@github.com/{repo}.git"
        clone = subprocess.run(
            ["git", "clone", "--branch", ref, "--depth", "1", clone_url, tmpdir],
            capture_output=True,
            text=True,
        )
        if clone.returncode != 0:
            return TestResult(ran=False, passed=False, output=clone.stderr.strip())

        pytest_run = subprocess.run(
            ["pytest", "-v"],
            cwd=tmpdir,
            capture_output=True,
            text=True,
        )
        output = (pytest_run.stdout + pytest_run.stderr).strip()
        return TestResult(ran=True, passed=pytest_run.returncode == 0, output=output)
