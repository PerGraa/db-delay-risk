"""Builds tiny Parquet files shaped like piebro/deutsche-bahn-data monthly_processed_data."""

from datetime import datetime, timedelta

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

TS = pa.timestamp("ns")
SCHEMA = pa.schema(
    [
        ("id", pa.string()),
        ("eva", pa.string()),
        ("station_name", pa.string()),
        ("train_type", pa.string()),
        ("train_number", pa.string()),
        ("line_number", pa.string()),
        ("train_line_ride_id", pa.string()),
        ("train_line_station_num", pa.int64()),
        ("arrival_planned_time", TS),
        ("arrival_change_time", TS),
        ("departure_planned_time", TS),
        ("departure_change_time", TS),
        ("arrival_is_canceled", pa.bool_()),
        ("departure_is_canceled", pa.bool_()),
        ("delay_in_min", pa.int32()),
        ("time", TS),
    ]
)


def trip(ride, start, train_type, number, stops):
    """One run of a train. `stops` = [(eva, name, minutes_after_start, arr_delay, dep_delay)].

    Use None for the arrival at the first stop and the departure at the last stop.
    A delay of "X" marks that event as cancelled.
    """
    rows = []
    start_dt = datetime.fromisoformat(start)
    for seq, (eva, name, offset, arr_delay, dep_delay) in enumerate(stops, start=1):
        planned = start_dt + timedelta(minutes=offset)
        first, last = seq == 1, seq == len(stops)
        arr_p = None if first else planned
        dep_p = None if last else planned + timedelta(minutes=0 if first else 2)
        arr_c = arr_p + timedelta(minutes=arr_delay) if arr_p and arr_delay != "X" else None
        dep_c = dep_p + timedelta(minutes=dep_delay) if dep_p and dep_delay != "X" else None
        delay = dep_delay if not last else arr_delay
        rows.append(
            {
                "id": f"{ride}-{start_dt:%y%m%d%H%M}-{seq}",
                "eva": eva,
                "station_name": name,
                "train_type": train_type,
                "train_number": number,
                "line_number": None,
                "train_line_ride_id": ride,
                "train_line_station_num": seq,
                "arrival_planned_time": arr_p,
                "arrival_change_time": arr_c or arr_p,
                "departure_planned_time": dep_p,
                "departure_change_time": dep_c or dep_p,
                "arrival_is_canceled": arr_delay == "X",
                "departure_is_canceled": dep_delay == "X",
                "delay_in_min": 0 if delay in (None, "X") else delay,
                "time": (dep_c or dep_p) if not last else (arr_c or arr_p),
            }
        )
    return rows


@pytest.fixture
def write_parquet(tmp_path):
    def _write(rows, name="data-2026-09.parquet"):
        path = tmp_path / name
        pq.write_table(pa.Table.from_pylist(rows, schema=SCHEMA), path)
        return path

    return _write
