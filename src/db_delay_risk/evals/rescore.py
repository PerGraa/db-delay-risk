"""Re-run the checks on saved transcripts, without calling the model again.

uv run db-delay-risk-evals-rescore evals/results/<run>
"""

from __future__ import annotations

import sys
from pathlib import Path

from db_delay_risk.evals.checks import run_checks
from db_delay_risk.evals.report import RunResult, summarize
from db_delay_risk.evals.transcript import Transcript


def main() -> None:
    run_dir = Path(sys.argv[1])
    results = []
    for f in sorted((run_dir / "transcripts").glob("*.jsonl")):
        case_id, model, variant, _repeat = f.stem.split("__")
        t = Transcript.parse(f.read_text())
        results.append(
            RunResult(case_id, model, variant == "skill", t.cost_usd, t.tokens, t.duration_s, run_checks(t))
        )
    report = summarize(results).to_markdown()
    (run_dir / "report.md").write_text(report)
    print(report)
