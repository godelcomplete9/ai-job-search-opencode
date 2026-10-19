---
framework_version: 1.0.0
---

# Agent Guidelines: AI Job Search

This workspace is structured to manage job search activities, scraper tools, CVs, cover letters, and interview preparation.

## Thin-Pointer Design (Single Source of Truth)

To prevent duplication and configuration drift across different AI agent frameworks (Claude Code, Google Antigravity, Codex, Cursor, Gemini CLI, etc.), this workspace uses a unified thin-pointer design. All agent runtimes should load the canonical specifications and candidate profiles from the files and directories below:

1. **Personal Candidate Profile:**
   - The candidate profile, contact details, education, and target preferences are defined in [CLAUDE.md](CLAUDE.md) and the individual profile methodology files under [.claude/skills/job-application-assistant/](.claude/skills/job-application-assistant/) (specifically `01-*.md` etc.).
2. **Canonical Workflow Specifications:**
   - The step-by-step instructions and triggers for tasks (setup, scrape, rank, apply, upskill, interview) are defined in the [.claude/](.claude/) directory (specifically under `.claude/skills/` and `.claude/commands/`).
   - Do not duplicate these rules or specifications. Treat `.claude/` files as the single source of truth.
3. **Portal Search Skills:**
   - Job-portal search CLIs live under [.agents/skills/](.agents/skills/) in the portable Agent Skills format (with a `SKILL.md` per portal). Codex and Antigravity discover these automatically; the `/scrape` workflow in [.claude/skills/job-scraper/](.claude/skills/job-scraper/) orchestrates them.

## opencode Runtime

opencode is a first-class runtime for this workspace alongside Claude Code. The wiring is deliberately thin, so the canonical files above stay the only source of truth:

- [opencode.json](opencode.json) (project root) is the opencode config: it loads `CLAUDE.md` via `instructions`, registers `.claude/skills` via `skills.paths`, and mirrors the Claude Code bash allowlist from `.claude/settings.json` under `permission.bash`.
- `.opencode/command/*.md` are thin slash-command loaders. Each reads the matching canonical spec in `.claude/commands/` and executes it. Never copy workflow text into them - they contain only a description, the pointer, and the opencode runtime mapping.
- `.opencode/agent/*.md` are thin subagent loaders over `.claude/agents/`.
- Skills are auto-discovered from `.claude/skills/` and `.agents/skills/`; the `/scrape` and `/upskill` loaders hand off to the skill tool.
- `tools/lint_opencode.py` (CI) keeps the loaders, the config, and the canonical files in lockstep; `tools/security_guards.py` audits `opencode.json` the same way it audits `.claude/settings.json`.

### Claude Code -> opencode tool mapping

When executing a canonical spec written for Claude Code under opencode, translate tool names:

| Claude Code | opencode |
|-------------|----------|
| WebFetch | `webfetch` tool |
| WebSearch | `websearch` tool |
| Read / Write / Edit | `read` / `write` / `edit` tools |
| Glob / Grep | `glob` / `grep` tools |
| Bash | `bash` tool |
| Agent tool spawning a `general-purpose` subagent | `task` tool with `subagent_type: "general"` |
| AskUserQuestion | `question` tool |
| Skill tool | `skill` tool |
| `mcp__notion__*` (Notion MCP) | Notion MCP server in `opencode.json` (`mcp`) with OAuth - see [OPENCODE.md](OPENCODE.md) |
| `mcp__claude_ai_Gmail__*` (hosted Gmail connector) | no equivalent - needs a user-configured Gmail MCP server; see [OPENCODE.md](OPENCODE.md) |

`.claude/...` file paths are canonical in every runtime - read them as-is. See [OPENCODE.md](OPENCODE.md) for the full migration guide, config reference, and known parity gaps.
