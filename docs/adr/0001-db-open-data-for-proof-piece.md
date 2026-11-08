# Deutsche Bahn open data, not a synthetic incident demo

The proof piece first planned incident triage on the OpenTelemetry Astronomy Shop with seeded faults. We switched to Deutsche Bahn open data: piebro/deutsche-bahn-data, CC BY 4.0, scraped from the DB Timetables API. That gives real, messy, German enterprise-scale data. It is also clearly separate from the author's day job in data-infrastructure operations. It is the kind of customer a Munich-based forward-deployed engineer would actually meet.

## Considered Options

- **OTel demo + seeded faults.** Exact answer keys, but a staged demo, and close to the author's current work domain.
- **FlixBus GTFS (ODbL).** Planned timetables only, with no realtime or delay data, so there is nothing to analyse.
- **DB Timetables API live.** Needs an API key, 60 req/min, and gives no history. Kept as a possible optional extension.

## Consequences

Eval answer keys must be computed from the data with independent SQL, or planted on purpose. They cannot be known in advance by construction.
