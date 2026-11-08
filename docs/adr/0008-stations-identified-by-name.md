# Stations are identified by name, not by EVA id

The tools originally took EVA ids. On real data, 43 station names have more than one EVA id. München Hbf has four: the main hall (ICE/RE/RB), the S-Bahn tunnel, and two ids used by BRB, Meridian and some EC/RJ trains. The same holds for Berlin Hbf, Frankfurt (Main) Hbf, Hamburg Hbf, Stuttgart Hbf, Leipzig Hbf and others. Searching from one id silently missed departures from the others. In six months of data no EVA id ever carries two names, so the name is a clean grouping key. All tools now take the exact station name. `find_station` returns one entry per name with its list of ids, and an unknown name fails with a message that points the model back to `find_station`.

## Considered Options

- **Keep EVA ids and let the agent pass lists of ids.** This is precise but easy to get wrong for an agent: it must remember to collect every id, and tool calls become noisy.
- **Hand-curated station groups** (e.g. "München Hbf" + "München Hbf Gl.27-36"). Not needed: the source already uses one name for all ids of a station.

## Consequences

Two different places with the same name would be merged; we have seen none. A transfer *within* a grouped station (e.g. main hall to S-Bahn tunnel) is treated like any other transfer, with the same minimum transfer time.
