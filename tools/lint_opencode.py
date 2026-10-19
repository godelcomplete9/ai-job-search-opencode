#!/usr/bin/env python3
"""Lint the opencode wiring that makes this repo runnable under opencode.

Run from anywhere: python tools/lint_opencode.py

This repo keeps every workflow specification in .claude/ (the single source of
truth - see AGENTS.md). opencode is wired to those specs through thin loaders.
This lint keeps the three layers in lockstep:

Checks:
- opencode.json parses, declares $schema, loads CLAUDE.md via `instructions`,
  and registers .claude/skills via `skills`
- Every .opencode/command/*.md has YAML frontmatter with a non-empty
  `description`, only known frontmatter keys, and a body that is a thin
  pointer: it references an existing canonical file under .claude/ (a command
  spec or a skill), never duplicating workflow text
- Command loaders that wrap .claude/commands specs also point at the
  Claude Code -> opencode mapping table in AGENTS.md
- Every .claude/commands/*.md has a matching .opencode/command/<name>.md
  loader, so a command added upstream cannot silently stay invisible to
  opencode
- Every .opencode/agent/*.md points at an existing .claude/agents/*.md
  definition, and every .claude/agents/*.md has a loader
- No .opencode/skills/ or .opencode/skill/ tree exists - skills are canonical
  in .claude/skills/ and .agents/skills/; a copy here would drift and double-load

Exit code 0 on success, 1 with a failure list otherwise.
"""

import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("lint_opencode.py requires PyYAML: pip install pyyaml")

ROOT = Path(__file__).resolve().parent.parent
errors: list[str] = []

COMMAND_FRONTMATTER_KEYS = {"description", "agent", "model", "variant", "subtask"}
AGENT_FRONTMATTER_KEYS = {
    "name",
    "model",
    "variant",
    "description",
    "mode",
    "hidden",
    "color",
    "steps",
    "options",
    "permission",
    "disable",
    "temperature",
    "top_p",
}
CLAUDE_PATH_RE = re.compile(r"`(\.claude/[\w./-]+\.md)`")


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def parse_frontmatter(path: Path):
    """Return (data, error). data is None when the frontmatter is unusable."""
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    if not text.startswith("---\n"):
        return None, "missing YAML frontmatter (file must start with ---)"
    end = text.find("\n---", 4)
    if end == -1:
        return None, "unterminated YAML frontmatter"
    try:
        data = yaml.safe_load(text[4:end])
    except yaml.YAMLError as exc:
        return None, f"frontmatter is not valid YAML: {exc}"
    if not isinstance(data, dict):
        return None, "frontmatter did not parse to a mapping"
    return data, None


def body_of(path: Path) -> str:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    end = text.find("\n---", 4)
    return text[end + 4 :] if end != -1 else text


def check_opencode_json() -> None:
    path = ROOT / "opencode.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"opencode.json: unreadable or invalid JSON: {exc}")
        return
    if not isinstance(data, dict):
        errors.append("opencode.json: top-level JSON value must be an object")
        return
    if data.get("$schema") != "https://opencode.ai/config.json":
        errors.append(
            "opencode.json: $schema must be https://opencode.ai/config.json "
            "(editors validate against it and opencode accepts unknown fields nowhere else)"
        )

    instructions = data.get("instructions")
    if not isinstance(instructions, list) or "CLAUDE.md" not in instructions:
        errors.append(
            "opencode.json: `instructions` must be a list including CLAUDE.md - "
            "the candidate profile is not ambient without it"
        )

    skills = data.get("skills")
    if isinstance(skills, list):
        skill_paths = skills
    elif isinstance(skills, dict):
        skill_paths = skills.get("paths", [])
    else:
        skill_paths = None
    if not isinstance(skill_paths, list) or ".claude/skills" not in skill_paths:
        errors.append(
            "opencode.json: `skills` must register .claude/skills so the canonical "
            "skills load even on opencode versions that do not auto-discover them"
        )

    bash = data.get("permission", {}).get("bash", {}) if isinstance(data.get("permission"), dict) else {}
    if not isinstance(bash, dict) or not bash:
        errors.append("opencode.json: permission.bash must be a non-empty rule object")


def check_command_loaders() -> list[Path]:
    wrap_dir = ROOT / ".opencode" / "command"
    wrappers = sorted(wrap_dir.glob("*.md")) if wrap_dir.is_dir() else []
    if not wrappers:
        errors.append(".opencode/command: no command loaders found - opencode would offer no slash commands")
        return wrappers

    for wrapper in wrappers:
        data, err = parse_frontmatter(wrapper)
        if err:
            errors.append(f"{rel(wrapper)}: {err}")
            continue
        unknown = set(data) - COMMAND_FRONTMATTER_KEYS
        if unknown:
            errors.append(f"{rel(wrapper)}: unknown frontmatter key(s): {sorted(unknown)}")
        if not data.get("description"):
            errors.append(f"{rel(wrapper)}: frontmatter missing required key 'description'")

        body = body_of(wrapper)
        refs = CLAUDE_PATH_RE.findall(body)
        if not refs:
            errors.append(
                f"{rel(wrapper)}: body references no `.claude/...md` canonical file - "
                "loaders must point at the spec instead of duplicating workflow text"
            )
            continue
        for ref in refs:
            if not (ROOT / ref).is_file():
                errors.append(f"{rel(wrapper)}: references a missing canonical file: {ref}")

        spec_ref = f".claude/commands/{wrapper.stem}.md"
        if spec_ref in refs:
            if "AGENTS.md" not in body:
                errors.append(
                    f"{rel(wrapper)}: wraps {spec_ref} but does not point at the Claude Code -> "
                    "opencode mapping table in AGENTS.md"
                )
        elif not any(ref.startswith(".claude/skills/") and ref.endswith("/SKILL.md") for ref in refs):
            errors.append(
                f"{rel(wrapper)}: must either wrap `.claude/commands/{wrapper.stem}.md` "
                "or load a `.claude/skills/*/SKILL.md` skill"
            )

    command_names = {p.stem for p in (ROOT / ".claude" / "commands").glob("*.md")}
    loader_names = {p.stem for p in wrappers}
    for missing in sorted(command_names - loader_names):
        errors.append(
            f".opencode/command/{missing}.md: missing loader for .claude/commands/{missing}.md - "
            "add a thin loader when a command is added upstream"
        )
    return wrappers


def check_agent_loaders() -> None:
    wrap_dir = ROOT / ".opencode" / "agent"
    wrappers = sorted(wrap_dir.glob("*.md")) if wrap_dir.is_dir() else []
    for wrapper in wrappers:
        data, err = parse_frontmatter(wrapper)
        if err:
            errors.append(f"{rel(wrapper)}: {err}")
            continue
        unknown = set(data) - AGENT_FRONTMATTER_KEYS
        if unknown:
            errors.append(f"{rel(wrapper)}: unknown frontmatter key(s): {sorted(unknown)}")
        if not data.get("description"):
            errors.append(f"{rel(wrapper)}: frontmatter missing required key 'description'")
        mode = data.get("mode")
        if mode is not None and mode not in {"primary", "subagent", "all"}:
            errors.append(f"{rel(wrapper)}: mode must be primary, subagent, or all (found: {mode!r})")

        body = body_of(wrapper)
        refs = CLAUDE_PATH_RE.findall(body)
        if not any(ref.startswith(".claude/agents/") for ref in refs):
            errors.append(
                f"{rel(wrapper)}: does not point at a `.claude/agents/*.md` definition - "
                "agent loaders must reference the canonical prompt"
            )
        for ref in refs:
            if not (ROOT / ref).is_file():
                errors.append(f"{rel(wrapper)}: references a missing canonical file: {ref}")

    agent_names = {p.stem for p in (ROOT / ".claude" / "agents").glob("*.md")}
    loader_names = {p.stem for p in wrappers}
    for missing in sorted(agent_names - loader_names):
        errors.append(
            f".opencode/agent/{missing}.md: missing loader for .claude/agents/{missing}.md"
        )


def check_no_skill_copies() -> None:
    for dup in (".opencode/skills", ".opencode/skill"):
        if (ROOT / dup).exists():
            errors.append(
                f"{dup}/ must not exist - skills are canonical in .claude/skills/ and "
                ".agents/skills/ and auto-discovered by opencode; a copy here would drift"
            )


def main() -> int:
    check_opencode_json()
    check_command_loaders()
    check_agent_loaders()
    check_no_skill_copies()

    if errors:
        print(f"lint_opencode: {len(errors)} failure(s)")
        for err in errors:
            print(f"  - {err}")
        return 1
    command_count = len(list((ROOT / ".opencode" / "command").glob("*.md")))
    agent_count = len(list((ROOT / ".opencode" / "agent").glob("*.md")))
    print(
        f"lint_opencode: OK (opencode.json, {command_count} command loaders, "
        f"{agent_count} agent loaders, no skill copies)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
