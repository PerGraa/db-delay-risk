"""Seam: the claude -p command line. No test calls the CLI; the real run is checked by hand."""

from pathlib import Path

from db_delay_risk.evals.runner import RunSpec, command

ENV = Path("/tmp/eval-env")


def spec(**kw):
    return RunSpec(case_id="muc-ba", question="Munich to Bamberg?", model="haiku", skill=False, **kw)


def test_command_is_headless_isolated_and_budget_capped():
    cmd = command(spec(), ENV)

    assert cmd[:3] == ["claude", "-p", "Munich to Bamberg?"]
    for flag in ("--bare", "--strict-mcp-config", "--no-session-persistence"):
        assert flag in cmd
    assert cmd[cmd.index("--output-format") + 1] == "stream-json"
    assert cmd[cmd.index("--tools") + 1] == ""  # no built-in tools: only the MCP server
    assert cmd[cmd.index("--model") + 1] == "haiku"
    assert float(cmd[cmd.index("--max-budget-usd") + 1]) <= 1.0
    assert cmd[cmd.index("--mcp-config") + 1] == str(ENV / "mcp.json")


def test_only_the_four_mcp_tools_are_allowed():
    cmd = command(spec(), ENV)

    allowed = cmd[cmd.index("--allowedTools") + 1 : cmd.index("--allowedTools") + 5]
    assert sorted(allowed) == sorted(
        f"mcp__db-delay-risk__{t}" for t in ("find_station", "route_options", "trip_risk", "connection_risk")
    )


def test_skill_variant_loads_the_plugin_and_invokes_the_skill():
    with_skill = command(spec().with_skill(), ENV)
    without = command(spec(), ENV)

    assert with_skill[2] == "/rail-skill:analyzing-rail-delay-risk Munich to Bamberg?"
    assert with_skill[with_skill.index("--plugin-dir") + 1] == str(ENV / "plugin")
    assert "--plugin-dir" not in without


def test_effort_is_passed_only_when_set():
    assert "--effort" not in command(spec(), ENV)
    cmd = command(spec(effort="low"), ENV)
    assert cmd[cmd.index("--effort") + 1] == "low"
