"""MCP server exposing the delay-risk Domain API as read-only tools.

Thin layer: argument validation and JSON shapes only. All logic lives in `Store`.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations

from db_delay_risk.store import WEEKDAYS, Store, UnknownStation

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)
DEFAULT_BUFFERS = [2, 5, 10, 15, 20, 30]


def _check(weekdays: list[str], hour_from: int, hour_to: int) -> None:
    unknown = [d for d in weekdays if d not in WEEKDAYS]
    if unknown:
        raise ToolError(f"Unknown weekday(s) {unknown}; use any of {list(WEEKDAYS)}")
    if not 0 <= hour_from < hour_to <= 24:
        raise ToolError("Need 0 <= hour_from < hour_to <= 24 (local time, Europe/Berlin)")


@contextmanager
def _station_errors() -> Iterator[None]:
    """Unknown station names are the model's mistake to fix, so its message must reach it."""
    try:
        yield
    except UnknownStation as e:
        raise ToolError(str(e)) from e


def make_server(store: Store) -> MCPServer:
    data_from, data_to = store.period()

    def scope(weekdays: list[str], hour_from: int, hour_to: int) -> dict[str, Any]:
        """Stated in every answer so the model always reports what the numbers cover."""
        return {
            "data_from": data_from,
            "data_to": data_to,
            "weekdays": weekdays,
            "departure_hours": f"{hour_from:02d}:00-{hour_to:02d}:00",
            "timezone": "Europe/Berlin",
            "kind": "historical frequencies, not a forecast",
        }

    server = MCPServer(
        "db-delay-risk",
        instructions=(
            "Historical delay statistics for Deutsche Bahn trips, from observed stops "
            "(open data, CC BY 4.0). Numbers describe the past, not a forecast. "
            "Resolve exact station names with find_station first; other tools take those names."
        ),
    )

    @server.tool(annotations=READ_ONLY)
    def find_station(query: str, limit: int = 10) -> dict[str, Any]:
        """Find stations by name, ignoring case and umlauts. Returns the exact names the
        other tools expect, their EVA ids, and how many stops back each one (a proxy for how
        much data exists)."""
        return {"stations": [asdict(s) for s in store.find_station(query, limit)]}

    @server.tool(annotations=READ_ONLY)
    def trip_risk(
        origin: str, dest: str, weekdays: list[str], hour_from: int, hour_to: int, late_min: int = 6
    ) -> dict[str, Any]:
        """Direct runs origin -> dest departing in [hour_from, hour_to) on the given weekdays
        (Mon..Sun): how many arrived >= late_min minutes late or were cancelled."""
        _check(weekdays, hour_from, hour_to)
        with _station_errors():
            r = store.trip_risk(
                origin, dest, weekdays=weekdays, hours=(hour_from, hour_to), late_min=late_min
            )
        return {
            **asdict(r),
            "late_share": r.late_share,
            "late_min": late_min,
            "scope": scope(weekdays, hour_from, hour_to),
        }

    @server.tool(annotations=READ_ONLY)
    def connection_risk(
        origin: str,
        transfer: str,
        weekdays: list[str],
        hour_from: int,
        hour_to: int,
        buffers: list[int] | None = None,
    ) -> dict[str, Any]:
        """For runs origin -> transfer departing in the window: the share arriving at the
        transfer station later than each buffer (minutes). Cancelled counts as missed."""
        _check(weekdays, hour_from, hour_to)
        bs = buffers or DEFAULT_BUFFERS
        with _station_errors():
            r = store.connection_risk(
                origin, transfer, weekdays=weekdays, hours=(hour_from, hour_to), buffers=bs
            )
        return {
            "scope": scope(weekdays, hour_from, hour_to),
            "runs": r.runs,
            "by_buffer": [
                {"buffer_min": b, "missed": r.missed[b], "missed_share": r.missed_share(b)} for b in bs
            ],
        }

    @server.tool(annotations=READ_ONLY)
    def route_options(
        origin: str,
        dest: str,
        weekdays: list[str],
        hour_from: int,
        hour_to: int,
        late_min: int = 6,
        min_transfer: int = 5,
        min_runs: int = 3,
        min_reliable_runs: int = 30,
        limit: int = 8,
    ) -> dict[str, Any]:
        """Direct and one-transfer route options origin -> dest, ordered by planned duration.
        Each has service_class (long-distance / mixed / regional / road), run count, planned
        minutes, planned transfer minutes, and missed / late / cancelled counts and shares.
        A missed connection counts as late. late_low..late_high is the 95% interval of
        late_share. The fastest option of every service class is always included; options
        seen fewer than min_runs times are dropped, those under min_reliable_runs are kept
        but marked anecdotal and listed last."""
        _check(weekdays, hour_from, hour_to)
        with _station_errors():
            opts = store.route_options(
                origin,
                dest,
                weekdays=weekdays,
                hours=(hour_from, hour_to),
                late_min=late_min,
                min_transfer=min_transfer,
                min_runs=min_runs,
                min_reliable_runs=min_reliable_runs,
                limit=limit,
            )
        return {
            "scope": scope(weekdays, hour_from, hour_to),
            "options": [
                {
                    **asdict(o),
                    "service_class": o.service_class,
                    "missed_share": o.missed_share,
                    "late_share": o.late_share,
                    "late_low": round(o.late_low, 3),
                    "late_high": round(o.late_high, 3),
                }
                for o in opts
            ],
        }

    return server


def main() -> None:
    db_file = os.environ.get("DB_DELAY_RISK_DB", "data/stops.duckdb")
    make_server(Store.load(db_file)).run()
