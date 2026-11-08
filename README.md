# db-delay-risk

How reliable has a Deutsche Bahn trip been, and is there a slower route that is safer? An **MCP server** and an **agent skill** that let Claude answer that from six months of open data on observed train stops. An **eval harness** measures whether the skill actually makes the answers better.

> **Not affiliated with Deutsche Bahn.** Data: Deutsche Bahn, CC BY 4.0, collected by [piebro/deutsche-bahn-data](https://github.com/piebro/deutsche-bahn-data).

## Why

Deutsche Bahn's long-distance trains have gotten considerably less reliable, dropping from a [~75% punctuality rate in 2015 to ~60% in 2025](https://tagesschau.de/wirtschaft/deutsche-bahn-puenktlichkeit-104.html). On the other hand, the rail network is extensive, with many options to go from A to B, especially for major cities. As someone who likes to travel by train, I find myself comparing connections, travel durations and wondering what the optimal choice would be. This AI project gives a way to quickly and cheaply answer part of that conundrum: if I want to travel by train from A to B in Germany, in a specific time slot of the week - for example Sunday evening - what route and choice of connections is the most reliable based on historical open data?

On a higher level the project is a demonstration of how tool design and model evaluations make a cheap model outperform a far more expensive one used without the skill.

## What it answers

The skill and tools cover four kinds of question, for any pair of stations in the data:

| Question | Example |
|---|---|
| Delay risk of a trip | *How risky is Munich → Bamberg on a Friday evening?* |
| Route alternatives (≤ 1 transfer) | *Is there a slower route that is more reliable than the direct ICE?* |
| Connection risk at a transfer | *I have 10 minutes to change at Nürnberg. How likely am I to miss it?* |
| Weekday / time-of-day comparison | *Is Köln → Frankfurt more punctual on Tuesday mornings or Friday afternoons?* |

Every answer is a historical frequency over observed runs, never a forecast. Every tool response carries a `scope` block (data period, weekdays, hours, time zone) so the answer can say what the numbers cover.

## Results

10 eval cases × Haiku / Sonnet / Opus 5.5 × with / without the skill × 3 repeats = **180 headless Claude Code runs**, 5 deterministic checks each ([evals/report-2026-10-15.md](evals/report-2026-10-15.md)):

| Model | Without skill | With skill | Cost per answer (with skill) |
|---|---|---|---|
| Haiku 5.5 | 76% | **99%** | $0.0019 |
| Sonnet 5.5 | 78% | **99%** | $0.0218 |
| Opus 5.5 | 73% | **100%** | $0.0508 |

- **Haiku with the skill beats Opus without it, at about 1/25 of the cost.**
- Without the skill, every model mostly failed the same check: it did not say what period the numbers cover, or that they are historical (27 of 30 runs each).
- The evals found a bug that the unit tests did not: concurrent tool calls shared one DuckDB connection and sporadically rejected valid station names ([ADR 0004](docs/adr/0004-prebuilt-duckdb-with-memory-cap.md)).
- Total cost of the run: $4.10 at list prices.

How the checks came about, including the failures of a session *without* the skill that motivated them, is in [evals/baseline-findings.md](evals/baseline-findings.md).

## How it works

```
Claude Code ──(skill: analyzing-rail-delay-risk)──┐
                                                  ▼
                MCP server (stdio, 4 read-only tools)  src/db_delay_risk/server.py
                                                  │
                Domain API: Store                 src/db_delay_risk/store.py
                  find_station · trip_risk · connection_risk · route_options
                                                  │
                DuckDB file, deduplicated, ~88M stop events (6 months)
                                                  ▲
                Parquet months from piebro/deutsche-bahn-data (CC BY 4.0)
```

| Tool | Returns |
|---|---|
| `find_station` | Exact station names (a station can have several EVA ids), and how many stops back each one |
| `trip_risk` | Direct runs: late and cancelled counts, late share, fixed delay bands that add up to the run count |
| `connection_risk` | Share of inbound runs that arrive later than each transfer buffer |
| `route_options` | Direct and one-transfer options with service class, planned minutes, missed / late / cancelled shares, a 95% Wilson interval, differences to the direct option, and an `anecdotal` flag for small samples |

Design rule ([ADR 0009](docs/adr/0009-tools-compute-model-explains.md)): **the tools compute every number, the model only explains.** In the first manual session the model miscalculated differences and mixed up "missed" with "late" although the tool output was correct.

## Quick start

Requirements: [uv](https://docs.astral.sh/uv/), Python 3.12, ~2.2 GB for the download, ~8 GB for the built database.

```bash
uv sync

# 1. Download six months of processed data (about 350 MB per month)
uv run --with huggingface-hub hf download piebro/deutsche-bahn-data \
  --repo-type=dataset --local-dir=raw \
  --include "monthly_processed_data/data-2026-0[4-9].parquet"

# 2. Build the deduplicated DuckDB file (~7 minutes, capped at 4 GB RAM; spills to disk)
uv run db-delay-risk-build data/stops.duckdb raw/monthly_processed_data/*.parquet

# 3. Start Claude Code in this directory; approve the project MCP server once
claude
```

`.mcp.json` registers the server (`uv run db-delay-risk-mcp`). The skill lives in `.claude/skills/analyzing-rail-delay-risk/` and is picked up automatically in this directory.

On a shared machine, run the build in a memory-capped scope so it cannot starve other processes: `systemd-run --user --scope -p MemoryMax=6G uv run db-delay-risk-build …` ([ADR 0004](docs/adr/0004-prebuilt-duckdb-with-memory-cap.md)).

## Running the evals

```bash
uv run db-delay-risk-evals --settings path/to/auth-settings.json \
  --models haiku sonnet opus --repeats 3 --parallel 3
uv run db-delay-risk-evals-rescore evals/results/<run>   # re-check saved transcripts, no model calls
```

Each run is a headless `claude -p` call, isolated so that *with* and *without* the skill differ in exactly one thing ([ADR 0011](docs/adr/0011-evals-via-headless-claude-code.md)): `--bare`, a separate config directory, only this MCP server, no built-in tools, a $1 budget cap per run. `--settings` points to a file that holds only authentication. The report ends with the token usage and cost of the whole run.

## Design decisions

| ADR | Decision |
|---|---|
| [0001](docs/adr/0001-db-open-data-for-proof-piece.md) | Deutsche Bahn open data, not a synthetic incident demo |
| [0002](docs/adr/0002-scope-delay-questions-only.md) | Delay questions only; no occupancy or onboard catering |
| [0003](docs/adr/0003-run-identity-and-arrival-delay.md) | A train run is identified by the stop id prefix; arrival delay is computed, not read |
| [0004](docs/adr/0004-prebuilt-duckdb-with-memory-cap.md) | Prebuilt DuckDB file with a hard memory cap; one cursor per thread |
| [0005](docs/adr/0005-route-options-one-transfer-asof.md) | At most one transfer, built from observed stops with an ASOF join; deterministic pairing |
| [0006](docs/adr/0006-stop-order-by-planned-time.md) | Stop order from planned time, because diversion stops carry sequence number 100+ |
| [0007](docs/adr/0007-service-classes-keep-slow-alternatives.md) | Service classes keep the slower regional alternative visible |
| [0008](docs/adr/0008-stations-identified-by-name.md) | Stations are identified by name, not EVA id |
| [0009](docs/adr/0009-tools-compute-model-explains.md) | Tools compute every number; the model only explains |
| [0010](docs/adr/0010-anecdotal-flag-and-wilson-interval.md) | Anecdotal flag and 95% Wilson interval decided by the tool |
| [0011](docs/adr/0011-evals-via-headless-claude-code.md) | Evals through headless Claude Code, isolated per run |

## Limitations

- **Historical, not a forecast.** Six months (2026-04 to 2026-09); seasons are not separated.
- **One transfer at most**, with a flat 5-minute minimum transfer time; real minimum times vary by station.
- **No occupancy or catering data**: no open historical source exists ([ADR 0002](docs/adr/0002-scope-delay-questions-only.md)).
- **The checks test form, not judgement.** Whether a recommendation follows from the numbers is not checked automatically yet; that needs a model-graded check.
- **The checks were corrected after the first full run.** Four kinds of false alarm (German date format, several tool calls per answer, abbreviated station names, leg order) were found by reading failures one by one; each fix has a test, and the saved transcripts were re-scored without new model calls.

## Development

```bash
uv run pytest          # 63 tests: data layer, domain API, MCP tools end to end, eval checks
uv run ruff check . && uv run ruff format --check .
uv run mypy            # strict
```

Built test-first with [Claude Code](https://code.claude.com). Decisions are recorded as ADRs while they are made.

## License

Code: [MIT](LICENSE). Data: Deutsche Bahn, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), via [piebro/deutsche-bahn-data](https://github.com/piebro/deutsche-bahn-data).
