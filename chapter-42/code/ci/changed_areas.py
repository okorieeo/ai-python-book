"""Decide which parts of the monorepo a change touches, so CI only runs what is needed.

Usage in a workflow:   git diff --name-only -z HEAD^1 HEAD | python ci/changed_areas.py
Prints lines such as   backend=true   that can be appended to $GITHUB_OUTPUT.
"""

import sys

AREAS = ("backend", "web", "mobile")

# A change to the pipeline itself, or to files every area shares, must re-check everything.
SHARED_PREFIXES = (".github/", "ci/")
SHARED_FILES = {".pre-commit-config.yaml"}


def classify(paths: list[str]) -> dict[str, bool]:
    result = dict.fromkeys(AREAS, False)
    for raw in paths:
        path = raw.strip().replace("\\", "/").removeprefix("./")
        if not path:
            continue
        if path in SHARED_FILES or path.startswith(SHARED_PREFIXES):
            return dict.fromkeys(AREAS, True)
        for area in AREAS:
            if path.startswith(f"{area}/"):
                result[area] = True
    return result


def parse_nul_separated(data: bytes) -> list[str]:
    """`git diff --name-only -z` separates names with NUL, so unusual file names stay whole."""
    return [p.decode("utf-8", errors="replace") for p in data.split(b"\0") if p]


def render(result: dict[str, bool]) -> str:
    return "\n".join(f"{area}={'true' if result[area] else 'false'}" for area in AREAS)


def main(argv: list[str]) -> int:
    if "--all" in argv:  # pushes to main: nothing is skipped
        print(render(dict.fromkeys(AREAS, True)))
        return 0
    print(render(classify(parse_nul_separated(sys.stdin.buffer.read()))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
