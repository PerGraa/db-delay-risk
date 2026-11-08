from conftest import trip

from db_delay_risk import Store

MUC, IN, NUE = ("08000261", "München Hbf"), ("08000183", "Ingolstadt Hbf"), ("08000284", "Nürnberg Hbf")
BA, WÜ = ("08000025", "Bamberg"), ("08000260", "Würzburg Hbf")
FRI = "2026-09-04"


def ice_direct(day, ba_delay=0):  # MUC 17:00 -> NUE 18:10 -> BA 18:50
    return trip(
        f"ice-{day}",
        f"{day} 17:00",
        "ICE",
        "1002",
        [(*MUC, 0, None, 0), (*NUE, 70, 0, 0), (*BA, 110, ba_delay, None)],
    )


def ice_to_nue(day, nue_delay=0):  # MUC 17:30 -> NUE 18:40
    return trip(
        f"ice2-{day}", f"{day} 17:30", "ICE", "600", [(*MUC, 0, None, 0), (*NUE, 70, nue_delay, None)]
    )


def re_nue_ba(day, start="18:50", ba_delay=0):  # NUE -> BA in 45 min
    return trip(
        f"re-{day}-{start}", f"{day} {start}", "RE", "4010", [(*NUE, 0, None, 0), (*BA, 45, ba_delay, None)]
    )


def options(store, **kw):
    return store.route_options(MUC[1], BA[1], weekdays=["Fri"], hours=(17, 18), **kw)


def test_direct_run_is_a_route_option_without_transfer(write_parquet):
    store = Store.open([write_parquet(ice_direct(FRI))])

    (opt,) = options(store)

    assert opt.via is None
    assert opt.legs == ["ICE"]
    assert opt.planned_minutes == 110


def test_one_transfer_option_pairs_legs_with_enough_planned_transfer_time(write_parquet):
    # ICE arrives NUE 18:40; RE leaves 18:50 (10 min, ok) and 18:42 (2 min, below the 5 min minimum)
    rows = ice_to_nue(FRI) + re_nue_ba(FRI, "18:50") + re_nue_ba(FRI, "18:42")
    store = Store.open([write_parquet(rows)])

    (opt,) = options(store, min_transfer=5)

    assert opt.via == NUE[1]
    assert opt.legs == ["ICE", "RE"]
    assert opt.transfer_minutes == 10
    assert opt.planned_minutes == 70 + 10 + 45


def test_transfer_option_reports_missed_connections(write_parquet):
    # Inbound late 0 and 15 min on two Fridays; 10 min planned transfer -> missed once
    rows = ice_to_nue(FRI, 0) + re_nue_ba(FRI) + ice_to_nue("2026-09-11", 15) + re_nue_ba("2026-09-11")
    store = Store.open([write_parquet(rows)])

    (opt,) = options(store)

    assert (opt.runs, opt.missed) == (2, 1)
    assert opt.missed_share == 0.5


def test_options_are_ordered_by_planned_duration_and_carry_delay_risk(write_parquet):
    rows = ice_direct(FRI, ba_delay=20) + ice_to_nue(FRI) + re_nue_ba(FRI)
    store = Store.open([write_parquet(rows)])

    direct, via_nue = options(store, late_min=6)

    assert (direct.planned_minutes, via_nue.planned_minutes) == (110, 125)
    assert (direct.late, via_nue.late) == (1, 0)


def test_transfer_must_happen_on_the_same_run_date(write_parquet):
    rows = ice_to_nue(FRI) + re_nue_ba("2026-09-11")  # connecting train one week later
    store = Store.open([write_parquet(rows)])

    assert options(store) == []


def test_stop_order_follows_planned_time_not_sequence_number(write_parquet):
    # Diversion stops (is_additional_stop) carry train_line_station_num >= 100 in the source,
    # so the sequence number says "after München" although Ingolstadt is passed first.
    rows = trip(
        "div", f"{FRI} 17:00", "ICE", "1002", [(*NUE, 0, None, 0), (*IN, 60, 0, 0), (*MUC, 120, 0, None)]
    )
    rows[1]["train_line_station_num"] = 100
    store = Store.open([write_parquet(rows)])

    assert store.route_options(IN[1], MUC[1], weekdays=["Fri"], hours=(18, 19)) != []
    assert store.route_options(MUC[1], IN[1], weekdays=["Fri"], hours=(17, 23)) == []


def re_muc_in(day):  # MUC 17:10 -> IN 18:10, regional
    return trip(f"re1-{day}", f"{day} 17:10", "RE", "4101", [(*MUC, 0, None, 0), (*IN, 60, 0, None)])


def re_in_ba(day):  # IN 18:30 -> BA 20:30, regional
    return trip(f"re2-{day}", f"{day} 18:30", "RE", "4103", [(*IN, 0, None, 0), (*BA, 120, 0, None)])


def test_min_runs_drops_rarely_seen_options(write_parquet):
    rows = ice_direct(FRI) + ice_direct("2026-09-11") + ice_to_nue(FRI) + re_nue_ba(FRI)
    store = Store.open([write_parquet(rows)])

    (opt,) = options(store, min_runs=2)

    assert opt.via is None


def ice_nue_ba(day):  # NUE 18:50 -> BA 19:25, long-distance
    return trip(f"ice3-{day}", f"{day} 18:50", "ICE", "800", [(*NUE, 0, None, 0), (*BA, 35, 0, None)])


def test_limit_keeps_the_fastest_option_of_each_service_class(write_parquet):
    # Options: ICE direct (110), ICE+ICE (115), ICE+RE (130), RE+RE via Ingolstadt (200).
    # limit=3 must keep one per class (long-distance, mixed, regional) and drop ICE+ICE,
    # although it is faster than the regional one: the slow, regional route is the
    # alternative a traveller asks about.
    rows = ice_direct(FRI) + ice_to_nue(FRI) + ice_nue_ba(FRI) + re_nue_ba(FRI, "18:55")
    rows += re_muc_in(FRI) + re_in_ba(FRI)
    store = Store.open([write_parquet(rows)])

    opts = options(store, limit=3)

    assert [(o.service_class, o.legs) for o in opts] == [
        ("long-distance", ["ICE"]),
        ("mixed", ["ICE", "RE"]),
        ("regional", ["RE", "RE"]),
    ]


def test_transfer_pairs_with_first_onward_train_of_each_service_class(write_parquet):
    # At Nürnberg an ICE leaves 18:50 and an RE 18:55: both connections are real options.
    rows = ice_to_nue(FRI) + ice_nue_ba(FRI) + re_nue_ba(FRI, "18:55")
    store = Store.open([write_parquet(rows)])

    assert sorted(o.legs for o in options(store)) == [["ICE", "ICE"], ["ICE", "RE"]]


def test_service_class_of_legs():
    from db_delay_risk.store import service_class

    assert service_class(["ICE"]) == "long-distance"
    assert service_class(["ICE", "RE"]) == "mixed"
    assert service_class(["ag", "BRB"]) == "regional"
    assert service_class(["RE", "Bus"]) == "road"
    assert service_class(["RE", "SEV"]) == "road"


def test_regional_inbound_is_kept_when_a_faster_ice_reaches_the_same_connection(write_parquet):
    # RE leaves MUC 17:05, ICE leaves 17:30; both reach NUE before the 18:50 RE to Bamberg.
    # The ICE wins for a traveller who takes any train, but regional-only is its own option.
    re_muc_nue = trip("re0", f"{FRI} 17:05", "RE", "4001", [(*MUC, 0, None, 0), (*NUE, 95, 0, None)])
    rows = re_muc_nue + ice_to_nue(FRI) + re_nue_ba(FRI)
    store = Store.open([write_parquet(rows)])

    assert sorted(o.legs for o in options(store, limit=5) if o.via) == [["ICE", "RE"], ["RE", "RE"]]


def test_options_carry_differences_to_the_fastest_frequent_option(write_parquet):
    # Baseline = fastest option with at least min_runs runs (here: ICE direct, 110 min, 2 runs, 1 late).
    rows = ice_direct(FRI, ba_delay=20) + ice_direct("2026-09-11")
    rows += ice_to_nue(FRI) + re_nue_ba(FRI) + ice_to_nue("2026-09-11") + re_nue_ba("2026-09-11")
    store = Store.open([write_parquet(rows)])

    direct, via_nue = options(store, min_runs=2)

    assert (direct.delta_minutes, direct.delta_late_pp) == (0, 0.0)
    assert via_nue.delta_minutes == 125 - 110
    assert via_nue.delta_late_pp == -50.0  # 0% late vs 50% late


ERL = ("08001844", "Erlangen")


def test_same_journey_reachable_at_two_transfer_stations_is_counted_once_and_deterministically(write_parquet):
    # ICE MUC -> NUE arr 18:10 -> ERL arr 18:25; RE NUE dep 18:30 -> ERL dep 18:47 -> BA.
    # The traveller can change at NUE (20 min) or ERL (22 min): one journey, not two,
    # and always the same transfer station (the one with the longer planned transfer).
    ice = trip(
        "ice", f"{FRI} 17:00", "ICE", "600", [(*MUC, 0, None, 0), (*NUE, 70, 0, 0), (*ERL, 85, 0, None)]
    )
    re_ = trip("re", f"{FRI} 18:30", "RE", "4010", [(*NUE, 0, None, 0), (*ERL, 15, 0, 0), (*BA, 45, 0, None)])
    store = Store.open([write_parquet(ice + re_)])

    results = {tuple((o.via, o.runs) for o in options(store)) for _ in range(20)}

    assert results == {((ERL[1], 1),)}


def test_baseline_is_the_direct_option_when_there_is_one(write_parquet):
    # A rarely seen transfer option is faster than the direct ICE; deltas still refer to direct.
    fast_rare = trip("x1", f"{FRI} 17:00", "ICE", "9", [(*MUC, 0, None, 0), (*NUE, 60, 0, None)])
    fast_rare += trip("x2", f"{FRI} 18:05", "ICE", "8", [(*NUE, 0, None, 0), (*BA, 35, 0, None)])
    store = Store.open([write_parquet(ice_direct(FRI) + fast_rare)])

    opts = options(store)

    direct = next(o for o in opts if o.via is None)
    assert direct.delta_minutes == 0
    assert opts[0].via is not None and opts[0].delta_minutes < 0


def test_rarely_seen_options_are_flagged_anecdotal_and_sorted_last(write_parquet):
    # Direct ICE seen twice, a faster transfer option seen once; threshold 2 runs.
    rows = ice_direct(FRI) + ice_direct("2026-09-11")
    rows += trip("x1", f"{FRI} 17:00", "ICE", "9", [(*MUC, 0, None, 0), (*NUE, 60, 0, None)])
    rows += trip("x2", f"{FRI} 18:05", "ICE", "8", [(*NUE, 0, None, 0), (*BA, 35, 0, None)])
    store = Store.open([write_parquet(rows)])

    opts = options(store, min_reliable_runs=2)

    assert [(o.via, o.anecdotal) for o in opts] == [(None, False), (NUE[1], True)]


def test_late_share_comes_with_a_95_percent_wilson_interval(write_parquet):
    # 1 late of 2 runs: Wilson 95% interval is about 9.5%..90.5%
    rows = ice_direct(FRI, ba_delay=20) + ice_direct("2026-09-11")
    store = Store.open([write_parquet(rows)])

    (opt,) = options(store)

    assert (round(opt.late_low, 3), round(opt.late_high, 3)) == (0.095, 0.905)
