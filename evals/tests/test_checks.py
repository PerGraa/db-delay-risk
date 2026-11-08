"""Seam: deterministic checks, (Transcript) -> CheckResult. Built from hand-made transcripts."""

from db_delay_risk.evals.checks import (
    anecdotal_kept_out,
    no_raw_eva_ids,
    numbers_traceable,
    reliable_options_mentioned,
    scope_stated,
)
from db_delay_risk.evals.transcript import ToolCall, Transcript

SCOPE = {"data_from": "2026-03-31", "data_to": "2026-10-01"}


def opt(via, legs, runs, late, anecdotal=False, missed=0.0, planned=114):
    return {
        "via": via,
        "legs": legs,
        "runs": runs,
        "late_share": late,
        "missed_share": missed,
        "anecdotal": anecdotal,
        "planned_minutes": planned,
        "delta_minutes": 0,
        "delta_late_pp": 0.0,
        "late_low": 0.0,
        "late_high": 1.0,
    }


DIRECT = opt(None, ["ICE"], 132, 0.51)
VIA_NUE = opt("Nürnberg Hbf", ["ICE", "RE"], 173, 0.46, missed=0.40, planned=121)
RARE = opt("Erlangen", ["S", "FLX"], 23, 0.48, anecdotal=True, planned=126)


def transcript(answer, options=(DIRECT, VIA_NUE, RARE)):
    call = ToolCall("route_options", {}, {"scope": SCOPE, "options": list(options)})
    return Transcript(calls=[call], answer=answer)


def test_scope_needs_data_period_and_not_a_forecast():
    ok = transcript("**Scope:** 2026-03-31 to 2026-10-01 · Fri · historical frequencies, not a forecast")
    missing = transcript("ICE direct is 51% late.")

    assert scope_stated(ok).passed
    assert not scope_stated(missing).passed


def test_numbers_must_come_from_tool_output():
    ok = transcript("ICE direct 51% late (132 runs); via Nürnberg Hbf 46%, 40% missed, 121 min.")
    invented = transcript("ICE direct 51% late; via Nürnberg Hbf 38% late.")

    assert numbers_traceable(ok).passed
    result = numbers_traceable(invented)
    assert not result.passed
    assert "38%" in result.detail


def test_anecdotal_option_must_not_appear_in_the_main_table():
    table = "| Option | Runs | Late |\n|---|---|---|\n| ICE direct | 132 | 51% |\n"
    ok = transcript(table + "\n**Anecdotal:** S + FLX via Erlangen, 23 runs, 48%")
    leaked = transcript(table + "| S + FLX via Erlangen | 23 | 48% |\n")

    assert anecdotal_kept_out(ok).passed
    assert not anecdotal_kept_out(leaked).passed


def test_every_reliable_option_is_mentioned():
    ok = transcript("ICE direct 51%. ICE + RE via Nürnberg Hbf 46%.")
    missing = transcript("Take the ICE direct, 51% late.")

    assert reliable_options_mentioned(ok).passed
    result = reliable_options_mentioned(missing)
    assert not result.passed
    assert "Nürnberg Hbf" in result.detail


def test_answer_must_not_show_raw_eva_ids():
    assert no_raw_eva_ids(transcript("München Hbf → Bamberg")).passed
    assert not no_raw_eva_ids(transcript("From 08000261 to Bamberg")).passed


def test_anecdotal_check_tells_options_at_the_same_station_apart_by_legs():
    # Real case: S+ICE via Hamburg Hbf is reliable, S+FLX via Hamburg Hbf is anecdotal.
    reliable = opt("Hamburg Hbf", ["S", "ICE"], 68, 0.85, planned=214)
    rare = opt("Hamburg Hbf", ["S", "FLX"], 23, 0.48, anecdotal=True, planned=238)
    table = "| Option | Runs | Late |\n|---|---|---|\n| S + ICE via Hamburg Hbf | 68 | 85% |\n"
    t_ok = transcript(table + "\n**Anecdotal:** S + FLX via Hamburg Hbf, 23 runs", options=(reliable, rare))
    t_leak = transcript(table + "| S + FLX via Hamburg Hbf | 23 | 48% |\n", options=(reliable, rare))

    assert anecdotal_kept_out(t_ok).passed
    assert not anecdotal_kept_out(t_leak).passed


def test_confidence_level_label_is_not_a_data_value():
    t = transcript("| Option | Late, 95% range |\n| ICE direct | 51% |\nThe 95% ranges overlap.")

    assert numbers_traceable(t).passed


def test_scope_is_not_required_when_no_tool_returned_data():
    t = Transcript(
        calls=[ToolCall("find_station", {"query": "Hogwarts"}, {"stations": []})], answer="No such station."
    )

    assert scope_stated(t).passed


def test_scope_accepts_german_date_format_and_wording():
    t = transcript(
        "**Scope:** 31.03.2026 bis 01.10.2026 · Sonntag · historische Häufigkeiten, keine Prognose"
    )

    assert scope_stated(t).passed


def test_options_from_every_route_options_call_count_when_comparing_windows():
    # Comparison questions call route_options once per window; an option is "mentioned"
    # if the answer names it, whichever call returned it, and missing ones from any call count.
    tue = ToolCall("route_options", {}, {"scope": SCOPE, "options": [DIRECT, VIA_NUE]})
    fri = ToolCall("route_options", {}, {"scope": SCOPE, "options": [DIRECT]})
    both = Transcript(
        calls=[tue, fri], answer="Tuesday: ICE direct 51%, via Nürnberg Hbf 46%. Friday: ICE direct."
    )
    missing = Transcript(calls=[tue, fri], answer="Tuesday: ICE direct 51%. Friday: ICE direct.")

    assert reliable_options_mentioned(both).passed
    assert not reliable_options_mentioned(missing).passed


def test_abbreviated_station_name_counts_as_mentioned():
    airport = opt("Frankfurt am Main Flughafen Fernbahnhof", ["ICE", "ICE"], 242, 0.83)
    t = transcript("| ICE + ICE via Frankfurt Flughafen Fernbf | 242 | 83% |", options=(DIRECT, airport))
    other = transcript("| ICE + ICE via Frankfurt Hbf | 242 | 83% |", options=(DIRECT, airport))

    assert reliable_options_mentioned(t).passed
    assert not reliable_options_mentioned(other).passed


def test_anecdotal_check_respects_leg_order():
    # Real case: ICE+RE via Ingolstadt (51 runs) is reliable, RE+ICE via Ingolstadt (26) is not.
    ice_re = opt("Ingolstadt Hbf", ["ICE", "RE"], 51, 0.55)
    re_ice = opt("Ingolstadt Hbf", ["RE", "ICE"], 26, 0.60, anecdotal=True)
    table = "| Option | Runs |\n|---|---|\n| ICE + RE via Ingolstadt Hbf (5 min transfer) | 51 |\n"

    assert anecdotal_kept_out(transcript(table, options=(ice_re, re_ice))).passed
    leak = table + "| RE + ICE via Ingolstadt Hbf | 26 |\n"
    assert not anecdotal_kept_out(transcript(leak, options=(ice_re, re_ice))).passed
