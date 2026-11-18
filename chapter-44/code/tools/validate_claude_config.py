#!/usr/bin/env python3
"""
Validate the Claude Code configuration in a project: hooks and permissions in .claude/settings.json, skills in
.claude/skills/*/SKILL.md, subagents in .claude/agents/*.md, and MCP servers in .mcp.json.

Why: a typo in a hook event name, a command path that does not exist, or an HTTP MCP server with no "type" fails
SILENTLY. Claude Code does not stop you; the guard you thought you had is simply not there. This turns those quiet
failures into errors in CI. Needs PyYAML (pip install pyyaml).

    python tools/validate_claude_config.py [project_root]
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

CORE_EVENTS = {"PreToolUse", "PostToolUse", "UserPromptSubmit", "Stop", "SubagentStop", "SessionStart", "SessionEnd", "Notification", "PreCompact"}
MATCHER_EVENTS = {"PreToolUse", "PostToolUse"}
HANDLER_TYPES = {"command", "prompt", "agent", "http"}
KNOWN_TOOLS = {"Read", "Grep", "Glob", "Edit", "Write", "MultiEdit", "NotebookEdit", "Bash", "WebFetch", "WebSearch", "Task", "TodoWrite", "BashOutput", "KillShell"}
WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
MODEL_ALIASES = {"sonnet", "opus", "haiku", "inherit"}
NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
RULE = re.compile(r"^[A-Za-z_][\w]*(\(.*\))?$")
SECRET = re.compile(r"(sk-ant-|sk_live_|ghp_|AKIA[0-9A-Z]{16}|Bearer\s+[A-Za-z0-9_\-]{20,}|://[^/\s:@]+:[^/\s@]{6,}@)")
SIDE_EFFECTS = re.compile(r"\bgit (?:commit|push)\b|\beas (?:submit|build|update)\b|\bdeploy\b|\bdrop table\b|\bmigrate\b", re.IGNORECASE)


@dataclass
class Problem:
    severity: str          # error | warn
    where: str
    message: str


def _frontmatter(path: Path) -> tuple[dict | None, str, str | None]:
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.DOTALL)
    if not m:
        return None, text, "no frontmatter: the file must start with a line containing only ---"
    try:
        data = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as exc:
        return None, m.group(2), f"frontmatter is not valid YAML: {str(exc).splitlines()[0]}"
    if not isinstance(data, dict):
        return None, m.group(2), "frontmatter must be a set of key: value lines"
    return data, m.group(2), None


def validate_settings(path: Path, root: Path) -> list[Problem]:
    out: list[Problem] = []
    where = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
    err = lambda msg: out.append(Problem("error", where, msg))
    warn = lambda msg: out.append(Problem("warn", where, msg))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        return [Problem("error", where, f"not valid JSON: {exc}")]
    if not isinstance(data, dict):
        return [Problem("error", where, "top level must be an object")]

    perms = data.get("permissions", {})
    for kind in ("allow", "deny", "ask"):
        rules = perms.get(kind, [])
        if not isinstance(rules, list) or not all(isinstance(r, str) for r in rules):
            err(f"permissions.{kind} must be a list of strings")
            continue
        for r in rules:
            if not RULE.match(r):
                err(f"permissions.{kind}: {r!r} is not a rule like Tool or Tool(pattern)")
    denies = " ".join(perms.get("deny", []) if isinstance(perms.get("deny"), list) else [])
    if ".env" not in denies:
        warn("no deny rule for reading .env files; add Read(./.env)")

    hooks = data.get("hooks", {})
    if not isinstance(hooks, dict):
        return out + [Problem("error", where, "hooks must be an object of event name to a list")]
    for event, entries in hooks.items():
        if event not in CORE_EVENTS:
            near = [e for e in CORE_EVENTS if e.lower() == event.lower()]
            if near:
                err(f"hook event {event!r} is mis-capitalised: event names are case-sensitive, did you mean {near[0]!r}? (it would silently never run)")
            else:
                warn(f"hook event {event!r} is not one of the core events; check the spelling against the hooks reference")
        if not isinstance(entries, list):
            err(f"hooks.{event} must be a list")
            continue
        for i, entry in enumerate(entries):
            tag = f"hooks.{event}[{i}]"
            if not isinstance(entry, dict) or not isinstance(entry.get("hooks"), list) or not entry["hooks"]:
                err(f"{tag} needs a non-empty 'hooks' list")
                continue
            matcher = entry.get("matcher")
            if matcher is not None:
                if not isinstance(matcher, str):
                    err(f"{tag}.matcher must be a string")
                else:
                    try:
                        re.compile(matcher)
                    except re.error:
                        err(f"{tag}.matcher {matcher!r} is not a valid pattern")
                    if " " in matcher:
                        warn(f"{tag}.matcher {matcher!r} contains a space; tool names are matched exactly")
            elif event in MATCHER_EVENTS:
                warn(f"{tag} has no matcher, so it runs for EVERY tool call")
            for j, h in enumerate(entry["hooks"]):
                htag = f"{tag}.hooks[{j}]"
                if not isinstance(h, dict) or h.get("type") not in HANDLER_TYPES:
                    err(f"{htag}.type must be one of {sorted(HANDLER_TYPES)}")
                    continue
                if "timeout" in h and (not isinstance(h["timeout"], int) or isinstance(h["timeout"], bool) or h["timeout"] <= 0):
                    err(f"{htag}.timeout must be a positive whole number of seconds")
                if h["type"] == "command":
                    cmd = h.get("command")
                    if not isinstance(cmd, str) or not cmd.strip():
                        err(f"{htag}.command is empty")
                        continue
                    for m in re.finditer(r"\$CLAUDE_PROJECT_DIR/?([\w./-]+)", cmd.replace('"', "")):
                        if not (root / m.group(1)).exists():
                            err(f"{htag} runs {m.group(1)!r}, which does not exist: the hook would silently do nothing")
    return out


def validate_skills(skills_dir: Path, root: Path) -> list[Problem]:
    out: list[Problem] = []
    for d in sorted(p for p in skills_dir.iterdir() if p.is_dir()) if skills_dir.exists() else []:
        f = d / "SKILL.md"
        where = str(f.relative_to(root)) if f.exists() else str(d.relative_to(root))
        err = lambda msg, w=where: out.append(Problem("error", w, msg))
        warn = lambda msg, w=where: out.append(Problem("warn", w, msg))
        if not f.exists():
            err("folder has no SKILL.md")
            continue
        fm, body, problem = _frontmatter(f)
        if problem:
            err(problem)
            continue
        name = fm.get("name", d.name)
        if name != d.name:
            err(f"name {name!r} must match the folder name {d.name!r}")
        if not isinstance(name, str) or not NAME.match(name) or len(name) > 64:
            err("name must be lowercase letters, digits and hyphens, at most 64 characters")
        desc = fm.get("description")
        if not isinstance(desc, str) or not desc.strip():
            err("description is required: it is how Claude decides when this skill applies")
        if "disable-model-invocation" in fm and not isinstance(fm["disable-model-invocation"], bool):
            err("disable-model-invocation must be true or false")
        if "argument-hint" in fm and "$ARGUMENTS" not in body and not re.search(r"\$\d", body):
            warn("argument-hint is set but the body never uses $ARGUMENTS")
        if not body.strip():
            err("the skill has no instructions")
        if SIDE_EFFECTS.search(body) and fm.get("disable-model-invocation") is not True and "allowed-tools" not in fm:
            err("this skill commits, deploys or migrates but can be triggered automatically: add disable-model-invocation: true")
    return out


def _tools(value) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        return [t.strip() for t in value.split(",") if t.strip()]
    if isinstance(value, list) and all(isinstance(t, str) for t in value):
        return [t.strip() for t in value]
    raise ValueError("tools must be a comma-separated string or a list")


def validate_agents(agents_dir: Path, root: Path) -> list[Problem]:
    out: list[Problem] = []
    for f in sorted(agents_dir.glob("*.md")) if agents_dir.exists() else []:
        where = str(f.relative_to(root))
        err = lambda msg, w=where: out.append(Problem("error", w, msg))
        warn = lambda msg, w=where: out.append(Problem("warn", w, msg))
        fm, body, problem = _frontmatter(f)
        if problem:
            err(problem)
            continue
        name = fm.get("name")
        if not isinstance(name, str) or not NAME.match(name):
            err("name is required: lowercase letters, digits and hyphens")
        elif name != f.stem:
            err(f"name {name!r} should match the file name {f.stem!r}")
        desc = fm.get("description")
        if not isinstance(desc, str) or not desc.strip():
            err("description is required: it is how Claude decides when to delegate")
        elif not re.search(r"\buse\b", desc, re.IGNORECASE):
            warn("description does not say WHEN to use this agent; start it with what it does and add 'Use it when ...'")
        try:
            tools = _tools(fm.get("tools"))
        except ValueError as exc:
            err(str(exc))
            tools = None
        if tools is not None:
            for t in tools:
                base = t.split("(")[0]
                if base not in KNOWN_TOOLS and not t.startswith("mcp__"):
                    err(f"unknown tool {t!r}; check the spelling (tool names are case-sensitive)")
            if re.search(r"review|audit|check", str(name), re.IGNORECASE) and WRITE_TOOLS & {t.split("(")[0] for t in tools}:
                err("a reviewer, auditor or checker must be read-only: remove the editing tools")
        else:
            warn("no tools line: the agent inherits EVERY tool; list only what it needs")
        model = fm.get("model")
        if model is not None and model not in MODEL_ALIASES and not str(model).startswith("claude-"):
            err(f"model {model!r} must be sonnet, opus, haiku, inherit, or a full model id")
        if not body.strip():
            err("the agent has no instructions")
    return out


def validate_mcp(path: Path, root: Path) -> list[Problem]:
    where = str(path.relative_to(root))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        return [Problem("error", where, f"not valid JSON: {exc}")]
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    if not isinstance(servers, dict):
        return [Problem("error", where, "needs a top-level 'mcpServers' object")]
    out: list[Problem] = []
    for name, cfg in servers.items():
        err = lambda msg, n=name: out.append(Problem("error", f"{where}:{n}", msg))
        if not isinstance(cfg, dict):
            err("server entry must be an object")
            continue
        kind = cfg.get("type")
        if "url" in cfg and kind not in ("http", "sse"):
            err("has a url but no \"type\": \"http\"; Claude Code would drop this server without telling you")
        if kind in ("http", "sse"):
            if not isinstance(cfg.get("url"), str) or not cfg["url"].startswith(("http://", "https://")):
                err("an http server needs an http(s) url")
            if kind == "sse":
                out.append(Problem("warn", f"{where}:{name}", "the sse transport is deprecated; prefer http"))
        elif kind in (None, "stdio"):
            if not isinstance(cfg.get("command"), str) or not cfg["command"]:
                err("a stdio server needs a 'command'")
            if "args" in cfg and not (isinstance(cfg["args"], list) and all(isinstance(a, str) for a in cfg["args"])):
                err("args must be a list of strings")
        else:
            err(f"unknown type {kind!r}")
        for field in ("env", "headers"):
            for key, value in (cfg.get(field) or {}).items():
                if isinstance(value, str) and SECRET.search(value) and "${" not in value:
                    err(f"{field}.{key} looks like a real secret committed to the repo; use ${{VAR}} expansion instead")
    return out


def validate_all(root: Path) -> list[Problem]:
    root = Path(root)
    problems: list[Problem] = []
    settings = root / ".claude" / "settings.json"
    if settings.exists():
        problems += validate_settings(settings, root)
    problems += validate_skills(root / ".claude" / "skills", root)
    problems += validate_agents(root / ".claude" / "agents", root)
    mcp = root / ".mcp.json"
    if mcp.exists():
        problems += validate_mcp(mcp, root)
    return problems


def main(argv: list[str]) -> int:
    root = Path(argv[0]) if argv else Path(__file__).resolve().parent.parent
    problems = validate_all(root)
    for p in problems:
        print(f"{p.severity.upper():5} {p.where}: {p.message}")
    errors = sum(p.severity == "error" for p in problems)
    print(f"{errors} error(s), {len(problems) - errors} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
