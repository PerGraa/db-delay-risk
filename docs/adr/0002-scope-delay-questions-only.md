# Scope: delay questions only; no occupancy or onboard catering

The skill answers four kinds of question for any covered station pair: delay risk of a trip, route alternatives with at most one transfer, connection risk at a transfer, and comparison by weekday and time of day. Questions about how full trains are, or about bistro/restaurant cars, are out of scope. No open historical source exists. DB's RIS::Transports (formation, occupancy, car features) is limited to railway operators and starts at €4,200/year. The unofficial live endpoints (db-vendo-client, Regio Guide) are partial and warn of random blocking.

## Consequences

The README lists "what real DB data access would add" as the next step a customer engagement would unlock. Route search stops at one transfer to keep it tractable and testable.
