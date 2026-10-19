import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
LINTER_SCRIPT = REPO_ROOT / "tools" / "lint_opencode.py"


def run_linter(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(root / "tools" / "lint_opencode.py")],
        capture_output=True,
        text=True,
    )


class OpencodeLinterFixture(unittest.TestCase):
    """A minimal thin-pointer tree the linter passes on, broken one way per test."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

        tools = self.root / "tools"
        tools.mkdir()
        shutil.copy(LINTER_SCRIPT, tools / "lint_opencode.py")
        # The Python-test CI job does not install PyYAML; the separate lint job
        # does. This stub parses flat "key: value" frontmatter, matching
        # tests/test_lint_skills.py.
        (tools / "yaml.py").write_text(
            "class YAMLError(Exception):\n"
            "    pass\n\n"
            "def safe_load(text):\n"
            "    result = {}\n"
            "    for line in (text or '').splitlines():\n"
            "        if ':' in line:\n"
            "            key, _, value = line.partition(':')\n"
            "            result[key.strip()] = value.strip()\n"
            "    return result\n",
            encoding="utf-8",
        )

        self.opencode = self.root / "opencode.json"
        self.write_opencode()

        (self.root / "AGENTS.md").write_text("# Agent Guidelines\n", encoding="utf-8")
        command = self.root / ".claude" / "commands" / "setup.md"
        command.parent.mkdir(parents=True)
        command.write_text("# /setup - Test setup command\n", encoding="utf-8")

        agent = self.root / ".claude" / "agents" / "example.md"
        agent.parent.mkdir(parents=True)
        agent.write_text("You are an example agent.\n", encoding="utf-8")

        self.loader = self.root / ".opencode" / "command" / "setup.md"
        self.loader.parent.mkdir(parents=True)
        self.loader.write_text(
            "---\n"
            "description: Test setup loader\n"
            "---\n\n"
            "Read the canonical workflow spec at `.claude/commands/setup.md` and execute it, "
            "applying the Claude Code -> opencode mapping table in `AGENTS.md`.\n",
            encoding="utf-8",
        )

        self.agent_loader = self.root / ".opencode" / "agent" / "example.md"
        self.agent_loader.parent.mkdir(parents=True)
        self.agent_loader.write_text(
            "---\n"
            "description: Test agent loader\n"
            "mode: subagent\n"
            "---\n\n"
            "Read the canonical agent definition at `.claude/agents/example.md`.\n",
            encoding="utf-8",
        )

    def write_opencode(self, data=None):
        if data is None:
            data = {
                "$schema": "https://opencode.ai/config.json",
                "instructions": ["CLAUDE.md"],
                "skills": [".claude/skills"],
                "permission": {"bash": {"*": "ask"}},
            }
        self.opencode.write_text(json.dumps(data), encoding="utf-8")


class CleanTreeTests(OpencodeLinterFixture):
    def test_clean_tree_passes(self):
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("lint_opencode: OK", result.stdout)


class ConfigTests(OpencodeLinterFixture):
    def test_missing_schema_fails(self):
        self.write_opencode({"instructions": ["CLAUDE.md"]})
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("$schema", result.stdout)

    def test_missing_claude_md_instruction_fails(self):
        self.write_opencode(
            {
                "$schema": "https://opencode.ai/config.json",
                "instructions": [],
                "skills": [".claude/skills"],
                "permission": {"bash": {"*": "ask"}},
            }
        )
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("CLAUDE.md", result.stdout)

    def test_missing_skills_registration_fails(self):
        self.write_opencode(
            {
                "$schema": "https://opencode.ai/config.json",
                "instructions": ["CLAUDE.md"],
                "permission": {"bash": {"*": "ask"}},
            }
        )
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn(".claude/skills", result.stdout)

    def test_skills_object_form_is_accepted(self):
        self.write_opencode(
            {
                "$schema": "https://opencode.ai/config.json",
                "instructions": ["CLAUDE.md"],
                "skills": {"paths": [".claude/skills"]},
                "permission": {"bash": {"*": "ask"}},
            }
        )
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_invalid_json_fails(self):
        self.opencode.write_text("{not json", encoding="utf-8")
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("invalid JSON", result.stdout)


class CommandLoaderTests(OpencodeLinterFixture):
    def test_missing_loader_for_a_command_fails(self):
        # A command added on the Claude Code side (upstream sync) must not stay
        # invisible to opencode: the loader parity check has to flag it.
        (self.root / ".claude" / "commands" / "rank.md").write_text(
            "# /rank - Test rank command\n", encoding="utf-8"
        )
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("missing loader for .claude/commands/rank.md", result.stdout)

    def test_all_loaders_removed_fails(self):
        self.loader.unlink()
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("no command loaders found", result.stdout)

    def test_missing_spec_target_fails(self):
        self.loader.write_text(
            "---\ndescription: Broken loader\n---\n\n"
            "Read `.claude/commands/ghost.md` and apply `AGENTS.md`.\n",
            encoding="utf-8",
        )
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("references a missing canonical file", result.stdout)
        self.assertIn(".claude/commands/ghost.md", result.stdout)

    def test_loader_without_agents_mapping_pointer_fails(self):
        self.loader.write_text(
            "---\ndescription: No mapping\n---\n\n"
            "Read `.claude/commands/setup.md` and execute it.\n",
            encoding="utf-8",
        )
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("mapping table in AGENTS.md", result.stdout)

    def test_loader_duplicating_workflow_text_fails(self):
        self.loader.write_text(
            "---\ndescription: Copied body\n---\n\n"
            "Do the whole workflow inline without pointing anywhere.\n",
            encoding="utf-8",
        )
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("references no", result.stdout)

    def test_missing_description_fails(self):
        self.loader.write_text(
            "---\nagent: build\n---\n\n"
            "Read `.claude/commands/setup.md` and apply `AGENTS.md`.\n",
            encoding="utf-8",
        )
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("missing required key 'description'", result.stdout)

    def test_unknown_frontmatter_key_fails(self):
        self.loader.write_text(
            "---\ndescription: X\nallowed-tools: Bash(*)\n---\n\n"
            "Read `.claude/commands/setup.md` and apply `AGENTS.md`.\n",
            encoding="utf-8",
        )
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("unknown frontmatter key", result.stdout)

    def test_skill_backed_loader_passes(self):
        skill = self.root / ".claude" / "skills" / "scrape" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text(
            "---\nname: scrape\ndescription: Find jobs\n---\n", encoding="utf-8"
        )
        loader = self.root / ".opencode" / "command" / "scrape.md"
        loader.write_text(
            "---\ndescription: Skill loader\n---\n\n"
            "Load the `scrape` skill; canonical definition `.claude/skills/scrape/SKILL.md`.\n",
            encoding="utf-8",
        )
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_crlf_frontmatter_is_tolerated(self):
        self.loader.write_bytes(
            b"---\r\ndescription: CRLF loader\r\n---\r\n\r\n"
            b"Read `.claude/commands/setup.md` and apply `AGENTS.md`.\r\n"
        )
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class AgentLoaderTests(OpencodeLinterFixture):
    def test_missing_agent_loader_fails(self):
        self.agent_loader.unlink()
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("missing loader for .claude/agents/example.md", result.stdout)

    def test_agent_loader_without_canonical_pointer_fails(self):
        self.agent_loader.write_text(
            "---\ndescription: Inline agent\nmode: subagent\n---\n\nYou are an inline agent.\n",
            encoding="utf-8",
        )
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("does not point at a", result.stdout)

    def test_invalid_mode_fails(self):
        self.agent_loader.write_text(
            "---\ndescription: Bad mode\nmode: chatbot\n---\n\n"
            "Read `.claude/agents/example.md`.\n",
            encoding="utf-8",
        )
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("mode must be", result.stdout)


class NoSkillCopiesTests(OpencodeLinterFixture):
    def test_copied_skills_tree_fails(self):
        (self.root / ".opencode" / "skills").mkdir()
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("must not exist", result.stdout)


if __name__ == "__main__":
    unittest.main()
