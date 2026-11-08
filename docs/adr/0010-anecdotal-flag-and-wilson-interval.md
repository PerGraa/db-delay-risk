# The tool flags anecdotal options and gives each late share a 95% interval

With the skill loaded, the model still broke its own "< 30 runs is anecdotal" rule when the result looked interesting. It called a 23-run option "clearly the best". It also ranked two options 0.5 percentage points apart (70 vs 173 runs) as if the gap meant something. Following ADR 0009, judgement calls that depend on numbers move into the tool. `route_options` marks options with fewer than `min_reliable_runs` (default 30) as `anecdotal` and lists them last. Every option carries `late_low`/`late_high`, the 95% Wilson score interval of its late share. The skill calls an option more reliable than the direct one only when the intervals do not overlap.

## Considered Options

- **Normal (Wald) interval.** Rejected: it breaks down for small samples and for shares near 0% or 100%, which are common here (e.g. 5 runs, 100% late).
- **A significance test per pair.** More precise, but harder for the model to explain in one sentence. Non-overlapping intervals are conservative and easy to state.

## Consequences

Non-overlap at 95% is stricter than a pairwise test, so some real but small improvements will be reported as "not clearly different". For a traveller that is the honest default. The expected values in the tests were cross-checked with `statsmodels.proportion_confint(method="wilson")`.
