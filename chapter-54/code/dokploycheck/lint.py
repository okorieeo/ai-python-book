import argparse
import sys

from .compose_lint import check_env_example, lint_compose, parse_env_example
from .findings import FAIL, worst_status


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="dokploycheck", description="Lint a production compose file for Dokploy.")
    p.add_argument("compose")
    p.add_argument("--env-example", help="the committed .env example that lists every variable")
    p.add_argument("--isolated", action="store_true", help="Isolated Deployments is on, so dokploy-network is not required")
    args = p.parse_args(argv)

    env = None
    findings = []
    if args.env_example:
        with open(args.env_example, encoding="utf-8") as fh:
            env = parse_env_example(fh.read())
        findings += check_env_example(env)
    with open(args.compose, encoding="utf-8") as fh:
        findings += lint_compose(fh.read(), env, isolated=args.isolated)
    for f in findings:
        print(f.line())
    return 1 if worst_status(findings) == FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
