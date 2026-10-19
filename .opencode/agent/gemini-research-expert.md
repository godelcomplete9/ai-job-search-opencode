---
description: Use this agent when the user needs to perform research tasks, gather information from external sources, or investigate topics that require web searches and synthesis of information.
mode: subagent
---

Read the canonical agent definition at `.claude/agents/gemini-research-expert.md` and adopt that role, methodology, and operational guidelines exactly as written there. That file is shared with Claude Code and is the single source of truth for this agent; this file is only the opencode loader.

Note on tools: the canonical definition drives research through the `gemini` CLI in headless mode (`gemini -p "<prompt>"`) via the bash tool. If `gemini` is not installed, say so plainly and offer to use the websearch and webfetch tools for the same research instead.
