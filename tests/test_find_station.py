from conftest import trip

from db_delay_risk import Store

MUC, NUE, BA = ("08000261", "München Hbf"), ("08000284", "Nürnberg Hbf"), ("08000025", "Bamberg")
MUC_S = ("08098263", "München Hbf")  # same station, S-Bahn tunnel id
PASING = ("08004158", "München-Pasing")


def store_with_stations(write_parquet):
    rows = trip(
        "r1", "2026-09-04 17:19", "ICE", "1002", [(*MUC, 0, None, 0), (*NUE, 74, 0, 0), (*BA, 120, 0, None)]
    )
    rows += trip("r2", "2026-09-04 18:00", "S", "8", [(*MUC_S, 0, None, 0), (*PASING, 10, 0, None)])
    return Store.open([write_parquet(rows)])


def test_one_station_per_name_with_all_its_evas(write_parquet):
    store = store_with_stations(write_parquet)

    (hit, *_) = store.find_station("München Hbf")

    assert hit.name == "München Hbf"
    assert sorted(hit.evas) == sorted([MUC[0], MUC_S[0]])
    assert hit.stops == 2


def test_matches_without_umlauts_and_case(write_parquet):
    store = store_with_stations(write_parquet)

    hits = store.find_station("munchen hbf")

    assert hits[0].name == "München Hbf"


def test_exact_name_ranks_before_other_matches(write_parquet):
    store = store_with_stations(write_parquet)

    hits = store.find_station("München")

    assert [h.name for h in hits] == ["München Hbf", "München-Pasing"]


def test_unknown_station_returns_empty(write_parquet):
    assert store_with_stations(write_parquet).find_station("Hogwarts") == []
