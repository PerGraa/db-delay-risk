"""Build the deduplicated DuckDB file from downloaded Parquet months (see ADR 0004).

Run under a memory cap on shared machines, e.g.
    systemd-run --user --scope -p MemoryMax=6G uv run db-delay-risk-build data/stops.duckdb raw/*.parquet
"""

from __future__ import annotations

import argparse
import time

from db_delay_risk.store import Store


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("db_file")
    p.add_argument("parquet", nargs="+")
    p.add_argument("--memory-limit", default="4GB")
    p.add_argument("--threads", type=int, default=4)
    a = p.parse_args()
    t = time.monotonic()
    Store.build(a.parquet, a.db_file, memory_limit=a.memory_limit, threads=a.threads)
    print(f"built {a.db_file}: {Store.load(a.db_file).count_stops():,} stops in {time.monotonic() - t:.0f}s")
