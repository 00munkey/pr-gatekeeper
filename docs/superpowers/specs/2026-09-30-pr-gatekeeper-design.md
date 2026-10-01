# pr-gatekeeper — Design

**Date:** 2026-09-30
**Owner:** Brandon Alexander
**Status:** Approved for implementation planning

## Purpose

A hands-on, public artifact demonstrating an agentic code-review gate wired into a real SDLC loop: a coding agent that reviews a real GitHub pull request, a deterministic test-based merge gate, persistent memory across runs, and instrumented metrics. Built as a weekend/short-timeline portfolio piece, scoped as a reusable component rather than a single end-to-end pipeline — it's the review/validation stage, not the full plan→code→review→ship factory (that larger scope, if pursued later, is a separate project this one could plug into).

**Non-goals for this version:** no auto-merge, no planner/coder subagents (reviewing, not generating, code), no GitHub Action/webhook trigger (CLI-first; a GHA wrapper is a documented future step, not part of this scope), no multi-repo or multi-language support (Python only, one demo repo).

## Target setup

A small Python repo (owned by the author, created as part of this work or an existing simple app) with a real `pytest` suite, seeded with at least three demo PRs:

1. A clean PR — passes tests, no security findings.
2. A PR with a real security issue (e.g., a hardcoded secret or a SQL-injection-shaped bug).
3. A PR with a failing test.

These three give a complete demo of every gate outcome without running untrusted third-party code.

## Architecture

```
review.py (CLI) --pr <github_pr_url>
   -> github_client.fetch_pr(pr_url)          # diff + changed files + branch ref
   -> security_agent.review(diff, file_reader_tool)   # Claude API call, security-focused prompt
   -> test_runner.run(branch_ref)             # checkout + pytest, deterministic
   -> memory_store.record(pr, findings, test_result, timing, cost)
   -> gate.decide(findings, test_result)      # -> blocked / warned / clear
   -> github_client.post_comment(pr, verdict, findings, test_result)
```

### Components

| File | Responsibility | Depends on |
|---|---|---|
| `github_client.py` | Fetch PR diff/changed files/branch ref via GitHub REST API; post a formatted comment back to the PR | GitHub personal access token (env var) |
| `security_agent.py` | Calls the Anthropic API directly (raw tool-use loop, no Agent SDK) with a security-review system prompt; has one tool — read a file's full content from the repo at a given ref, for context beyond the diff | Anthropic API key (env var), `github_client` for file reads |
| `test_runner.py` | Checks out the PR branch into a local temp worktree, runs `pytest`, captures pass/fail and output | local git, pytest installed in the demo repo's env |
| `memory_store.py` | SQLite wrapper — tables for `runs` (pr, timestamp, verdict, timing, token cost) and `findings` (pr, file, severity, description); supports a simple "has this file had a finding before" lookup | sqlite3 (stdlib) |
| `gate.py` | Pure decision logic: given findings + test result, return `blocked` / `warned` / `clear` plus the reason. No I/O — easy to unit test. | — |
| `orchestrator.py` | Wires the above together in the flow above | all of the above |
| `review.py` | CLI entrypoint (`argparse`), calls `orchestrator.run(pr_url)` | `orchestrator` |

### Memory

SQLite file (`.pr-gatekeeper/memory.db`, gitignored). Two uses:

1. **Recurrence signal:** if a file flagged in a past run appears again with a similar finding, the comment says so explicitly ("this file had a similar finding on PR #N") — this is the "memory" differentiator from a stateless linter.
2. **Metrics source:** `review.py --report` reads `runs` and prints a summary table (PRs reviewed, pass/block/warn counts, avg review time, total findings caught) — this is the defendable "number that moved" for the interview.

### Merge/review contract (gate.py logic)

| Condition | Verdict |
|---|---|
| Tests fail | `blocked` — list failing tests |
| Any high-severity security finding | `blocked` — flagged for human review |
| Only low-severity findings, tests pass | `warned` — not blocked |
| No findings, tests pass | `clear` — ready, but never auto-merged; a human always makes the merge call |

### Error handling

Fail closed, not open — this is itself a point worth being able to explain in interview:

- GitHub API failure (rate limit, network, bad token) → CLI exits non-zero with a clear message; no comment posted claiming a verdict that wasn't computed.
- Anthropic API failure → verdict defaults to `blocked` with reason "security review could not complete" — never silently treated as "no findings."
- Branch checkout / test-run failure (not the same as tests *failing*) → verdict `blocked` with reason "tests could not run" — distinguished from an actual test failure in both the comment and the stored record.

### Testing (of pr-gatekeeper itself)

- Unit tests for `gate.py` (pure logic, all four verdict branches) and `memory_store.py` (recurrence lookup, report aggregation) — fast, no network, run in CI for this repo.
- `github_client` and `security_agent` tested with mocked HTTP/API responses for the happy path and each failure mode above.
- One or two manual end-to-end runs against the seeded demo repo's real PRs — not run in CI, since each costs real Anthropic API tokens.

## How this maps to the AT&T Principal AI Engineer, SDLC JD

(Kept here because it's the reason this project exists on this timeline — see `~/code/career-ops/interview-prep/att-principal-ai-engineer-sdlc.md`.)

- "Hands-on daily use of a coding agent... point of view on when the agent is the driver versus when it must be gated" → the security subagent is the driver on review, the deterministic test runner is the gate; the design doc above is the explicit statement of that split.
- "Put evaluation in front of main. Agent changes do not ship on hope." → `test_runner.py` is real `pytest`, not an LLM's opinion.
- "At least one engineering metric they will defend: baseline, after, whose dashboard" → `review.py --report`, backed by `memory_store.py`.
- "Build and maintain reusable skills, workflows... that more than one team can pick up" → scoped as a standalone review/gate component on purpose, not wired to one team's pipeline.
- "Produce artifacts someone else can open — a public... repo... a talk" → the repo itself, plus a short README walkthrough or recorded demo once built.

## Success criteria for this pass

- `review.py --pr <url>` runs end-to-end against all three seeded demo PRs and produces the correct verdict for each.
- `review.py --report` shows real numbers from those runs.
- Unit tests pass for `gate.py` and `memory_store.py`.
- A README exists explaining what it does, why, and how to run it — this is the artifact itself.
