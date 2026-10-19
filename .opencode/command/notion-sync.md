---
description: Publish a one-way, read-only view of the pipeline to a Notion database via the Notion MCP server (OAuth).
---

Read the canonical workflow spec at `.claude/commands/notion-sync.md` and execute it exactly as written, treating the text below as that spec's `$ARGUMENTS` input. Where the spec names Claude Code tools, apply the Claude Code -> opencode mapping table in `AGENTS.md`.

Runtime note (opencode): the spec's preflight instructs the user to run `claude mcp add ...` and `/mcp`. In opencode, the Notion MCP server is a remote MCP server configured in `opencode.json` (see the Notion section of `OPENCODE.md` for the exact block), OAuth is completed on first use, and the shell command is `opencode mcp add`. If the Notion MCP tools are not available in this session, stop with the spec's graceful one-liner, adapted to the opencode instructions.

$ARGUMENTS
