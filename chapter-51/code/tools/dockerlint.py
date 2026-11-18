"""A tiny policy checker for Dockerfiles and .dockerignore files.

It turns the habits from Chapter 51 into rules a machine can check on every pull
request. It is NOT a replacement for a full linter such as hadolint, and it does not
understand heredoc syntax (RUN <<EOF). Standard library only.

    python tools/dockerlint.py backend/Dockerfile backend/.dockerignore
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Finding:
    rule: str
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.rule} line {self.line}: {self.message}"


@dataclass
class Instruction:
    line: int
    name: str
    args: str


@dataclass
class Stage:
    line: int
    image: str
    name: str | None
    instructions: list[Instruction] = field(default_factory=list)


# ---------------------------------------------------------------- parsing

def parse_instructions(text: str) -> list[Instruction]:
    """Split a Dockerfile into instructions (joins lines ending in a backslash)."""
    result: list[Instruction] = []
    buffer: list[str] = []
    start = 0
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not buffer and (not line or line.startswith("#")):
            continue
        if buffer and line.startswith("#"):
            continue  # comment lines are allowed inside a continued instruction
        if not buffer:
            start = number
        if line.endswith("\\"):
            buffer.append(line[:-1].strip())
            continue
        buffer.append(line)
        joined = " ".join(part for part in buffer if part)
        buffer = []
        name, _, args = joined.partition(" ")
        result.append(Instruction(start, name.upper(), args.strip()))
    if buffer:  # file ended in the middle of a continuation
        joined = " ".join(part for part in buffer if part)
        name, _, args = joined.partition(" ")
        result.append(Instruction(start, name.upper(), args.strip()))
    return result


def split_stages(instructions: list[Instruction]) -> tuple[list[Instruction], list[Stage]]:
    """Return (instructions before the first FROM, the stages)."""
    preamble: list[Instruction] = []
    stages: list[Stage] = []
    for item in instructions:
        if item.name == "FROM":
            tokens = [t for t in item.args.split() if not t.startswith("--")]
            image = tokens[0] if tokens else ""
            name = tokens[2] if len(tokens) >= 3 and tokens[1].upper() == "AS" else None
            stages.append(Stage(item.line, image, name))
        elif stages:
            stages[-1].instructions.append(item)
        else:
            preamble.append(item)
    return preamble, stages


def _tokens(args: str) -> list[str]:
    """Words of a COPY/ADD line without its --flags."""
    return [t for t in args.split() if not t.startswith("--")]


SECRET_NAME = re.compile(
    r"(SECRET|PASSWORD|PASSWD|TOKEN|API_?KEY|PRIVATE_?KEY|CREDENTIAL)", re.IGNORECASE
)
INSTALL_STEP = re.compile(r"\b(pip install|npm ci|npm install|pnpm install|yarn install)\b")


def _variable_names(args: str) -> list[str]:
    names = re.findall(r"(?:^|\s)([A-Za-z_][A-Za-z0-9_]*)=", args)
    if names:
        return names
    first = args.split()[0] if args.split() else ""  # old style: ENV NAME value
    return [first] if first else []


# ---------------------------------------------------------------- Dockerfile rules

def lint_dockerfile(text: str) -> list[Finding]:
    findings: list[Finding] = []
    preamble, stages = split_stages(parse_instructions(text))
    if not stages:
        return [Finding("DL000", 1, "No FROM instruction found.")]

    # DL001: pinned base image
    seen_names: set[str] = set()
    for stage in stages:
        image = stage.image
        if image.lower() == "scratch" or image in seen_names or image == "":
            pass
        elif "@sha256:" in image:
            pass  # pinned by digest: the strictest form
        elif image.startswith("$"):
            pass  # a build argument decides; we cannot tell
        else:
            last = image.rsplit("/", 1)[-1]
            if ":" not in last:
                findings.append(Finding("DL001", stage.line,
                    f"Base image {image!r} has no tag, so it means 'latest'. Pin a version."))
            elif last.endswith(":latest"):
                findings.append(Finding("DL001", stage.line,
                    f"Base image {image!r} uses the 'latest' tag. Pin a version."))
        if stage.name:
            seen_names.add(stage.name)

    # DL003: multi-stage build
    if len(stages) < 2:
        findings.append(Finding("DL003", stages[0].line,
            "Single-stage build: build tools end up in the final image. Use a multi-stage build."))

    final = stages[-1]

    # DL002: non-root user in the final stage
    users = [i for i in final.instructions if i.name == "USER"]
    if not users:
        findings.append(Finding("DL002", final.line,
            "The final stage never sets USER, so the app runs as root."))
    else:
        user = users[-1].args.split(":")[0].strip()
        if user in ("root", "0"):
            findings.append(Finding("DL002", users[-1].line,
                "The final stage ends as root. Switch to a non-root USER."))

    # DL007: health check in the final stage
    health = [i for i in final.instructions if i.name == "HEALTHCHECK"]
    if not health or all(h.args.strip().upper() == "NONE" for h in health):
        findings.append(Finding("DL007", final.line,
            "The final stage has no HEALTHCHECK."))

    # DL008: exec form for CMD and ENTRYPOINT (signals reach the process)
    for stage in stages:
        for item in stage.instructions:
            if item.name in ("CMD", "ENTRYPOINT") and not item.args.lstrip().startswith("["):
                findings.append(Finding("DL008", item.line,
                    f"{item.name} uses shell form. Use the JSON (exec) form so signals reach your process."))

    for stage in stages:
        broad_copy_line = None
        for item in stage.instructions:
            # DL004: apt-get hygiene
            if item.name == "RUN":
                if re.search(r"\bapt(-get)?\s+install\b", item.args):
                    if "--no-install-recommends" not in item.args:
                        findings.append(Finding("DL004", item.line,
                            "apt-get install without --no-install-recommends adds unneeded packages."))
                    if "/var/lib/apt/lists" not in item.args:
                        findings.append(Finding("DL004", item.line,
                            "Remove /var/lib/apt/lists/* in the same RUN, or the cache stays in the layer."))
                    if not re.search(r"\bapt(-get)?\s+update\b", item.args):
                        findings.append(Finding("DL004", item.line,
                            "Run apt-get update in the same RUN as install, or you install from a stale list."))
                elif re.search(r"\bapt(-get)?\s+update\b", item.args):
                    findings.append(Finding("DL004", item.line,
                        "apt-get update alone in a RUN gets cached and goes stale. Combine it with install."))

                # DL010: pip cache
                if "pip install" in item.args and "--no-cache-dir" not in item.args \
                        and "--mount=type=cache" not in item.args \
                        and not any("PIP_NO_CACHE_DIR" in i.args for i in stage.instructions if i.name == "ENV"):
                    findings.append(Finding("DL010", item.line,
                        "pip install keeps a download cache in the layer. Use --no-cache-dir or a cache mount."))

                # DL005 (second half): the dependency install must not come after COPY . .
                if INSTALL_STEP.search(item.args) and broad_copy_line is not None:
                    findings.append(Finding("DL005", broad_copy_line,
                        "COPY . . comes before the dependency install, so every code change reinstalls dependencies. "
                        "Copy only the dependency files first."))
                    broad_copy_line = None

            if item.name in ("COPY", "ADD"):
                words = _tokens(item.args)
                sources = words[:-1]
                if "--from=" in item.args:
                    continue
                # DL005 (first half): remember a broad copy
                if sources and sources[0] in (".", "./") and broad_copy_line is None:
                    broad_copy_line = item.line
                # DL009: secrets and ADD
                for source in sources:
                    base = source.rstrip("/").rsplit("/", 1)[-1]
                    if base == ".env" or (base.startswith(".env.") and base != ".env.example"):
                        findings.append(Finding("DL009", item.line,
                            f"{item.name} copies {source}, a secrets file, into the image."))
                if item.name == "ADD":
                    for source in sources:
                        if not re.match(r"https?://", source) and not re.search(r"\.(tar|tar\.gz|tgz)$", source):
                            findings.append(Finding("DL009", item.line,
                                "Use COPY instead of ADD for local files; ADD has surprising extra behaviour."))

            # DL006: secrets in ENV / ARG
            if item.name in ("ENV", "ARG"):
                for name in _variable_names(item.args):
                    if name.startswith("NEXT_PUBLIC_") or name.endswith("_FILE"):
                        continue  # public by design / only a path to a secret file
                    if SECRET_NAME.search(name):
                        findings.append(Finding("DL006", item.line,
                            f"{item.name} {name} looks like a secret. Values in ENV and ARG are visible in "
                            "'docker history' and 'docker inspect'. Pass secrets at run time, or use a build secret."))
    return findings


# ---------------------------------------------------------------- .dockerignore rules

REQUIRED_IGNORES = {
    "generic": [(".env", "secrets file"), (".git", "version-control history")],
    "python": [(".venv", "virtual environment"), ("__pycache__", "compiled caches")],
    "node": [("node_modules", "dependencies (installed inside the image)"), (".next", "build output")],
}


def _ignored(patterns: list[str], wanted: str) -> bool:
    for pattern in patterns:
        cleaned = pattern.lstrip("*/").rstrip("/")
        if cleaned == wanted or cleaned.startswith(wanted + "*") or cleaned == wanted + ".*":
            return True
        if wanted == ".venv" and cleaned == "venv":
            return True
    return False


def lint_dockerignore(text: str, kind: str = "generic") -> list[Finding]:
    findings: list[Finding] = []
    lines = [(n, l.strip()) for n, l in enumerate(text.splitlines(), start=1)]
    patterns = [l for _, l in lines if l and not l.startswith("#") and not l.startswith("!")]
    wanted = list(REQUIRED_IGNORES["generic"]) + list(REQUIRED_IGNORES.get(kind, []))
    for name, why in wanted:
        if not _ignored(patterns, name):
            findings.append(Finding("DI001", 1, f".dockerignore does not exclude {name} ({why})."))
    for number, line in lines:
        if line.startswith("!") and not line.endswith(".env.example"):
            findings.append(Finding("DI002", number,
                f"{line} re-includes a path. Only !.env.example is expected here."))
    return findings


# ---------------------------------------------------------------- command line

def _kind_for(path: Path) -> str:
    folder = path.parent
    if (folder / "manage.py").exists() or list(folder.glob("requirements*.txt")):
        return "python"
    if (folder / "package.json").exists():
        return "node"
    return "generic"


def main(argv: list[str] | None = None) -> int:
    paths = [Path(a) for a in (argv if argv is not None else sys.argv[1:])]
    if not paths:
        print("usage: python tools/dockerlint.py PATH [PATH ...]")
        return 2
    failed = False
    for path in paths:
        if not path.exists():
            print(f"MISSING {path}")
            failed = True
            continue
        text = path.read_text(encoding="utf-8")
        if path.name == ".dockerignore":
            findings = lint_dockerignore(text, _kind_for(path))
        else:
            findings = lint_dockerfile(text)
        if findings:
            failed = True
            print(f"FAIL {path}")
            for finding in findings:
                print(f"  {finding}")
        else:
            print(f"OK   {path}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
