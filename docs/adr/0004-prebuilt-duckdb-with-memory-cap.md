# Prebuilt, deduplicated DuckDB file with a hard memory cap

Agent tools must answer in about a second. Querying six months of raw Parquet (about 88M rows, 2.1 GB) took about 8 s per question for a single month, because duplicate snapshot rows are removed on every query. So we deduplicate once into a local DuckDB file, sorted by station, and the tools query that file read-only.

The first build attempt used DuckDB's default memory limit (80% of RAM). On a shared 62 GB workstation it pushed the machine into memory pressure, and systemd-oomd killed the terminal session. The build now sets `memory_limit`, `threads` and a `temp_directory` so it spills to disk instead, and it is run inside a `systemd-run --user --scope -p MemoryMax=…` sandbox so only the build can be killed.

## Consequences

The data must be rebuilt when new months are added (a `build` command, minutes not seconds). The built file is not committed; the README documents how to download the data and build it.

## Amendment: one cursor per thread (found by the evals)

The first eval run showed `find_station` resolving "Köln Hbf", then `route_options` rejecting the same name as unknown, plus bare "Error executing tool" crashes. The MCP server runs synchronous tools in worker threads, and all of them shared one DuckDB connection, which is not thread-safe. A concurrency test (200 calls on 8 threads) reproduced the failure on every run. `Store` now hands each thread its own cursor on the shared connection.
