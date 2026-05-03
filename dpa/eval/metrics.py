from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable

from dpa.task.smoke import ProgramSample, TestCase


Oracle = Callable[[TestCase], object]


def sample_passes(sample: ProgramSample, tests: Iterable[TestCase], oracle: Oracle) -> bool:
    for outcome in sample.run_many(tests):
        if outcome.raised or outcome.result != oracle(outcome.case):
            return False
    return True


def pass_rate(samples: Iterable[ProgramSample], tests: Iterable[TestCase], oracle: Oracle) -> float:
    sample_list = list(samples)
    if not sample_list:
        return 0.0
    return sum(sample_passes(sample, tests, oracle) for sample in sample_list) / len(sample_list)


def majority_vote_passes(samples: Iterable[ProgramSample], tests: Iterable[TestCase], oracle: Oracle) -> bool:
    sample_list = list(samples)
    for case in tests:
        votes: Counter[str] = Counter()
        decoded: dict[str, object] = {}
        for sample in sample_list:
            outcome = sample.run(case)
            if outcome.raised:
                key = f"raised:{outcome.error_type}"
            else:
                key = repr(outcome.result)
                decoded[key] = outcome.result
            votes[key] += 1
        if not votes:
            return False
        winner, _ = votes.most_common(1)[0]
        if winner.startswith("raised:") or decoded.get(winner) != oracle(case):
            return False
    return True
