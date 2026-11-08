"""Read-only access to piebro/deutsche-bahn-data monthly_processed_data Parquet files."""

from __future__ import annotations

import math
import threading
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

import duckdb

WEEKDAYS = {"Mon": 1, "Tue": 2, "Wed": 3, "Thu": 4, "Fri": 5, "Sat": 6, "Sun": 0}  # duckdb dayofweek

# Long-distance product codes seen in the data (DB and foreign/private operators). Every
# other rail code is a regional operator (RE, RB, S, ag, BRB, ...). See ADR 0007.
LONG_DISTANCE = ("ICE", "IC", "EC", "ECE", "RJ", "RJX", "NJ", "EN", "TGV", "FLX", "D", "EST", "ES", "EUR")
ROAD = ("Bus", "SEV", "Bsv", "BSV", "bus", "BUS", "TAXI", "Taxi")


def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a share k/n; behaves well for small n and shares near 0 or 1."""
    if n == 0:
        return 0.0, 1.0
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def service_class(legs: Sequence[str | None]) -> str:
    """Coarse class of a route: long-distance, regional, mixed (both), or road (any bus leg)."""
    if any(
        t is None or t in ROAD or t.lower().startswith(("bus", "bsv", "sev", "bev", "taxi")) for t in legs
    ):
        return "road"
    ld = [t in LONG_DISTANCE for t in legs]
    return "long-distance" if all(ld) else "regional" if not any(ld) else "mixed"


@dataclass(frozen=True)
class TripRisk:
    """`bands` splits every run into exactly one arrival-delay band (minutes, inclusive)."""

    runs: int
    late: int
    cancelled: int
    bands: dict[str, int]

    @property
    def late_share(self) -> float:
        return self.late / self.runs if self.runs else 0.0


@dataclass(frozen=True)
class ConnectionRisk:
    """How often the inbound leg arrives later than each transfer buffer (cancelled counts as missed)."""

    runs: int
    missed: dict[int, int]

    def missed_share(self, buffer: int) -> float:
        return self.missed[buffer] / self.runs if self.runs else 0.0


@dataclass(frozen=True)
class RouteOption:
    """One way to make a trip, aggregated over all matching journeys in the time window.

    `via` is None for a direct run. A missed connection counts as late; a cancelled
    final leg counts as cancelled. The deltas compare with the baseline (the direct option
    if there is one, else the fastest), so the model reads differences instead of computing them.
    """

    via: str | None
    legs: list[str]
    runs: int
    planned_minutes: int
    transfer_minutes: int | None
    missed: int
    late: int
    cancelled: int
    delta_minutes: int = 0
    delta_late_pp: float = 0.0
    anecdotal: bool = False

    @property
    def late_low(self) -> float:
        return wilson_interval(self.late, self.runs)[0]

    @property
    def late_high(self) -> float:
        return wilson_interval(self.late, self.runs)[1]

    @property
    def service_class(self) -> str:
        return service_class(self.legs)

    @property
    def missed_share(self) -> float:
        return self.missed / self.runs if self.runs else 0.0

    @property
    def late_share(self) -> float:
        return self.late / self.runs if self.runs else 0.0


@dataclass(frozen=True)
class Station:
    """A station is identified by its name; big stations have several EVA ids (e.g. the
    München Hbf S-Bahn tunnel), which all count as the same station. See ADR 0008."""

    name: str
    evas: list[str]
    stops: int


class UnknownStation(ValueError):
    pass


def _stops_query(paths: Sequence[Path | str]) -> str:
    files = ", ".join(f"'{Path(p).as_posix()}'" for p in paths)
    # `id` is "<ride>-<yymmddHHMM of first departure>-<stop seq>", so all but the last
    # part identify one run of a train, also across midnight. See ADR 0003.
    return f"""
        select *, regexp_replace(id, '-[0-9]+$', '') as run_id,
               datediff('minute', arrival_planned_time, arrival_change_time) as arr_delay,
               -- stop order: train_line_station_num is >= 100 for diversion stops, so use
               -- planned time instead (ADR 0006)
               coalesce(arrival_planned_time, departure_planned_time) as planned_at
        from read_parquet([{files}])
        qualify row_number() over (partition by id) = 1"""


class Store:
    """One row per stop per run. The source can hold the same stop several times
    (fetched by overlapping API snapshots), so rows are deduplicated on `id`."""

    def __init__(self, con: duckdb.DuckDBPyConnection):
        self._root = con
        self._local = threading.local()

    @property
    def _con(self) -> duckdb.DuckDBPyConnection:
        """A cursor per thread. A DuckDB connection is not safe to share between threads, and
        the MCP server runs tool calls in worker threads (ADR 0004, found by the evals)."""
        cur: duckdb.DuckDBPyConnection | None = getattr(self._local, "cursor", None)
        if cur is None:
            cur = self._root.cursor()
            self._local.cursor = cur
        return cur

    @classmethod
    def open(cls, paths: Sequence[Path | str]) -> Store:
        """Query Parquet files directly. Slow on real data; use `build` + `load` there."""
        con = duckdb.connect()
        con.execute(f"create view stops as {_stops_query(paths)}")
        return cls(con)

    @classmethod
    def build(
        cls, paths: Sequence[Path | str], db_file: Path | str, *, memory_limit: str = "4GB", threads: int = 4
    ) -> None:
        """Deduplicate the Parquet files once into a DuckDB file, ordered by station.

        DuckDB defaults to 80% of RAM; on a shared workstation that starves other
        processes, so memory is capped and larger-than-memory work spills to disk.
        """
        db_file = Path(db_file)
        with duckdb.connect(str(db_file)) as con:
            con.execute(f"set memory_limit = '{memory_limit}'")
            con.execute(f"set threads = {threads}")
            con.execute(f"set temp_directory = '{db_file.parent / 'duckdb_tmp'}'")
            con.execute("set preserve_insertion_order = false")
            con.execute(
                f"create or replace table stops as {_stops_query(paths)} order by station_name, run_id"
            )

    @classmethod
    def load(cls, db_file: Path | str, *, memory_limit: str = "2GB", threads: int = 4) -> Store:
        """Open a built file read-only. Memory is capped because the MCP server runs inside
        the user's editor or agent session, not a sandbox (ADR 0004)."""
        con = duckdb.connect(
            str(db_file), read_only=True, config={"memory_limit": memory_limit, "threads": threads}
        )
        return cls(con)

    def memory_limit_bytes(self) -> int:
        row = self._con.execute("select current_setting('memory_limit')").fetchone()
        assert row is not None
        number, unit = str(row[0]).split()  # e.g. "488.2 MiB"
        return int(float(number) * 1024 ** ["bytes", "KiB", "MiB", "GiB", "TiB"].index(unit))

    def period(self) -> tuple[str, str]:
        """First and last service date covered by the data (local time)."""
        row = self._con.execute("select min(planned_at)::date, max(planned_at)::date from stops").fetchone()
        assert row is not None
        return str(row[0]), str(row[1])

    def _one(self, sql: str, params: dict[str, object] | None = None) -> tuple[int, ...]:
        """Run an aggregate count query; those always return exactly one row of ints."""
        row = self._con.execute(sql, params).fetchone()
        assert row is not None
        return tuple(int(v) for v in row)

    def count_stops(self) -> int:
        return self._one("select count(*) from stops")[0]

    def find_station(self, query: str, limit: int = 10) -> list[Station]:
        """Stations whose name contains `query`, ignoring case and accents.

        Exact matches rank first, then prefix matches, then the rest; busier stations first.
        """
        rows = self._con.execute(
            """
            with names as (
                select station_name as name, list(distinct eva order by eva) as evas, count(*) as stops,
                       lower(strip_accents(station_name)) as norm
                from stops where station_name is not null group by station_name),
            q as (select lower(strip_accents($q)) as q)
            select name, evas, stops from names, q
            where contains(norm, q.q)
            order by case when norm = q.q then 0 when starts_with(norm, q.q) then 1 else 2 end,
                     stops desc, name
            limit $limit
            """,
            {"q": query.strip(), "limit": limit},
        ).fetchall()
        return [Station(name=n, evas=list(e), stops=int(c)) for n, e, c in rows]

    def _require(self, *names: str) -> None:
        known = {
            r[0]
            for r in self._con.execute(
                "select distinct station_name from stops where list_contains($n, station_name)",
                {"n": list(names)},
            ).fetchall()
        }
        unknown = [n for n in names if n not in known]
        if unknown:
            raise UnknownStation(f"Unknown station name(s) {unknown}; resolve exact names with find_station")

    def connection_risk(
        self,
        origin: str,
        transfer: str,
        *,
        weekdays: Sequence[str],
        hours: tuple[int, int],
        buffers: Sequence[int],
    ) -> ConnectionRisk:
        """For runs `origin` -> `transfer` departing in the window: how many arrive more than
        `buffer` minutes late at `transfer`, for each buffer."""
        self._require(origin, transfer)
        rows = self._con.execute(
            """
            select b.arrival_is_canceled or a.departure_is_canceled as cancelled, b.arr_delay
            from stops a join stops b using (run_id)
            where a.station_name = $o and b.station_name = $t
              and a.planned_at < b.planned_at
              and list_contains($days, dayofweek(a.departure_planned_time))
              and hour(a.departure_planned_time) >= $h0 and hour(a.departure_planned_time) < $h1
            """,
            {
                "o": origin,
                "t": transfer,
                "days": [WEEKDAYS[d] for d in weekdays],
                "h0": hours[0],
                "h1": hours[1],
            },
        ).fetchall()
        missed = {b: sum(1 for c, d in rows if c or (d or 0) > b) for b in buffers}
        return ConnectionRisk(runs=len(rows), missed=missed)

    def route_options(
        self,
        origin: str,
        dest: str,
        *,
        weekdays: Sequence[str],
        hours: tuple[int, int],
        late_min: int = 6,
        min_transfer: int = 5,
        max_wait: int = 60,
        min_runs: int = 1,
        min_reliable_runs: int = 30,
        limit: int = 10,
    ) -> list[RouteOption]:
        """Direct runs and one-transfer journeys from `origin` to `dest`, departing in the window.

        A transfer journey takes the first train leaving the transfer station at least
        `min_transfer` and at most `max_wait` planned minutes after the planned arrival.
        When several inbound runs of the same class (long-distance or not) reach the same
        outbound train, only the latest-departing one is kept: nobody would wait longer for
        the same connection. See ADR 0005.

        Options seen fewer than `min_runs` times are dropped; those seen fewer than
        `min_reliable_runs` times are kept but flagged `anecdotal` and sorted last (ADR 0010).
        The result keeps the fastest option of each service class first, then fills up to
        `limit` by planned duration, so a slower but regional-only route is not crowded out by
        fast variants (ADR 0007).
        """
        self._require(origin, dest)
        rows = self._con.execute(
            """
            with inb as (
                select a.run_id, a.departure_planned_time as dep0, b.station_name as via,
                       b.arrival_planned_time as arr_via, b.arr_delay as via_delay, a.train_type as t1,
                       a.departure_is_canceled or b.arrival_is_canceled as c1
                from stops a join stops b using (run_id)
                where a.station_name = $o and b.station_name not in ($o, $d)
                  and a.planned_at < b.planned_at
                  and list_contains($days, dayofweek(a.departure_planned_time))
                  and hour(a.departure_planned_time) >= $h0 and hour(a.departure_planned_time) < $h1),
            outb as (
                select b.run_id as run2, b.station_name as via, b.departure_planned_time as dep_via,
                       c.arrival_planned_time as arr_dest, c.arr_delay as dest_delay, b.train_type as t2,
                       b.departure_is_canceled or c.arrival_is_canceled as c2,
                       list_contains($ld, b.train_type) as ld2
                from stops b join stops c using (run_id)
                where c.station_name = $d and b.station_name <> $o
                  and b.planned_at < c.planned_at),
            transfers as (
                select * from (
                    select inb.via, [t1, t2] as legs, dep0, arr_dest, run_id, run2, t1,
                           datediff('minute', arr_via, dep_via) as transfer,
                           c1 or via_delay > datediff('minute', arr_via, dep_via) as missed,
                           c2 as cancelled, dest_delay
                    from (select * from inb, unnest([true, false]) as k(ld)) inb
                    asof join outb
                      on inb.via = outb.via and inb.ld = outb.ld2
                     and outb.dep_via >= inb.arr_via + to_minutes($min_transfer)
                    where run_id <> run2 and dep_via <= arr_via + to_minutes($max_wait)
                    -- the same two runs can meet at several stations: one journey, change
                    -- where the planned transfer is longest (ties: earliest station)
                    qualify row_number() over (
                        partition by run_id, run2 order by transfer desc, arr_via, inb.via) = 1)
                qualify row_number() over (
                    partition by run2, list_contains($ld, t1) order by dep0 desc, run_id) = 1),
            direct as (
                select null::varchar as via, [a.train_type] as legs, a.departure_planned_time as dep0,
                       b.arrival_planned_time as arr_dest, null::int as transfer, false as missed,
                       a.departure_is_canceled or b.arrival_is_canceled as cancelled,
                       b.arr_delay as dest_delay
                from stops a join stops b using (run_id)
                where a.station_name = $o and b.station_name = $d
                  and a.planned_at < b.planned_at
                  and list_contains($days, dayofweek(a.departure_planned_time))
                  and hour(a.departure_planned_time) >= $h0 and hour(a.departure_planned_time) < $h1),
            journeys as (select * from direct union all by name select * from transfers)
            select via, legs, count(*) as runs,
                   round(median(datediff('minute', dep0, arr_dest)))::int as planned_minutes,
                   round(median(transfer))::int as transfer_minutes,
                   count(*) filter (where missed) as missed,
                   count(*) filter (where missed or (not cancelled and dest_delay >= $late)) as late,
                   count(*) filter (where not missed and cancelled) as cancelled
            from journeys
            group by via, legs
            having count(*) >= $min_runs
            order by planned_minutes, runs desc
            """,
            {
                "o": origin,
                "d": dest,
                "days": [WEEKDAYS[d] for d in weekdays],
                "h0": hours[0],
                "h1": hours[1],
                "late": late_min,
                "min_transfer": min_transfer,
                "max_wait": max_wait,
                "min_runs": min_runs,
                "ld": list(LONG_DISTANCE),
            },
        ).fetchall()
        ranked = [RouteOption(*r) for r in rows]
        best_per_class = list({o.service_class: o for o in reversed(ranked)}.values())
        picked = sorted(best_per_class, key=ranked.index)[:limit]
        picked += [o for o in ranked if o not in picked][: limit - len(picked)]
        picked.sort(key=ranked.index)
        if not picked:
            return []
        # Baseline for deltas: the direct option if there is one, else the fastest.
        base = next((o for o in picked if o.via is None), picked[0])
        result = [
            replace(
                o,
                delta_minutes=o.planned_minutes - base.planned_minutes,
                delta_late_pp=round(100 * (o.late_share - base.late_share), 1),
                anecdotal=o.runs < min_reliable_runs,
            )
            for o in picked
        ]
        return sorted(result, key=lambda o: o.anecdotal)  # stable: keeps duration order

    def trip_risk(
        self, origin: str, dest: str, *, weekdays: Sequence[str], hours: tuple[int, int], late_min: int
    ) -> TripRisk:
        """Direct runs from `origin` to `dest` departing in [hours[0], hours[1]) on `weekdays`."""
        self._require(origin, dest)
        days = [WEEKDAYS[d] for d in weekdays]
        runs, late, cancelled, *bands = self._one(
            """
            select count(*),
                   count(*) filter (where not cancelled and b.arr_delay >= $late),
                   count(*) filter (where cancelled),
                   count(*) filter (where not cancelled and b.arr_delay <= 0),
                   count(*) filter (where not cancelled and b.arr_delay between 1 and 5),
                   count(*) filter (where not cancelled and b.arr_delay between 6 and 15),
                   count(*) filter (where not cancelled and b.arr_delay between 16 and 30),
                   count(*) filter (where not cancelled and b.arr_delay between 31 and 60),
                   count(*) filter (where not cancelled and b.arr_delay > 60)
            from stops a join stops b using (run_id),
                 lateral (select a.departure_is_canceled or b.arrival_is_canceled as cancelled)
            where a.station_name = $o and b.station_name = $d
              and a.planned_at < b.planned_at
              and list_contains($days, dayofweek(a.departure_planned_time))
              and hour(a.departure_planned_time) >= $h0 and hour(a.departure_planned_time) < $h1
            """,
            {"o": origin, "d": dest, "days": days, "h0": hours[0], "h1": hours[1], "late": late_min},
        )
        names = ["on_time_or_early", "1-5", "6-15", "16-30", "31-60", "over_60"]
        return TripRisk(
            runs=runs,
            late=late,
            cancelled=cancelled,
            bands={**dict(zip(names, bands, strict=True)), "cancelled": cancelled},
        )
