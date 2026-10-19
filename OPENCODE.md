# Running AI Job Search on opencode

[opencode](https://opencode.ai) is a first-class runtime for this fork alongside
Claude Code. The wiring is deliberately thin: every canonical workflow
specification, skill, agent definition, and the candidate profile stay in
`CLAUDE.md` and `.claude/` exactly as upstream ships them, and opencode reads
them from there. This document explains the wiring, the per-command behavior,
the security model, and - in the [parity section](#what-could-not-be-replicated)
- the handful of Claude Code features that have no opencode equivalent.

Nothing here changes the Claude Code setup: the same repo still runs under
`claude`, and the two runtimes can be used side by side on the same clone.

## Quick start

1. Install opencode and this fork ([SETUP.md section 1](SETUP.md#1-prerequisites),
   [README quick start](README.md#quick-start)).
2. Install the portal CLIs:

   ```bash
   python3 tools/install_portal_clis.py   # Windows: python tools\install_portal_clis.py
   ```

3. Start opencode in the repo root and run the same commands as before:

   ```
   /setup
   /scrape
   /apply <url>
   ```

`opencode debug config` prints the resolved configuration if a command is not
showing up, and `opencode debug skill` / `opencode debug agent` list what was
loaded.

## What is where

The single-source-of-truth rule from [AGENTS.md](AGENTS.md) applies: opencode
files are loaders, never copies.

| Path | Role | Runtime |
|------|------|---------|
| `opencode.json` | opencode config: instructions, skills path, bash permission allowlist | opencode |
| `.opencode/command/*.md` | Thin slash-command loaders; each points at its `.claude/commands/*.md` spec | opencode |
| `.opencode/agent/gemini-research-expert.md` | Thin subagent loader over `.claude/agents/gemini-research-expert.md` | opencode |
| `CLAUDE.md`, `.claude/commands/`, `.claude/skills/`, `.claude/agents/`, `.claude/settings.json` | Canonical profile, workflows, skills, agents, and Claude Code permissions | both |
| `AGENTS.md` | Cross-runtime onboarding + the Claude Code -> opencode tool mapping table | all runtimes |
| `.agents/skills/*/cli/` | Portal search CLIs (unchanged; run under `bun` in either runtime) | both |
| `tools/lint_opencode.py`, `tools/security_guards.py` | CI checks that keep the loaders, config, and allowlists honest | CI |

## How the wiring works

### `opencode.json`

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "instructions": ["CLAUDE.md"],       // the candidate profile + workflow rules
  "skills": [".claude/skills"],        // project skills, upstream location
  "permission": {
    "bash": {
      "*": "ask",                      // everything not listed below prompts
      "bun run .agents/skills/jobbank-search/cli/src/cli.ts*": "allow",
      // ... one line per portal CLI (six shipped) ...
      "python3 tools/rank_state.py*": "allow",
      "python3 tools/job_key.py*": "allow",
      "python3 tools/verify_pdf.py*": "allow",
      "python3 tools/verify_layout.py*": "allow",
      "python salary_lookup.py*": "allow",
      "pdftotext*": "allow"
    }
  }
}
```

- `instructions` loads `CLAUDE.md`; opencode additionally picks up `AGENTS.md`
  natively as project rules.
- `skills` is pinned explicitly even though opencode 1.18+ also auto-discovers
  project `.claude/skills/` and `.agents/skills/`: the explicit path keeps the
  wiring from silently depending on discovery behavior (opencode dedupes, so
  nothing loads twice).
- The `permission.bash` allowlist mirrors `.claude/settings.json` one-for-one -
  the same 17 reviewed patterns. See [Permissions & security](#permissions--security).

### Command loaders (`.opencode/command/`)

opencode does not read command definitions from `.claude/commands/`, so each
canonical command has a thin loader in `.opencode/command/` with the same name.
A loader contains only:

1. a one-line `description`,
2. an instruction to read the canonical spec at `.claude/commands/<name>.md`
   and execute it exactly as written, applying the tool mapping table in
   `AGENTS.md`,
3. for skills exposed as slash commands (`/scrape`, `/upskill`), a pointer to
   the canonical `SKILL.md` plus the skill name to load,
4. runtime notes where the spec itself contains Claude-Code-specific steps
   (`/gmail-sync`, `/notion-sync`, see below).

Workflow text is never copied into a loader. `tools/lint_opencode.py` fails CI
if a loader stops pointing at an existing canonical file, if the mapping-table
pointer disappears, or if a canonical command lacks a loader (so upstream
additions cannot silently go missing on opencode).

### Shipped commands

All 14 commands work on opencode (`/setup` through `/reset`, including the
skill-backed `/scrape` and `/upskill`):

`/setup`, `/scrape`, `/apply`, `/rank`, `/expand`, `/outcome`, `/interview`,
`/html-report`, `/gmail-sync`*, `/notion-sync`, `/add-template`, `/add-portal`,
`/reset`, `/upskill`.

\* `/gmail-sync` requires a Gmail MCP server on opencode - see
[Gmail](#gmail-the-hosted-connector-gap).

### Agents

`.opencode/agent/gemini-research-expert.md` is a subagent loader for the
canonical `.claude/agents/gemini-research-expert.md`. Inline agents spawned by
workflows (`/apply`'s reviewer, `/rank`'s scoring agents) are dispatched with
opencode's `task` tool (`subagent_type: general`) per the mapping table in
`AGENTS.md` - no per-agent loader is needed for those.

### Skills

The nine skills (job-application-assistant + methodology files, job-scraper,
upskill, and the six portal skills) load via opencode's `skill` tool from
`.claude/skills/` and `.agents/skills/`. Skill-backed slash commands
(`/scrape`, `/upskill`) go through the command loaders, which load the skill
explicitly. `/add-portal`-generated portal skills are auto-discovered the same
way - no loader needed, since portal skills are model-invoked rather than
slash commands.

## Permissions & security

The security posture is the same as the Claude Code side, expressed in
opencode's config format:

- **`"*": "ask"`** - every shell command not on the reviewed allowlist prompts
  before running (same default as Claude Code's `ask` fallback).
- **17 reviewed allowlist entries** - copied from `.claude/settings.json`:
  the six portal CLI invocations (`bun run .agents/skills/<portal>/cli/src/cli.ts*`),
  `salary_lookup.py`, `tools/rank_state.py`, `tools/job_key.py`,
  `tools/verify_pdf.py`, `tools/verify_layout.py` (each `python` and `python3`
  forms), and `pdftotext*`.
- **No plugins, no MCP servers by default** - `opencode.json` ships with none.
- **CI enforcement** - `tools/security_guards.py` audits `opencode.json` the
  same way it audits `.claude/settings.json`: it fails on any bash allow
  pattern outside the reviewed set, on a wildcard allow (`"*": "allow"`), and
  on any `plugin` or `mcp` entry not on the reviewed allowlists (both are
  empty by design - additions require a conscious edit to the guard, which is
  the review checkpoint).

If you personalize your own fork and want a new portal pre-approved, edit
**both** `opencode.json` and `OPENCODE_ALLOWED_BASH` in
`tools/security_guards.py`; otherwise leave it off the allowlist and approve
the prompt when it appears.

## MCP integrations

### Notion (reproducible)

`/notion-sync` works on opencode through the same remote Notion MCP server
(`https://mcp.notion.com/mcp`), configured in `opencode.json`:

```jsonc
{
  "mcp": {
    "notion": {
      "type": "remote",
      "url": "https://mcp.notion.com/mcp"
    }
  }
}
```

OAuth runs on first use (`opencode mcp auth notion` to trigger or redo it;
`opencode mcp list` shows status). Adding this block is a personal-fork change:
also add `"notion"` to `OPENCODE_ALLOWED_MCP_SERVERS` in
`tools/security_guards.py` if you push it. The `/notion-sync` loader already
adapts the spec's `claude mcp add` preflight to these opencode instructions;
tool names differ (`mcp__notion__...` vs opencode's naming) and the spec
already allows for that.

### Gmail: the hosted-connector gap

`/gmail-sync` on Claude Code uses the claude.ai **hosted** Gmail connector
(`mcp__claude_ai_Gmail__*`) - an account-level feature of the Claude apps with
no opencode equivalent. opencode can run `/gmail-sync` only if you configure
*your own* Gmail MCP server (a local/remote MCP process you trust and
maintain; there is no vetted, shipped option here). The loader's runtime note
makes the command check for Gmail MCP tools in the session and exit gracefully
with instructions if none are connected - it never falls back to IMAP or Bash
mailbox access. If you don't want to run a Gmail MCP server, run that one
command under Claude Code, or skip `/gmail-sync` and log outcomes manually via
`/outcome`.

## What could not be replicated

A complete, honest list of Claude Code capabilities this fork uses that
opencode does not have, and what was done instead. Everything not listed here
is fully replicated.

1. **Hosted Gmail connector** (`mcp__claude_ai_Gmail__*`). Account-level
   Claude feature; no equivalent. Mitigation: `/gmail-sync` loader detects
   available Gmail MCP tools and degrades gracefully (see above).

2. **Skill-level tool restrictions (`allowed-tools:` frontmatter).** Claude
   Code constrains a skill to its declared tools. opencode loads skills but
   does not enforce per-skill tool scoping - tool access is governed by the
   session's permissions. Mitigation: the prompt-first `permission.bash`
   posture above covers the shell surface; the skills' `allowed-tools` lines
   remain in place for the Claude Code runtime and as documentation.

3. **`context: fork` for skills.** Claude Code can run a skill in an isolated
   forked context; opencode has no per-skill context isolation. Skills run in
   the session context. Where isolation matters (bulk scoring, review
   passes), the workflow already dispatches `task` subagents, which are
   isolated. The frontmatter line is simply ignored on opencode.

4. **Skills as native slash commands.** Claude Code exposes skills directly
   as `/scrape`, `/upskill`; opencode's skills are model-invoked via the
   `skill` tool. Mitigation: thin command loaders restore the slash UX. A
   user-added skill (beyond `/scrape`/`/upskill`) would be model-invoked
   only, unless a loader is added.

5. **Hooks.** This repo ships no hooks (and `security_guards.py` rejects
   non-allowlisted ones), so nothing is lost today. If upstream ever adds a
   Claude Code hook, the opencode analog is a plugin - not automatically
   translated, and `lint_opencode.py` will not create one; a follow-up change
   would be needed, gated by the plugin allowlist in the guard.

6. **PDF visual inspection depends on the model, not opencode.** `/apply`
   requires visually inspecting the compiled PDF. opencode supports PDF/image
   attachments when the selected model does; a text-only model (e.g. some
   local/provider models - the local `freetoken` provider's model declares
   `attachment: false`) cannot do the visual pass. Mitigation:
   `tools/verify_layout.py` measures layout programmatically (holes, orphans,
   footer collisions) and `verify_pdf.py` checks page count/text, but the
   mandatory visual checklist is a hard requirement of `/apply` and needs a
   vision/PDF-capable model.

7. **Claude-specific runtime commands inside specs.** `/notion-sync`'s
   `claude mcp add` / `/mcp` preflight and `/gmail-sync`'s connector check are
   Claude Code mechanics. The opencode wrappers override exactly those
   lines; the rest of each spec is model-level guidance that runs as written.

8. **Subagent dispatch mechanics.** `Agent` tool + `general-purpose` becomes
   `task` + `general`. Parallel dispatch in `/rank` maps to parallel `task`
   calls; nesting depth is subject to opencode's default subagent depth (1),
   which matches what the workflows need.

9. **WebFetch behavior details.** Claude Code's WebFetch has its own user
   agent and robots handling. opencode's `webfetch` differs in details. The
   escalation ladder in `09-web-research.md` (portal CLI -> webfetch -> curl
   with browser headers -> employer site) still applies, but site-specific
   403 behavior may differ between runtimes.

10. **Machine-local permission overrides.** Claude Code has
    `.claude/settings.local.json` (gitignored, per-clone). The opencode analog
    is the global `~/.config/opencode/opencode.json`, which is outside the
    repo - equally personal, different scope. Per-project opencode changes go
    in this repo's `opencode.json` and are guard-checked.

11. **Model-level prompt adherence.** The specs are tuned for Claude models.
    opencode can run them on other providers; portal search skills are
    provider-independent (upstream supports Codex/Antigravity for those), but
    long multi-step workflows like `/apply` reward a strong instruction-following
    model. Pick your model accordingly; this is a model property, not an
    opencode limitation.

12. **`CLAUDE.md` content mentions.** The candidate-profile instructions
    reference "Claude Code" by name in one place (agentic-coding experience
    phrasing). That is profile content, not runtime behavior; it stays
    upstream-compatible. Personalize it if your own experience differs.

## Maintenance

- **Upstream sync.** Pull upstream as usual (SETUP.md section 8). The
  canonical `.claude/` files update freely; if upstream adds or renames a
  command, `python3 tools/lint_opencode.py` fails until a matching loader
  exists - by design, so opencode never silently misses a workflow. New
  skills auto-load; new agents need a loader.
- **Adding a portal** (`/add-portal` or copying one from another fork): the
  CLI and skill are picked up automatically. The first `bun run` prompts
  unless you add the new path to `opencode.json` + `security_guards.py`.
- **Adding an MCP server** (e.g. Notion, a Gmail server): add it to
  `opencode.json` and to the appropriate allowlist in `tools/security_guards.py`,
  then run the guard.
- **CI parity.** `.github/workflows/ci.yml` runs `tools/lint_skills.py`,
  `tools/lint_opencode.py`, and `tools/security_guards.py` plus the unit
  tests, so a fork that breaks the thin-pointer wiring fails loudly.

## Troubleshooting

- **A command doesn't appear:** `opencode debug config` (config resolved?)
  and check the loader exists in `.opencode/command/`. Run
  `python3 tools/lint_opencode.py`.
- **A skill doesn't load:** `opencode debug skill`; confirm the skill file is
  under `.claude/skills/` or `.agents/skills/` with valid frontmatter.
- **Repeated permission prompts for a portal you trust:** add the exact
  pattern to `opencode.json` and `OPENCODE_ALLOWED_BASH` (guard-checked).
- **`/gmail-sync` exits immediately:** expected without a Gmail MCP server -
  see the Gap section.
- **Notion tools missing:** `opencode mcp list`; add the config block above
  and authenticate once.
- **PDF checks fail while the PDF looks fine:** the visual pass needs a
  vision/PDF-capable model; `python3 tools/verify_layout.py` gives the
  programmatic measurements.

## FAQ

- **Do I need Claude Code too?** No, for everything except the hosted Gmail
  connector path.
- **Are the two runtimes compatible on one clone?** Yes - state lives in
  repo-local files (`job_scraper/`, `job_search_tracker.csv`, drafts), and
  neither runtime modifies the other's config.
- **Which one should I use?** Claude Code is the upstream-tested runtime;
  opencode is fully wired and CI-checked. Use whichever you prefer - the
  canonical files are shared, so you can switch or mix per command.
