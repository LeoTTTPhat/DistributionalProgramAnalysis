from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from dpa.analyzer import PredicateAnalyzer
from dpa.apps import filter_samples
from dpa.eval.metrics import majority_vote_passes, pass_rate, sample_passes
from dpa.posterior import survival_rates
from dpa.task.smoke import (
    ProgramSample,
    build_smoke_samples,
    rolling_max_oracle,
    smoke_tests,
)


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _serialize_invariants(invariants: set[object]) -> list[str]:
    return sorted(str(invariant) for invariant in invariants)


def run_smoketest(run_root: Path = Path("runs/smoketest")) -> dict[str, object]:
    start = time.time()
    samples = build_smoke_samples()
    tests = smoke_tests()
    analyzer = PredicateAnalyzer(tests=tests)
    inferred = {sample.sample_id: analyzer.analyze(sample) for sample in samples}
    posterior = survival_rates(inferred.values(), denominator=len(samples))
    survivors = filter_samples(samples, inferred, posterior, threshold=0.85)

    pick_first = sample_passes(samples[0], tests, rolling_max_oracle)
    self_consistency = majority_vote_passes(samples, tests, rolling_max_oracle)
    dpa_filter = majority_vote_passes(survivors, tests, rolling_max_oracle)
    elapsed = time.time() - start

    result = {
        "task_id": "rolling_max",
        "sample_count": len(samples),
        "test_count": len(tests),
        "unique_invariant_count": len(posterior),
        "mean_invariants_per_sample": round(
            sum(len(values) for values in inferred.values()) / len(samples), 3
        ),
        "survivor_count": len(survivors),
        "pick_first_pass": pick_first,
        "self_consistency_pass": self_consistency,
        "dpa_filter_pass": dpa_filter,
        "raw_sample_pass_rate": round(pass_rate(samples, tests, rolling_max_oracle), 3),
        "survivor_pass_rate": round(pass_rate(survivors, tests, rolling_max_oracle), 3),
        "elapsed_seconds": round(elapsed, 3),
    }

    _write_json(
        run_root / "manifest.json",
        {
            "git_sha": _git_sha(),
            "model_id": "fixed-smoke-samples",
            "analyzer": "dpa.analyzer.PredicateAnalyzer",
            "threshold": 0.85,
        },
    )
    for sample in samples:
        sample_path = run_root / "samples" / f"{sample.sample_id}.py"
        sample_path.parent.mkdir(parents=True, exist_ok=True)
        sample_path.write_text(sample.source, encoding="utf-8")
        _write_json(
            run_root / "invariants" / f"{sample.sample_id}.json",
            _serialize_invariants(inferred[sample.sample_id]),
        )
    _write_json(
        run_root / "posterior.json",
        {str(invariant): survival for invariant, survival in sorted(posterior.items(), key=lambda item: str(item[0]))},
    )
    _write_json(run_root / "result.json", result)
    return result


def main() -> None:
    result = run_smoketest()
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
