from pathlib import Path

from db_delay_risk.evals.transcript import Transcript

FIXTURES = Path(__file__).parent / "fixtures"


def test_parses_tool_calls_results_answer_and_cost_from_stream_json():
    t = Transcript.parse((FIXTURES / "hamburg-leipzig-skill-haiku.jsonl").read_text())

    assert [c.tool for c in t.calls] == ["find_station", "find_station", "route_options", "trip_risk"]
    assert t.calls[2].args["origin"] == "Hamburg-Altona"
    assert t.calls[2].result["scope"]["data_from"] == "2026-03-31"
    assert t.answer.startswith("**Scope:**")
    assert t.cost_usd > 0
    assert t.turns == 5
    assert not t.is_error


def test_route_options_helper_returns_the_last_route_options_result():
    t = Transcript.parse((FIXTURES / "hamburg-leipzig-skill-haiku.jsonl").read_text())

    opts = t.route_options()

    direct = next(o for o in opts if o["via"] is None)
    assert (direct["runs"], direct["planned_minutes"]) == (53, 235)


def test_ignores_non_json_noise_lines():
    result = '{"type":"result","result":"hi","total_cost_usd":0.1,"num_turns":1,"is_error":false}'
    t = Transcript.parse(f"warning: something\n{result}\n")

    assert (t.answer, t.calls) == ("hi", [])


def test_parses_token_usage_and_duration():
    t = Transcript.parse((FIXTURES / "hamburg-leipzig-skill-haiku.jsonl").read_text())

    assert t.tokens == {"input": 8, "output": 2485, "cache_read": 6789, "cache_write": 5498}
    assert t.duration_s == 19.745
