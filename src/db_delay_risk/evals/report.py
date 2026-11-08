"""Aggregate many runs into one table, ending with what the whole eval run cost."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from db_delay_risk.evals.checks import CheckResult

TOKEN_KINDS = ("input", "output", "cache_read", "cache_write")


@dataclass(frozen=True)
class RunResult:
    case_id: str
    model: str
    skill: bool
    cost_usd: float
    tokens: dict[str, int]
    duration_s: float
    checks: list[CheckResult]


@dataclass
class Row:
    runs: int = 0
    checks_passed: int = 0
    checks_total: int = 0
    cost_usd: float = 0.0
    duration_s: float = 0.0
    failures: dict[str, int] = field(default_factory=lambda: defaultdict(int))


@dataclass
class Summary:
    rows: dict[tuple[str, bool], Row]
    runs: int
    total_cost_usd: float
    total_tokens: dict[str, int]

    def to_markdown(self) -> str:
        lines = [
            "| Model | Skill | Runs | Checks passed | Pass rate | Most failed | Cost | Cost/run | Avg time |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for (model, skill), r in sorted(self.rows.items()):
            worst = ", ".join(f"{k} x{v}" for k, v in sorted(r.failures.items(), key=lambda kv: -kv[1])[:2])
            lines.append(
                f"| {model} | {'yes' if skill else 'no'} | {r.runs} | {r.checks_passed}/{r.checks_total} "
                f"| {r.checks_passed / r.checks_total:.0%} | {worst or '—'} | ${r.cost_usd:.4f} "
                f"| ${r.cost_usd / r.runs:.4f} | {r.duration_s / r.runs:.0f} s |"
            )
        t = self.total_tokens
        lines += [
            "",
            f"**Total cost of this run:** ${self.total_cost_usd:.4f} for {self.runs} runs · tokens: "
            f"{t['input']:,} input, {t['output']:,} output, {t['cache_read']:,} cache read, "
            f"{t['cache_write']:,} cache write",
        ]
        return "\n".join(lines) + "\n"


def summarize(results: list[RunResult]) -> Summary:
    rows: dict[tuple[str, bool], Row] = defaultdict(Row)
    totals = dict.fromkeys(TOKEN_KINDS, 0)
    for res in results:
        row = rows[(res.model, res.skill)]
        row.runs += 1
        row.cost_usd += res.cost_usd
        row.duration_s += res.duration_s
        row.checks_total += len(res.checks)
        row.checks_passed += sum(c.passed for c in res.checks)
        for c in res.checks:
            if not c.passed:
                row.failures[c.name] += 1
        for k in TOKEN_KINDS:
            totals[k] += res.tokens.get(k, 0)
    for row in rows.values():
        row.cost_usd = round(row.cost_usd, 6)
    return Summary(
        rows=dict(rows),
        runs=len(results),
        total_cost_usd=round(sum(r.cost_usd for r in results), 6),
        total_tokens=totals,
    )
