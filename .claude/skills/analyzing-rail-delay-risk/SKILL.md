---
name: analyzing-rail-delay-risk
description: Answers questions about how reliable Deutsche Bahn train trips have been, using the db-delay-risk MCP tools over historical open data. Covers delay risk of a trip, slower-but-safer route alternatives with one transfer, risk of missing a connection, and comparisons by weekday or time of day. Use when the user asks how late, punctual, risky or reliable a German train journey or connection is, or which route to take.
---

# Analyzing rail delay risk

The tools return historical frequencies over observed stops. **Every number in your answer must come from a tool field.** Do not compute differences, sums or shares yourself; the tools already return them (`delta_minutes`, `delta_late_pp`, `late_share`, `missed_share`, `bands`).

## Workflow

```
- [ ] 1. Resolve both stations with find_station; use the exact `name`
- [ ] 2. Pin the window: weekdays (Mon..Sun) and departure hours, local time
- [ ] 3. route_options for the trip (always, even for "how risky is X → Y"); deltas compare with the direct option
- [ ] 4. trip_risk for the direct option if one exists (gives delay bands)
- [ ] 5. connection_risk only when the user asks about a specific transfer or buffer
- [ ] 6. Answer with the template below
```

Tools: `mcp__db-delay-risk__find_station`, `…__route_options`, `…__trip_risk`, `…__connection_risk`.

If the user names a city ("Munich"), pick the main station (`… Hbf`) and say so. If a time is vague, "evening" = 16–21, "morning" = 6–10, and say what you used.

## Rules

1. **Missed ≠ late.** `missed_share` = the transfer failed. `late_share` = arrived ≥ `late_min` minutes late *or* missed the connection. Report both, in separate columns, and never call one the other.
2. **Compare before you conclude.** An option is *more reliable* than the direct one only if its `late_high` is below the direct option's `late_low` (non-overlapping 95% intervals). Overlapping means *not clearly different*: say so, and then time decides. Never say "no better option" without checking this for every non-anecdotal option.
3. **Anecdotal is decided by the tool.** Options with `anecdotal: true` go in a separate "Anecdotal" line below the table, never in the main table, and never into the recommendation, however good they look.
4. **Mention every non-anecdotal option** the tool returned, including ones you rule out, with one reason each.
5. **No invented causes.** The data shows *how often*, not *why*. Do not explain delays (construction, weather, small samples "causing" lateness) unless the user supplies the reason.
6. **Scope line.** Start the answer with the `scope` block: data period, weekdays, departure hours, and "historical, not a forecast".

## Answer template

```markdown
**Scope:** <data_from> to <data_to> · <weekdays> · departures <departure_hours> (Europe/Berlin) · historical frequencies, not a forecast

| Option | Class | Runs | Planned | vs direct | Missed connection | Late (≥6 min or missed), 95% range |
|---|---|---|---|---|---|---|
| ICE direct | long-distance | 132 | 114 min | — | — | 51% (42–59%) |
| ICE + RE via Nürnberg Hbf (7 min transfer) | mixed | 173 | 121 min | +7 min, −4.5 pp | 40% | 46% (39–54%) |

**Anecdotal** (`anecdotal: true`, not used for the answer): <option, runs, late share> · …

**Answer:** <1–3 sentences answering the user's actual question, citing the table>

**Delay distribution** (direct option, from `bands`; only if asked or useful): on time or early X · 1–5 min X · 6–15 X · 16–30 X · 31–60 X · over 60 X · cancelled X (of N runs)

**Caveats:** <only the ones that apply: overlapping ranges, short transfers, data gaps>
```

Shares as whole percent; deltas as `+N min` and `±N pp` (percentage points).
