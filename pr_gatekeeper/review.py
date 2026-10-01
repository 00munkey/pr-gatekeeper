import argparse
import os
import sys
from pr_gatekeeper.orchestrator import run
from pr_gatekeeper.memory_store import MemoryStore

DB_PATH = ".pr-gatekeeper/memory.db"


def main():
    parser = argparse.ArgumentParser(prog="review")
    parser.add_argument("--pr", help="GitHub PR URL to review")
    parser.add_argument("--report", action="store_true", help="print run history summary")
    args = parser.parse_args()

    os.makedirs(".pr-gatekeeper", exist_ok=True)

    if args.report:
        store = MemoryStore(DB_PATH)
        report = store.report()
        print(f"Total runs:     {report.total_runs}")
        print(f"Blocked:        {report.blocked_count}")
        print(f"Warned:         {report.warned_count}")
        print(f"Clear:          {report.clear_count}")
        print(f"Avg duration:   {report.avg_duration_s:.2f}s")
        print(f"Total findings: {report.total_findings}")
        return

    if not args.pr:
        parser.error("--pr <url> or --report is required")

    github_token = os.environ.get("GITHUB_TOKEN")
    anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not github_token or not anthropic_api_key:
        print("GITHUB_TOKEN and ANTHROPIC_API_KEY must be set in the environment", file=sys.stderr)
        sys.exit(1)

    verdict = run(pr_url=args.pr, github_token=github_token, anthropic_api_key=anthropic_api_key, db_path=DB_PATH)
    print(f"Verdict: {verdict.status} — {verdict.reason}")
    sys.exit(0 if verdict.status != "blocked" else 1)


if __name__ == "__main__":
    main()
