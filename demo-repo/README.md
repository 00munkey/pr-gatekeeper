# demo-repo

Minimal demo app used to exercise pr-gatekeeper. Three PRs are opened against
this repo on GitHub to demonstrate each gate outcome:

1. `clean-pr` branch — adds a harmless function, all tests pass, no findings.
2. `secret-pr` branch — introduces a hardcoded API key, tests pass, security finding blocks it.
3. `failing-pr` branch — changes `add` to a buggy implementation, breaks `test_add`.
