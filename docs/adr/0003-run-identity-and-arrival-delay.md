# Identify a train run by the stop id prefix; compute arrival delay ourselves

In the source, `train_line_ride_id` is shared by every day a service runs, so joining two stations on it multiplies the matches across days. The stop `id` has the shape `<ride>-<yymmddHHMM of first departure>-<stop seq>`. We take everything before the last `-` as the run id, which identifies exactly one run, including runs that cross midnight. The source's `delay_in_min` is the *departure* delay, except at the last stop (verified on September 2026: it matches the departure delay in 100% of a 200k sample, and the arrival delay in only 57%). So the delay at a destination is computed from `arrival_change_time - arrival_planned_time`.

## Consequences

If the upstream id format changes, run identity breaks silently. A store test pins the format.
