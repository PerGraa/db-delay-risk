# Tools compute every number; the model only explains

In a baseline session without a skill (`evals/baseline-findings.md`), the model read correct tool output and still got it wrong. It said "adds ~24 min" for an 8-minute difference, called a 45% vs 25% gap "almost as likely", mixed up missed connections with late arrivals, and never stated the data period. Instructions alone do not make arithmetic reliable. So the tools now return the derived numbers the answer needs. `route_options` gives `delta_minutes` and `delta_late_pp` against the fastest option. `trip_risk` gives fixed, non-overlapping delay `bands` that add up to `runs`. Every response carries a `scope` block: data period, weekdays, departure hours, time zone, and "historical frequencies, not a forecast". The skill then tells the model to quote these fields rather than calculate its own.

## Consequences

Tool outputs are larger, and new comparisons need a tool change rather than a prompt change. The `Store.load` memory cap (default 2 GB) also lives here, because the server runs inside the user's agent session without a sandbox.
