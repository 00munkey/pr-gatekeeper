# pr-gatekeeper

A coding-agent code reviewer wired into a real GitHub PR workflow: a
security-focused Claude subagent reviews the diff, a deterministic `pytest`
run gates on whether the change actually works, results are remembered
across runs in SQLite, and a verdict comment is posted back to the PR.

## Why this exists

Built to demonstrate putting a coding agent into the real SDLC — review,
gate, remember, measure — rather than a chat demo. See
`docs/superpowers/specs/2026-09-30-pr-gatekeeper-design.md` for the full
design and how each piece maps to that goal.

## ⚠️ This executes untrusted code

Reviewing a PR means cloning its branch and running `pytest` against it.
`pytest` executes a repo's `conftest.py` at collection time, before any test
runs — so merely *reviewing* a hostile PR is arbitrary code execution, as
the invoking user, with `GITHUB_TOKEN` and `ANTHROPIC_API_KEY` in the
environment. Only point this at repos and branches you trust. The demo
repo is scoped deliberately so this never comes up there; for anything
beyond that, run it inside a container or VM with no access to real
secrets, not on your own machine.

The diff content sent to the security subagent is also treated as
untrusted: it's fenced in `<diff>` tags and the system prompt instructs the
model to analyze it as data, never as instructions, so a PR can't talk its
way past its own review.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in GITHUB_TOKEN and ANTHROPIC_API_KEY
```

## Usage

```bash
python -m pr_gatekeeper.review --pr https://github.com/<owner>/<repo>/pull/<n>
python -m pr_gatekeeper.review --report
```

## How it decides

| Condition | Verdict |
|---|---|
| Tests fail or can't run | blocked |
| High-severity security finding | blocked |
| Low-severity finding only | warned |
| Clean | clear (still human-merged — no auto-merge) |

## Architecture

`github_client` (fetch/comment) → `security_agent` (Claude API review) +
`test_runner` (real pytest, not an LLM's opinion) → `gate` (pure decision
logic) → `memory_store` (SQLite: history + recurrence + metrics).

## Demo

See `demo-repo/` for a minimal app with three seeded PRs covering each gate
outcome (clean / security finding / failing test) — the repo you'd push to
GitHub and point this tool at.
