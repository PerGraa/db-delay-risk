"""Seam 3: the MCP server end to end, through an in-process MCP client."""

import pytest
from conftest import trip
from mcp import Client

from db_delay_risk import Store
from db_delay_risk.server import make_server

MUC, NUE, BA = ("08000261", "München Hbf"), ("08000284", "Nürnberg Hbf"), ("08000025", "Bamberg")

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def server(write_parquet):
    rows = trip(
        "r1", "2026-09-04 17:00", "ICE", "1002", [(*MUC, 0, None, 0), (*NUE, 70, 0, 0), (*BA, 110, 12, None)]
    )
    return make_server(Store.open([write_parquet(rows)]))


async def test_lists_read_only_tools(server):
    async with Client(server) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}

    assert set(tools) == {"find_station", "trip_risk", "connection_risk", "route_options"}
    assert all(t.annotations and t.annotations.read_only_hint for t in tools.values())


async def test_trip_risk_returns_counts_and_shares(server):
    async with Client(server) as client:
        result = await client.call_tool(
            "trip_risk",
            {"origin": MUC[1], "dest": BA[1], "weekdays": ["Fri"], "hour_from": 17, "hour_to": 18},
        )

    assert not result.is_error
    out = result.structured_content
    assert {k: out[k] for k in ("runs", "late", "cancelled", "late_share", "late_min")} == {
        "runs": 1,
        "late": 1,
        "cancelled": 0,
        "late_share": 1.0,
        "late_min": 6,
    }
    assert out["bands"]["6-15"] == 1


async def test_find_station_resolves_names(server):
    async with Client(server) as client:
        result = await client.call_tool("find_station", {"query": "nurnberg"})

    assert result.structured_content == {"stations": [{"name": NUE[1], "evas": [NUE[0]], "stops": 1}]}


async def test_route_options_and_connection_risk_answer(server):
    async with Client(server) as client:
        routes = await client.call_tool(
            "route_options",
            {
                "origin": MUC[1],
                "dest": BA[1],
                "weekdays": ["Fri"],
                "hour_from": 17,
                "hour_to": 18,
                "min_runs": 1,
            },
        )
        conn = await client.call_tool(
            "connection_risk",
            {"origin": MUC[1], "transfer": NUE[1], "weekdays": ["Fri"], "hour_from": 17, "hour_to": 18},
        )

    (opt,) = routes.structured_content["options"]
    assert (opt["legs"], opt["service_class"]) == (["ICE"], "long-distance")
    assert conn.structured_content["runs"] == 1


async def test_unknown_weekday_is_a_clear_tool_error(server):
    async with Client(server) as client:
        result = await client.call_tool(
            "trip_risk",
            {"origin": MUC[1], "dest": BA[1], "weekdays": ["Freitag"], "hour_from": 17, "hour_to": 18},
        )

    assert result.is_error
    assert "Mon" in result.content[0].text


async def test_unknown_station_is_a_clear_tool_error(server):
    async with Client(server) as client:
        result = await client.call_tool(
            "trip_risk",
            {"origin": "Munich", "dest": BA[1], "weekdays": ["Fri"], "hour_from": 17, "hour_to": 18},
        )

    assert result.is_error
    assert "find_station" in result.content[0].text


async def test_every_answer_states_the_data_period_and_window(server):
    args = {"origin": MUC[1], "dest": BA[1], "weekdays": ["Fri"], "hour_from": 17, "hour_to": 18}
    async with Client(server) as client:
        results = [
            await client.call_tool("trip_risk", args),
            await client.call_tool("route_options", {**args, "min_runs": 1}),
            await client.call_tool(
                "connection_risk",
                {"origin": MUC[1], "transfer": NUE[1], "weekdays": ["Fri"], "hour_from": 17, "hour_to": 18},
            ),
        ]

    for r in results:
        assert r.structured_content["scope"] == {
            "data_from": "2026-09-04",
            "data_to": "2026-09-04",
            "weekdays": ["Fri"],
            "departure_hours": "17:00-18:00",
            "timezone": "Europe/Berlin",
            "kind": "historical frequencies, not a forecast",
        }


async def test_route_options_expose_anecdotal_flag_and_late_interval(server):
    async with Client(server) as client:
        r = await client.call_tool(
            "route_options",
            {
                "origin": MUC[1],
                "dest": BA[1],
                "weekdays": ["Fri"],
                "hour_from": 17,
                "hour_to": 18,
                "min_runs": 1,
            },
        )

    (opt,) = r.structured_content["options"]
    assert opt["anecdotal"] is True  # 1 run < default 30
    assert opt["late_low"] < opt["late_share"] <= opt["late_high"]
