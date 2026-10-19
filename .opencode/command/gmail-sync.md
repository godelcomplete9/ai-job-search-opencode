---
description: Read Gmail for status signals on your open applications and propose tracker updates for approval. Requires a Gmail MCP server configured in opencode (see OPENCODE.md).
---

Read the canonical workflow spec at `.claude/commands/gmail-sync.md` and execute it exactly as written, treating the text below as that spec's `$ARGUMENTS` input. Where the spec names Claude Code tools, apply the Claude Code -> opencode mapping table in `AGENTS.md`.

Runtime note (opencode): the spec's preflight checks for the hosted Claude.ai Gmail connector (`mcp__claude_ai_Gmail__*`), which does not exist in opencode. Instead, check which Gmail MCP tools are present in this session's tool list (`gmail*` or `mcp__gmail*` or similar) and use those for the reads the spec describes. If no Gmail MCP server is connected, stop with the one-line graceful exit, telling the user to configure a Gmail MCP server in `opencode.json` (and pointing at the Gmail section of `OPENCODE.md`) - never attempt IMAP or Bash-based mailbox access.

$ARGUMENTS
