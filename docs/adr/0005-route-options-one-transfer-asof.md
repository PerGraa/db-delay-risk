# Route options: at most one transfer, built from observed stops with an ASOF join

The source holds observed stops, not a timetable, so there is no ready-made journey planner. A Route option with one transfer is built from the data itself. Every run from the origin to any intermediate station is paired, by an ASOF join, with the *first* run leaving that station towards the destination at least `min_transfer` (default 5) and at most `max_wait` (default 60) planned minutes later, on the same day. When several inbound runs reach the same outbound train, only the latest-departing one is kept, because nobody would set off earlier for the same connection. A missed connection (inbound delay greater than the planned transfer time, or a cancelled inbound leg) counts as a late journey.

## Considered Options

- **Use DB's real minimum transfer times.** These vary by station and platform and are not in the open data. A flat 5 minutes is a stated assumption that the caller can change.
- **Two or more transfers.** The search space grows quickly and adds little to the proof piece. Rejected for now (see ADR 0002).
- **A fixed "safe" threshold.** Rejected. The tool reports missed and late shares per option, and the agent explains the trade-off between time and risk.

## Consequences

Arrival after a missed connection (the next train) is not yet modelled. "Late" for a missed connection is a lower bound on how bad it was. Options with very few runs are returned too, so the agent must report sample sizes.

## Amendment: deterministic pairing (after a smoke test on real data)

Repeated identical queries returned different run counts, e.g. ICE+RE via Erlangen 47, 68, 70, 71. Two runs that share several stations (ICE and RE both calling at Nürnberg and Erlangen) produced one journey per shared station. The window functions then picked among ties in a non-deterministic order. Now each pair of runs yields exactly one journey, changing where the planned transfer is longest (ties: earliest arrival, then station name). Every `row_number()` has a total order. Deltas use the direct option as baseline when there is one, else the fastest.
