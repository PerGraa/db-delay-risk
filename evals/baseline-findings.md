# Baseline session without a skill (2026-10-15)

Claude Code with the MCP server only, no skill. Four Trip questions. Every number below was checked against the tools on the same data (2026-03-31 → 2026-10-01).

## What went well
- It resolved names with `find_station` first and never passed raw EVA ids.
- It chose sensible tools: `route_options` → `connection_risk` → `trip_risk`.
- It reported run counts, flagged small samples, defined "late" (≥ 6 min or cancelled), and called the numbers historical frequencies.

## Failures (each becomes an eval case)
| # | Failure | Truth from the tools |
|---|---|---|
| F1 | Mixed up *missed* (connection) with *late* (arrival); the user had to ask | Two separate shares per Route option |
| F2 | "Direct ICE roughly tied for best reliability"; answered "no" to slower-but-safer | ICE+RE via Nürnberg 46% late (203 runs) vs ICE direct 51% (132 runs), +8 min |
| F3 | Hamburg-Altona→Leipzig: S+FLX "adds ~24 min over the direct ICE" | 243 vs 235 min = 8 min |
| F4 | Ignored S+ICE via Hamburg Hbf: faster (214 min) and more runs (67) than ICE direct (53) | It is 85% late, so not better, but it must be mentioned |
| F5 | "30+ min delay is almost as likely as being roughly on time" | ~45% vs ~25%: nearly twice as likely |
| F6 | Claimed risk stays high "because sample sizes shrink" | Sample size affects certainty, not lateness |
| F7 | Never stated the data period | 2026-03-31 → 2026-10-01 |
| F8 | Small-sample option (5–17 runs) quoted as the best case | Must be labelled as weak evidence |

## Implications for the skill
1. Always report missed and late as two separate columns.
2. Compute differences from tool output (the arithmetic is shown, or done with a tool).
3. Compare every option with ≥ N runs against the direct baseline before saying "no better option".
4. State the data period and the time window in every answer.
5. Treat options with fewer than ~30 runs as anecdotal.
6. Do not give causal explanations the data cannot support.

---

# Session with skill `analyzing-rail-delay-risk` (2026-10-15)

Two Trip questions (Munich → Bamberg, Hamburg-Altona → Leipzig, Friday evening). Tool calls: find_station → route_options → trip_risk for each. Every number was checked against the raw tool output in the session log.

| Baseline failure | With skill |
|---|---|
| F1 missed vs late mixed up | Fixed: separate columns, correct values |
| F2 "no better option" | Fixed: ICE+RE options named as 4.5–5 pp more reliable for +7/+11 min |
| F3 wrong time difference | Fixed: all deltas quoted from tool fields |
| F4 options left out | Fixed: every option with ≥ 30 runs listed |
| F5 wrong distribution comparison | Fixed: bands quoted verbatim |
| F6 invented causes | Fixed: none |
| F7 no data period | Fixed: scope line in both answers |
| F8 small samples as best case | Partly: see N1 |

## New findings
- **N1 (threshold leak).** Hamburg-Altona → Leipzig: S+FLX with 23 runs went into the main table and was called "clearly the best", although the skill says < 30 runs is anecdotal. ICE+ICE via Berlin Hbf (17 runs) also went into the main table. The model noted "borderline, treat with caution" but broke rule 3. Fix: the tool marks options `anecdotal: true` (threshold as a parameter), so the model does not apply the rule by itself.
- **N2 (ranking).** In the first answer, Erlangen (70 runs, −5.0 pp) is listed before Nürnberg (173 runs, −4.5 pp), and the two are called equal. That is fine, but a 0.5 pp gap between samples of 70 and 173 is noise. Fix: the tool returns a simple uncertainty band (e.g. a 95% Wilson interval) so "better" means "better beyond noise".
- **N3 (window).** "Later than 21:00 allowed" became 16–23. That is reasonable, and it was stated.
- **N4 (cost).** Both answers used 4–5 tool calls and finished in 32–50 s.

---

# Automated eval run (2026-10-15, 20261015-103348)

10 cases × Haiku/Sonnet/Opus 5.5 × with/without skill × 3 repeats = 180 headless Claude Code runs, 5 deterministic checks each (see ADR 0011). Rescored after fixing four false alarms in the checks (German dates, several route_options calls per answer, abbreviated station names, leg order). Each fix has a test. The remaining failures were inspected one by one and are real.

| Model | Skill | Runs | Checks passed | Pass rate | Most failed | Cost | Cost/run | Avg time |
|---|---|---|---|---|---|---|---|---|
| haiku | no | 30 | 114/150 | 76% | scope_stated x27, numbers_traceable x5 | $0.0318 | $0.0011 | 17 s |
| haiku | yes | 30 | 148/150 | 99% | no_raw_eva_ids x2 | $0.0584 | $0.0019 | 26 s |
| opus | no | 30 | 109/150 | 73% | scope_stated x27, numbers_traceable x12 | $1.3988 | $0.0466 | 25 s |
| opus | yes | 30 | 150/150 | 100% | — | $1.5250 | $0.0508 | 23 s |
| sonnet | no | 30 | 117/150 | 78% | scope_stated x27, numbers_traceable x3 | $0.4306 | $0.0144 | 16 s |
| sonnet | yes | 30 | 149/150 | 99% | reliable_options_mentioned x1 | $0.6540 | $0.0218 | 18 s |

**Total cost of this run:** $4.0986 for 180 runs · tokens: 1,528 input, 319,051 output, 1,650,746 cache read, 373,967 cache write

## Reading
- The skill lifts every model from 73–78% to 98–100% of checks.
- Without the skill, the most common failure is the same in all models: no data period or "historical" disclaimer (27 of 30 runs each). Opus without the skill also had the most untraceable numbers (12).
- **Haiku with the skill (99%) beats Opus without it (73%) at 1/25 of the cost** ($0.0019 vs $0.0466 per answer).
- Remaining real failures: Haiku twice printed raw EVA ids; Sonnet once left out a reliable option.
- Bug found by the evals, not by unit tests: concurrent tool calls shared one DuckDB connection (fixed, ADR 0004 amendment).
- Not covered yet: whether the recommendation follows from the numbers (needs a judge), and whether answers to the forecast-trap question refuse to forecast.
