# Service classes keep the slower, regional alternative visible

A traveller's typical question is "is there a slower route that is more reliable?". Ranking route options by planned duration and cutting at a limit hid exactly that answer. On real data, Munich → Bamberg (Fridays 15–21h, 6 months) showed eight fast ICE variants and no regional-only route. So each route option gets a service class from its leg product codes: *long-distance* (ICE, IC, EC, RJ, NJ, FLX, …), *regional* (all other rail operators: RE, RB, S, ag, BRB, …), *mixed*, or *road* (any bus or rail-replacement leg). The class is used three times:

1. At a transfer, an inbound run is paired with the first onward train *of each class*, not just the first train.
2. When several inbound runs reach the same onward train, the latest one is kept per inbound class, so a regional inbound is not dropped in favour of a faster ICE.
3. The result always includes the fastest option of every class before filling up by duration. `min_runs` (default 3 in the MCP tool) drops options seen too rarely to judge.

After the change the same query surfaces RE+RE via Nürnberg (121 runs, 169 min, 49% late) next to ICE direct (132 runs, 114 min, 51% late).

## Consequences

The code list for long-distance is hand-maintained. The source has over 150 product codes, including private and foreign operators and typos. An unknown long-distance code would be classed as regional, so a rare misclassification is possible and acceptable for a historical overview.
