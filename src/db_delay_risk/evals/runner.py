"""Run eval cases through Claude Code in headless mode (`claude -p`).

Each run is isolated: `--bare` skips the user's CLAUDE.md, hooks and auto-memory;
`--strict-mcp-config` loads only this project's MCP server; `--tools ""` removes all
built-in tools; a separate CLAUDE_CONFIG_DIR keeps installed plugins out. The skill
variant loads the skill as a plugin and invokes it explicitly, so "with skill" and
"without skill" differ in exactly one thing. See ADR 0011.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path

from db_delay_risk.evals.transcript import MCP_PREFIX

TOOLS = ("find_station", "route_options", "trip_risk", "connection_risk")
PLUGIN = "rail-skill"
SKILL = "analyzing-rail-delay-risk"
MAX_BUDGET_USD = 1.0  # hard cap per run; a normal run costs well under $0.10


@dataclass(frozen=True)
class RunSpec:
    case_id: str
    question: str
    model: str
    skill: bool
    effort: str | None = None
    repeat: int = 0

    def with_skill(self) -> RunSpec:
        return replace(self, skill=True)

    @property
    def run_id(self) -> str:
        variant = "skill" if self.skill else "noskill"
        effort = f"-{self.effort}" if self.effort else ""
        return f"{self.case_id}__{self.model}{effort}__{variant}__r{self.repeat}"


def command(spec: RunSpec, env_dir: Path) -> list[str]:
    prompt = f"/{PLUGIN}:{SKILL} {spec.question}" if spec.skill else spec.question
    cmd = [
        "claude",
        "-p",
        prompt,
        "--bare",
        "--model",
        spec.model,
        "--tools",
        "",
        "--allowedTools",
        *(MCP_PREFIX + t for t in TOOLS),
        "--strict-mcp-config",
        "--mcp-config",
        str(env_dir / "mcp.json"),
        "--settings",
        str(env_dir / "settings.json"),
        "--permission-mode",
        "dontAsk",
        "--no-session-persistence",
        "--output-format",
        "stream-json",
        "--verbose",
        "--max-budget-usd",
        str(MAX_BUDGET_USD),
    ]
    if spec.skill:
        cmd += ["--plugin-dir", str(env_dir / "plugin")]
    if spec.effort:
        cmd += ["--effort", spec.effort]
    return cmd


def prepare_env(env_dir: Path, project_dir: Path, db_file: Path, settings_file: Path) -> None:
    """Write the isolated run environment: MCP config, plugin wrapping the skill, settings, config dir.

    `settings_file` supplies only authentication (e.g. apiKeyHelper) and is copied as is.
    """
    env_dir.mkdir(parents=True, exist_ok=True)
    (env_dir / "config").mkdir(mode=0o700, exist_ok=True)
    (env_dir / "work").mkdir(exist_ok=True)
    mcp = {
        "mcpServers": {
            "db-delay-risk": {
                "type": "stdio",
                "command": "uv",
                "args": ["run", "--directory", str(project_dir), "db-delay-risk-mcp"],
                "env": {"DB_DELAY_RISK_DB": str(db_file)},
            }
        }
    }
    (env_dir / "mcp.json").write_text(json.dumps(mcp, indent=2))
    plugin = env_dir / "plugin"
    if plugin.exists():
        shutil.rmtree(plugin)
    (plugin / ".claude-plugin").mkdir(parents=True)
    (plugin / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": PLUGIN, "version": "0.0.0", "description": "Eval wrapper for the skill"})
    )
    # A copy, not a symlink: the CLI does not follow symlinked skill directories.
    shutil.copytree(project_dir / ".claude" / "skills" / SKILL, plugin / "skills" / SKILL)
    target = env_dir / "settings.json"
    shutil.copyfile(settings_file, target)
    target.chmod(0o600)


def run(spec: RunSpec, env_dir: Path, out_dir: Path, timeout_s: int = 600) -> Path:
    """Run one spec and store its raw stream-json transcript. Returns the transcript path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{spec.run_id}.jsonl"
    env = {**os.environ, "CLAUDE_CONFIG_DIR": str(env_dir / "config")}
    proc = subprocess.run(
        command(spec, env_dir),
        cwd=env_dir / "work",
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout_s,
        check=False,
    )
    out.write_text(proc.stdout)
    return out
