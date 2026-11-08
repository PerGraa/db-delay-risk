"""Deterministic checks on one answer, each tied to a failure seen in a real session.

F-numbers refer to evals/baseline-findings.md. Every check gets the full Transcript, so it
can compare the answer text with what the tools actually returned.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from db_delay_risk.evals.transcript import Transcript


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


Check = Callable[[Transcript], CheckResult]


def scope_stated(t: Transcript) -> CheckResult:
    """F7: the answer states the data period and that numbers are historical.

    Not applicable when no tool returned data (e.g. the station does not exist)."""
    scope = _scope(t)
    if not scope:
        return CheckResult("scope_stated", True, "n/a: no data returned")
    missing = [v for v in (scope.get("data_from"), scope.get("data_to")) if v and not _date_in(v, t.answer)]
    historical = (
        re.search(r"historical|not a forecast|historisch|keine prognose", t.answer, re.IGNORECASE) is not None
    )
    detail = ", ".join([*(f"missing {m}" for m in missing), *([] if historical else ["no 'historical'"])])
    return CheckResult("scope_stated", bool(scope) and not missing and historical, detail)


def numbers_traceable(t: Transcript) -> CheckResult:
    """F3/F5: every percentage in the answer equals a share the tools returned (whole percent)."""
    known = _known_percentages(t)
    # "95% range" / "95% interval" names the confidence level, it is not a data value
    text = re.sub(r"95\s?%\s*(range|interval|confidence|CI)", "", t.answer, flags=re.IGNORECASE)
    used = {int(p) for p in re.findall(r"(?<![\d.])(\d{1,3})\s?%", text)}
    unknown = sorted(used - known)
    return CheckResult(
        "numbers_traceable", not unknown, ", ".join(f"{u}% not in tool output" for u in unknown)
    )


def anecdotal_kept_out(t: Transcript) -> CheckResult:
    """F8/N1: options flagged anecdotal never appear as a row of a markdown table."""
    rows = [line for line in t.answer.splitlines() if line.lstrip().startswith("|")]
    # Several options can share a transfer station (S+ICE and S+FLX via Hamburg Hbf),
    # so a row matches an option only if it names the station *and* every leg type.
    leaked = [
        f"{'+'.join(o['legs'])} via {o['via']}"
        for o in t.route_options()
        if o.get("anecdotal") and o.get("via") and any(_row_matches(r, o) for r in rows)
    ]
    return CheckResult("anecdotal_kept_out", not leaked, ", ".join(f"{v} in table" for v in leaked))


def _row_matches(row: str, option: dict[str, Any]) -> bool:
    """The row names the transfer station and the legs in order (ICE+RE is not RE+ICE)."""
    if option["via"] not in row:
        return False
    words = re.findall(r"[A-Za-z]+", row.split(option["via"])[0])  # legs come before "via X"
    legs = [w for w in words if w in {leg for leg in option["legs"]}]
    return legs[: len(option["legs"])] == list(option["legs"])


def reliable_options_mentioned(t: Transcript) -> CheckResult:
    """F4: every non-anecdotal transfer station returned by route_options is named."""
    missing = sorted(
        {o["via"] for o in t.all_route_options() if o.get("via") and not o.get("anecdotal")}
        - {v for v in _all_vias(t) if _station_named(v, t.answer)}
    )
    return CheckResult(
        "reliable_options_mentioned", not missing, ", ".join(f"{m} not mentioned" for m in missing)
    )


def no_raw_eva_ids(t: Transcript) -> CheckResult:
    """Station ids are internal; the traveller should only see names."""
    ids = re.findall(r"\b0?80\d{5}\b", t.answer)
    return CheckResult("no_raw_eva_ids", not ids, ", ".join(ids))


CHECKS: list[Check] = [
    scope_stated,
    numbers_traceable,
    anecdotal_kept_out,
    reliable_options_mentioned,
    no_raw_eva_ids,
]


def run_checks(t: Transcript) -> list[CheckResult]:
    return [check(t) for check in CHECKS]


# Generic words in station names that answers often abbreviate or drop ("Fernbf", "Flughafen").
_GENERIC = {"am", "main", "hbf", "hauptbahnhof", "fernbahnhof", "bahnhof", "bf", "fernbf", "(main)"}


def _station_named(name: str, text: str) -> bool:
    """Exact name, or every distinctive word of it (Frankfurt am Main Flughafen Fernbahnhof ->
    'Frankfurt' and 'Flughafen') appears in the same line."""
    if name in text:
        return True
    words = [w for w in re.split(r"[\s/\-]+", name) if w and w.lower() not in _GENERIC]
    return bool(words) and any(all(w in line for w in words) for line in text.splitlines())


def _date_in(iso: str, text: str) -> bool:
    """ISO date (2026-03-31) or its German form (31.03.2026)."""
    y, m, d = iso.split("-")
    return iso in text or f"{d}.{m}.{y}" in text


def _scope(t: Transcript) -> dict[str, Any]:
    for call in reversed(t.calls):
        if call.result and isinstance(call.result.get("scope"), dict):
            return dict(call.result["scope"])
    return {}


def _all_vias(t: Transcript) -> set[str]:
    return {o["via"] for o in t.all_route_options() if o.get("via")}


def _known_percentages(t: Transcript) -> set[int]:
    """Whole percents a faithful answer could quote: shares, interval bounds, band shares,
    and delta percentage points. Rounding either way is accepted."""
    values: set[float] = set()
    for call in t.calls:
        if not call.result:
            continue
        for o in call.result.get("options", []):
            for k in ("late_share", "missed_share", "late_low", "late_high"):
                if isinstance(o.get(k), int | float):
                    values.add(100 * o[k])
            if isinstance(o.get("delta_late_pp"), int | float):
                values.add(abs(o["delta_late_pp"]))
        for k in ("late_share",):
            if isinstance(call.result.get(k), int | float):
                values.add(100 * call.result[k])
        for b in call.result.get("by_buffer", []):
            values.add(100 * b.get("missed_share", 0))
        runs = call.result.get("runs")
        if isinstance(runs, int) and runs and isinstance(call.result.get("bands"), dict):
            values |= {100 * n / runs for n in call.result["bands"].values()}
    return {int(v) for v in values} | {round(v) for v in values} | {int(v) + 1 for v in values}
