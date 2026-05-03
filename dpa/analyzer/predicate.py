from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from dpa.invariants import Invariant
from dpa.task.smoke import ProgramSample, TestCase


Predicate = Callable[[TestCase, object], bool]


@dataclass(frozen=True)
class CandidatePredicate:
    invariant: Invariant
    check: Predicate


def _is_sequence(value: object) -> bool:
    return isinstance(value, list)


def _window_count(xs: list[int], k: int) -> int:
    return max(0, len(xs) - k + 1)


def rolling_max_predicates() -> list[CandidatePredicate]:
    return [
        CandidatePredicate(
            Invariant("type", "result is list"),
            lambda case, result: isinstance(result, list),
        ),
        CandidatePredicate(
            Invariant("length_relation", "len(result) <= len(xs)"),
            lambda case, result: _is_sequence(result) and len(result) <= len(case.xs),
        ),
        CandidatePredicate(
            Invariant("length_relation", "len(result) == max(0, len(xs) - k + 1) when k > 0"),
            lambda case, result: _is_sequence(result)
            and (case.k <= 0 or len(result) == _window_count(case.xs, case.k)),
        ),
        CandidatePredicate(
            Invariant("boundary", "result == [] when k <= 0"),
            lambda case, result: case.k > 0 or result == [],
        ),
        CandidatePredicate(
            Invariant("elementwise", "all(result[i] in xs)"),
            lambda case, result: _is_sequence(result)
            and all(value in case.xs for value in result),
        ),
        CandidatePredicate(
            Invariant("elementwise", "all(result[i] >= min(xs)) when xs"),
            lambda case, result: _is_sequence(result)
            and (not case.xs or all(value >= min(case.xs) for value in result)),
        ),
        CandidatePredicate(
            Invariant("postcondition", "result[i] == max(xs[i:i+k]) when k > 0"),
            lambda case, result: _is_sequence(result)
            and (
                case.k <= 0
                or (
                    len(result) == _window_count(case.xs, case.k)
                    and all(
                        result[i] == max(case.xs[i : i + case.k])
                        for i in range(_window_count(case.xs, case.k))
                    )
                )
            ),
        ),
        CandidatePredicate(
            Invariant("boundary", "result == [] when len(xs) < k"),
            lambda case, result: case.k <= 0
            or len(case.xs) >= case.k
            or result == [],
        ),
    ]


class PredicateAnalyzer:
    """Deterministic smoke-test analyzer over a closed invariant vocabulary."""

    def __init__(
        self,
        predicates: Iterable[CandidatePredicate] | None = None,
        tests: Iterable[TestCase] | None = None,
    ) -> None:
        self.predicates = list(predicates or rolling_max_predicates())
        self.tests = list(tests or [])

    def analyze(self, sample: ProgramSample) -> set[Invariant]:
        outcomes = sample.run_many(self.tests)
        invariants: set[Invariant] = set()
        for predicate in self.predicates:
            if outcomes and all(
                not outcome.raised and predicate.check(outcome.case, outcome.result)
                for outcome in outcomes
            ):
                invariants.add(predicate.invariant)
        return invariants
