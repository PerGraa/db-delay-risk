from conftest import trip

from db_delay_risk import Store

MUC, NUE, BA = ("08000261", "München Hbf"), ("08000284", "Nürnberg Hbf"), ("08000025", "Bamberg")
FRIDAYS = ["2026-09-04", "2026-09-11", "2026-09-18", "2026-09-25", "2026-10-02"]


def inbound(day, nue_arr_delay):
    return trip(day, f"{day} 17:19", "ICE", "1002", [(*MUC, 0, None, 0), (*NUE, 74, nue_arr_delay, 0)])


def test_missed_share_per_transfer_buffer(write_parquet):
    rows = []
    for day, delay in zip(FRIDAYS, [0, 4, 8, 12, "X"], strict=True):
        rows += inbound(day, delay)
    store = Store.open([write_parquet(rows)])

    risk = store.connection_risk(MUC[1], NUE[1], weekdays=["Fri"], hours=(17, 18), buffers=[5, 10])

    assert risk.runs == 5
    assert risk.missed == {5: 3, 10: 2}  # 8, 12, cancelled | 12, cancelled
    assert risk.missed_share(10) == 0.4
