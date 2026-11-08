"""Run the eval matrix and write a report: `uv run db-delay-risk-evals --help`."""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path

import yaml

from db_delay_risk.evals.checks import run_checks
from db_delay_risk.evals.report import RunResult, summarize
from db_delay_risk.evals.runner import RunSpec, prepare_env, run
from db_delay_risk.evals.transcript import Transcript


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cases", default="evals/cases.yaml")
    p.add_argument("--only", nargs="*", help="case ids to run (default: all)")
    p.add_argument("--models", nargs="+", default=["haiku", "sonnet", "opus"])
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--variants", nargs="+", default=["noskill", "skill"], choices=["noskill", "skill"])
    p.add_argument("--parallel", type=int, default=3, help="concurrent claude processes")
    p.add_argument("--settings", required=True, help="settings.json with authentication only")
    p.add_argument("--db", default="data/stops.duckdb")
    p.add_argument("--env-dir", default="evals/.env")
    p.add_argument("--out", default=None, help="results dir (default: evals/results/<timestamp>)")
    a = p.parse_args()

    project = Path.cwd()
    env_dir = Path(a.env_dir).resolve()
    out = Path(a.out or f"evals/results/{time.strftime('%Y%m%d-%H%M%S')}").resolve()
    prepare_env(env_dir, project, Path(a.db).resolve(), Path(a.settings).resolve())

    cases = yaml.safe_load(Path(a.cases).read_text())
    if a.only:
        cases = [c for c in cases if c["id"] in a.only]
    specs = [
        RunSpec(c["id"], c["question"], model, variant == "skill", repeat=r)
        for c in cases
        for model in a.models
        for variant in a.variants
        for r in range(a.repeats)
    ]
    print(f"{len(specs)} runs -> {out}")

    results: list[RunResult] = []
    with ThreadPoolExecutor(max_workers=a.parallel) as pool:
        futures = {pool.submit(run, s, env_dir, out / "transcripts"): s for s in specs}
        for i, fut in enumerate(as_completed(futures), 1):
            spec = futures[fut]
            t = Transcript.parse(fut.result().read_text())
            checks = run_checks(t)
            results.append(
                RunResult(spec.case_id, spec.model, spec.skill, t.cost_usd, t.tokens, t.duration_s, checks)
            )
            failed = [c.name for c in checks if not c.passed]
            print(f"[{i}/{len(specs)}] {spec.run_id} ${t.cost_usd:.4f} {failed if failed else 'OK'}")

    summary = summarize(results)
    (out / "results.jsonl").write_text("\n".join(json.dumps(asdict(r)) for r in results) + "\n")
    (out / "report.md").write_text(summary.to_markdown())
    print("\n" + summary.to_markdown())
