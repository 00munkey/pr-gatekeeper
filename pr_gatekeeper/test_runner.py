import base64
import os
import subprocess
import sys
import tempfile
from pr_gatekeeper.models import TestResult

CLONE_TIMEOUT_S = 60
TEST_TIMEOUT_S = 300


def run_tests(repo: str, ref: str, github_token: str) -> TestResult:
    with tempfile.TemporaryDirectory() as tmpdir:
        # Auth via an extra header, never in the URL - a URL-embedded token
        # leaks into subprocess argv, .git/config, and any echoed error text.
        auth_header = base64.b64encode(f"x-access-token:{github_token}".encode()).decode()
        clone_url = f"https://github.com/{repo}.git"
        env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}

        try:
            clone = subprocess.run(
                [
                    "git",
                    "-c", f"http.extraheader=AUTHORIZATION: basic {auth_header}",
                    "clone", "--branch", ref, "--depth", "1", clone_url, tmpdir,
                ],
                capture_output=True,
                text=True,
                timeout=CLONE_TIMEOUT_S,
                env=env,
                stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired:
            return TestResult(ran=False, passed=False, output=f"git clone timed out after {CLONE_TIMEOUT_S}s")

        if clone.returncode != 0:
            return TestResult(ran=False, passed=False, output=_redact(clone.stderr.strip(), github_token))

        try:
            pytest_run = subprocess.run(
                [sys.executable, "-m", "pytest", "-v"],
                cwd=tmpdir,
                capture_output=True,
                text=True,
                timeout=TEST_TIMEOUT_S,
                stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired:
            return TestResult(ran=False, passed=False, output=f"pytest timed out after {TEST_TIMEOUT_S}s")
        except (FileNotFoundError, OSError) as e:
            return TestResult(ran=False, passed=False, output=f"could not run pytest: {e}")

        output = _redact((pytest_run.stdout + pytest_run.stderr).strip(), github_token)
        # pytest exit codes: 0 = all passed, 1 = some tests failed (both real
        # test-suite outcomes). 2-5 are usage/internal/collection errors - the
        # suite never meaningfully ran, same bucket as a checkout failure.
        ran = pytest_run.returncode in (0, 1)
        passed = pytest_run.returncode == 0
        return TestResult(ran=ran, passed=passed, output=output)


def _redact(text: str, secret: str) -> str:
    return text.replace(secret, "***") if secret else text
