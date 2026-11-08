"""Seam: the summary over many runs, including what the whole run cost."""

from db_delay_risk.evals.checks import CheckResult
from db_delay_risk.evals.report import RunResult, summarize


def rr(model, skill, cost, passed, tokens_out=100):
    checks = [CheckResult("scope_stated", passed), CheckResult("numbers_traceable", True)]
    tokens = {"input": 10, "output": tokens_out, "cache_read": 1000, "cache_write": 500}
    return RunResult(
        case_id="c1", model=model, skill=skill, cost_usd=cost, tokens=tokens, duration_s=10.0, checks=checks
    )


def test_summary_reports_total_cost_and_tokens_for_the_full_run():
    runs = [rr("haiku", False, 0.002, False), rr("haiku", True, 0.003, True), rr("opus", True, 0.05, True)]

    s = summarize(runs)

    assert s.total_cost_usd == 0.055
    assert s.total_tokens == {"input": 30, "output": 300, "cache_read": 3000, "cache_write": 1500}
    assert s.runs == 3


def test_summary_breaks_down_pass_rate_and_cost_per_model_and_variant():
    runs = [rr("haiku", False, 0.002, False), rr("haiku", True, 0.003, True), rr("haiku", True, 0.003, True)]

    s = summarize(runs)

    row = s.rows[("haiku", True)]
    assert (row.runs, row.checks_passed, row.checks_total) == (2, 4, 4)
    assert row.cost_usd == 0.006
    assert s.rows[("haiku", False)].checks_passed == 1


def test_markdown_report_ends_with_the_cost_line():
    s = summarize([rr("haiku", True, 0.003, True)])

    last = s.to_markdown().strip().splitlines()[-1]

    assert last.startswith("**Total cost of this run:** $0.0030")
    assert "1 runs" in last and "tokens" in last
