# Evals run through headless Claude Code, isolated per run

The evals measure the *shipped* artifact: the MCP server plus the skill as Claude Code uses them. So they run `claude -p` rather than calling the Messages API directly. Each run is isolated so that "with skill" and "without skill" differ in exactly one thing:

- `--bare`: no user CLAUDE.md, hooks, auto-memory or keychain auth.
- A separate `CLAUDE_CONFIG_DIR`: none of the user's installed plugins or skills.
- `--strict-mcp-config` with a generated `mcp.json`: only this project's MCP server.
- `--tools ""` plus `--allowedTools` for the four MCP tools: no Bash or file access.
- `--permission-mode dontAsk`, `--no-session-persistence`, and `--max-budget-usd 1` per run.

The skill variant loads the skill as a temporary plugin (`--plugin-dir`) and invokes it explicitly (`/rail-skill:analyzing-rail-delay-risk <question>`). Under `--bare`, project skills are not discovered, and the model was not observed to load the plugin skill by itself. Authentication comes from a settings file that holds only the auth helper, kept outside the repo.

## Considered Options

- **Messages API with our own tool loop.** Full control and an API key, but it would test a re-implementation, not what a user runs.
- **Interactive sessions by hand.** That is how the first findings came about, but it cannot be repeated across models and repeats.

## Consequences

Checks are deterministic code over the stream-json transcript (scope stated, numbers traceable to tool output, anecdotal options kept out of the table, reliable options mentioned, no raw ids). Judgement questions, such as whether the recommendation follows from the numbers, are not covered yet. The report ends with the token usage and cost of the whole run, taken from the CLI's own `total_cost_usd`. The cost is the list price the CLI reports; what is actually billed depends on the account.
