from conftest import trip

from db_delay_risk import Store

MUC, NUE, BA = ("08000261", "München Hbf"), ("08000284", "Nürnberg Hbf"), ("08000025", "Bamberg")
FRIDAYS = ["2026-09-04", "2026-09-11", "2026-09-18", "2026-09-25"]


def ice_muc_ba(day, ride="r1", arr_delay_ba=0, time="17:19"):
    return trip(
        ride,
        f"{day} {time}",
        "ICE",
        "1002",
        [(*MUC, 0, None, 0), (*NUE, 74, 0, 0), (*BA, 120, arr_delay_ba, None)],
    )


def test_late_share_uses_arrival_delay_at_destination(write_parquet):
    rows = []
    for day, delay in zip(FRIDAYS, [0, 5, 10, 20], strict=True):
        rows += ice_muc_ba(day, arr_delay_ba=delay)
    store = Store.open([write_parquet(rows)])

    risk = store.trip_risk(MUC[1], BA[1], weekdays=["Fri"], hours=(17, 18), late_min=6)

    assert risk.runs == 4
    assert risk.late == 2  # 10 and 20 min are >= 6
    assert risk.cancelled == 0
    assert risk.late_share == 0.5


def test_cancelled_arrival_counts_as_cancelled_not_late(write_parquet):
    rows = ice_muc_ba(FRIDAYS[0], arr_delay_ba="X") + ice_muc_ba(FRIDAYS[1], arr_delay_ba=30)
    store = Store.open([write_parquet(rows)])

    risk = store.trip_risk(MUC[1], BA[1], weekdays=["Fri"], hours=(17, 18), late_min=6)

    assert (risk.runs, risk.late, risk.cancelled) == (2, 1, 1)


def test_filters_weekday_hour_and_direction(write_parquet):
    rows = ice_muc_ba(FRIDAYS[0], arr_delay_ba=30)
    rows += ice_muc_ba("2026-09-05", ride="sat", arr_delay_ba=30)  # Saturday
    rows += ice_muc_ba(FRIDAYS[1], ride="early", arr_delay_ba=30, time="09:00")  # wrong hour
    rows += trip(
        "back",
        f"{FRIDAYS[2]} 17:30",
        "ICE",
        "1003",  # BA -> MUC
        [(*BA, 0, None, 0), (*NUE, 40, 0, 0), (*MUC, 120, 30, None)],
    )
    store = Store.open([write_parquet(rows)])

    risk = store.trip_risk(MUC[1], BA[1], weekdays=["Fri"], hours=(17, 18), late_min=6)

    assert risk.runs == 1


def test_run_crossing_midnight_is_one_run_on_its_departure_day(write_parquet):
    rows = trip(
        "night",
        f"{FRIDAYS[0]} 20:59",
        "ICE",
        "1009",
        [(*MUC, 0, None, 0), (*NUE, 120, 0, 0), (*BA, 190, 7, None)],
    )  # arrives Sat 00:09
    store = Store.open([write_parquet(rows)])

    risk = store.trip_risk(MUC[1], BA[1], weekdays=["Fri"], hours=(20, 21), late_min=6)

    assert (risk.runs, risk.late) == (1, 1)


def test_station_name_covers_all_its_evas(write_parquet):
    muc_s_bahn_id = "08098263"
    rows = trip(
        "r9", f"{FRIDAYS[0]} 17:05", "RE", "4001", [(muc_s_bahn_id, MUC[1], 0, None, 0), (*BA, 150, 9, None)]
    )
    store = Store.open([write_parquet(rows)])

    risk = store.trip_risk(MUC[1], BA[1], weekdays=["Fri"], hours=(17, 18), late_min=6)

    assert (risk.runs, risk.late) == (1, 1)


def test_unknown_station_name_raises(write_parquet):
    import pytest

    from db_delay_risk import UnknownStation

    store = Store.open([write_parquet(ice_muc_ba(FRIDAYS[0]))])

    with pytest.raises(UnknownStation, match="Munich"):
        store.trip_risk("Munich", BA[1], weekdays=["Fri"], hours=(17, 18), late_min=6)


def test_delay_bands_split_every_run_exactly_once(write_parquet):
    rows = []
    days = ["2026-09-04", "2026-09-11", "2026-09-18", "2026-09-25", "2026-10-02", "2026-10-09", "2026-10-16"]
    for day, delay in zip(days, [-1, 0, 5, 6, 20, 75, "X"], strict=True):
        rows += ice_muc_ba(day, ride=day, arr_delay_ba=delay)
    store = Store.open([write_parquet(rows)])

    risk = store.trip_risk(MUC[1], BA[1], weekdays=["Fri"], hours=(17, 18), late_min=6)

    assert risk.bands == {
        "on_time_or_early": 2,
        "1-5": 1,
        "6-15": 1,
        "16-30": 1,
        "31-60": 0,
        "over_60": 1,
        "cancelled": 1,
    }
    assert sum(risk.bands.values()) == risk.runs
