from conftest import trip

from db_delay_risk import Store

MUC, NUE, BA = ("08000261", "München Hbf"), ("08000284", "Nürnberg Hbf"), ("08000025", "Bamberg")


def test_duplicate_snapshot_rows_count_as_one_stop(write_parquet):
    rows = trip(
        "r1",
        "2026-09-04 17:19",
        "ICE",
        "1002",
        [(*MUC, 0, None, 13), (*NUE, 74, 18, 18), (*BA, 120, 20, None)],
    )
    path = write_parquet(rows + rows[1:2])  # Nürnberg row fetched twice

    store = Store.open([path])

    assert store.count_stops() == 3


def test_built_database_answers_like_the_parquet_source(write_parquet, tmp_path):
    rows = trip(
        "r1", "2026-09-04 17:19", "ICE", "1002", [(*MUC, 0, None, 0), (*NUE, 74, 0, 0), (*BA, 120, 12, None)]
    )
    source = write_parquet(rows + rows)
    db_file = tmp_path / "stops.duckdb"

    Store.build([source], db_file)
    store = Store.load(db_file)

    assert store.count_stops() == 3
    assert store.trip_risk(MUC[1], BA[1], weekdays=["Fri"], hours=(17, 18), late_min=6).late == 1


def test_loaded_store_is_memory_capped_and_reports_its_period(write_parquet, tmp_path):
    rows = trip("r1", "2026-09-04 17:19", "ICE", "1002", [(*MUC, 0, None, 0), (*BA, 120, 0, None)])
    rows += trip("r2", "2026-09-25 08:00", "ICE", "1004", [(*MUC, 0, None, 0), (*BA, 120, 0, None)])
    db_file = tmp_path / "stops.duckdb"
    Store.build([write_parquet(rows)], db_file)

    store = Store.load(db_file, memory_limit="512MB")

    assert store.memory_limit_bytes() <= 512 * 1024**2
    assert store.period() == ("2026-09-04", "2026-09-25")


def test_concurrent_queries_on_one_store_all_succeed(write_parquet, tmp_path):
    # The MCP server runs sync tools in worker threads; one shared DuckDB connection gave
    # sporadic wrong "unknown station" errors under concurrent calls (found by the evals).
    from concurrent.futures import ThreadPoolExecutor

    rows = []
    for i in range(30):
        rows += trip(
            f"r{i}", f"2026-09-{1 + i % 28:02d} 17:19", "ICE", "1", [(*MUC, 0, None, 0), (*BA, 120, i, None)]
        )
    db_file = tmp_path / "stops.duckdb"
    Store.build([write_parquet(rows)], db_file)
    store = Store.load(db_file)

    def call(_):
        return store.trip_risk(
            MUC[1],
            BA[1],
            weekdays=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
            hours=(0, 24),
            late_min=6,
        ).runs

    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(call, range(200)))

    assert set(results) == {30}
