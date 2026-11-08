# Stop order comes from planned time, not train_line_station_num

On real data, `route_options` returned a journey with a negative duration. In the source, `train_line_station_num` is set to 100 or more for diversion and additional stops (`is_additional_stop`), so such a stop sorts *after* the terminus. We order stops within a run by planned time (`coalesce(arrival_planned_time, departure_planned_time)`), stored as `planned_at`. On a September 2026 sample of 3.4M stop pairs, the two orderings disagree in only 11 cases among normal (< 100) stops, so planned time is safe as the single rule.
