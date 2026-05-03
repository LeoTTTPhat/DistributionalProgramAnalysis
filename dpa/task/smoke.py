from __future__ import annotations

from dataclasses import dataclass
from types import FunctionType
from typing import Any


@dataclass(frozen=True)
class TestCase:
    xs: list[int]
    k: int


@dataclass(frozen=True)
class Outcome:
    case: TestCase
    result: Any = None
    raised: bool = False
    error_type: str | None = None


@dataclass(frozen=True)
class ProgramSample:
    sample_id: str
    source: str
    entry_point: str = "rolling_max"

    def function(self) -> FunctionType:
        namespace: dict[str, object] = {}
        exec(self.source, namespace)
        function = namespace[self.entry_point]
        if not isinstance(function, FunctionType):
            raise TypeError(f"{self.entry_point} is not a function")
        return function

    def run(self, case: TestCase) -> Outcome:
        try:
            result = self.function()(list(case.xs), case.k)
            return Outcome(case=case, result=result)
        except Exception as exc:
            return Outcome(case=case, raised=True, error_type=type(exc).__name__)

    def run_many(self, cases: list[TestCase]) -> list[Outcome]:
        return [self.run(case) for case in cases]


def rolling_max_oracle(case: TestCase) -> list[int]:
    if case.k <= 0 or len(case.xs) < case.k:
        return []
    return [
        max(case.xs[index : index + case.k])
        for index in range(len(case.xs) - case.k + 1)
    ]


def smoke_tests() -> list[TestCase]:
    return [
        TestCase([1, 3, 2, 5, 4], 3),
        TestCase([4, 1, 2], 1),
        TestCase([4, 1, 2], 5),
        TestCase([], 3),
        TestCase([2, 2, 1], 2),
        TestCase([-3, -1, -2, -4], 2),
        TestCase([9, 7, 8], 0),
    ]


def build_smoke_samples() -> list[ProgramSample]:
    sources = {
        "s00_slice": """
def rolling_max(xs, k):
    if k <= 0:
        return []
    return [max(xs[i:i+k]) for i in range(len(xs)-k+1)]
""",
        "s01_deque": """
def rolling_max(xs, k):
    if k <= 0:
        return []
    out, dq = [], []
    for i, x in enumerate(xs):
        while dq and dq[0] <= i - k:
            dq.pop(0)
        while dq and xs[dq[-1]] < x:
            dq.pop()
        dq.append(i)
        if i >= k - 1:
            out.append(xs[dq[0]])
    return out
""",
        "s02_left_prefix": """
def rolling_max(xs, k):
    if k <= 0:
        return []
    return [max(xs[max(0, i-k+1):i+1]) for i in range(len(xs))]
""",
        "s03_too_short_single": """
def rolling_max(xs, k):
    if k <= 0:
        return []
    return [max(xs[i:i+k]) for i in range(len(xs)-k+1)]
""",
        "s04_missing_guard": """
def rolling_max(xs, k):
    if k <= 0:
        return []
    return [max(xs[i:i+k]) for i in range(len(xs)-k+1)]
""",
        "s05_off_by_one": """
def rolling_max(xs, k):
    if k <= 0:
        return []
    return [max(xs[i:i+k]) for i in range(max(0, len(xs)-k))]
""",
        "s06_min_window": """
def rolling_max(xs, k):
    if k <= 0:
        return []
    return [min(xs[i:i+k]) for i in range(len(xs)-k+1)]
""",
        "s07_reverse_correct": """
def rolling_max(xs, k):
    if k <= 0 or len(xs) < k:
        return []
    out = []
    for start in range(len(xs)-k, -1, -1):
        out.insert(0, max(xs[start:start+k]))
    return out
""",
        "s08_global_max": """
def rolling_max(xs, k):
    if k <= 0 or len(xs) < k:
        return []
    return [max(xs[i:i+k]) for i in range(len(xs) - k + 1)]
""",
        "s09_pairs_only": """
def rolling_max(xs, k):
    if k <= 0:
        return []
    return [max(xs[i:i+k]) for i in range(len(xs)-k+1)]
""",
        "s10_loop_correct": """
def rolling_max(xs, k):
    if k <= 0:
        return []
    out = []
    for i in range(0, len(xs) - k + 1):
        out.append(max(xs[i:i+k]))
    return out
""",
        "s11_while_correct": """
def rolling_max(xs, k):
    if k <= 0:
        return []
    out = []
    i = 0
    while i + k <= len(xs):
        out.append(max(xs[i:i+k]))
        i += 1
    return out
""",
        "s12_nested_correct": """
def rolling_max(xs, k):
    if k <= 0 or len(xs) < k:
        return []
    out = []
    for i in range(len(xs) - k + 1):
        best = xs[i]
        for value in xs[i:i+k]:
            if value > best:
                best = value
        out.append(best)
    return out
""",
        "s13_map_correct": """
def rolling_max(xs, k):
    if k <= 0:
        return []
    windows = (xs[i:i+k] for i in range(len(xs)-k+1))
    return list(map(max, windows))
""",
        "s14_local_helper_correct": """
def rolling_max(xs, k):
    def window(i):
        return xs[i:i+k]
    if k <= 0:
        return []
    return [max(window(i)) for i in range(len(xs)-k+1)]
""",
        "s15_prealloc_correct": """
def rolling_max(xs, k):
    if k <= 0 or k > len(xs):
        return []
    out = [0] * (len(xs) - k + 1)
    for i in range(len(out)):
        out[i] = max(xs[i:i+k])
    return out
""",
        "s16_copy_correct": """
def rolling_max(xs, k):
    values = list(xs)
    if k <= 0:
        return []
    return [max(values[i:i+k]) for i in range(len(values)-k+1)]
""",
        "s17_enumerate_correct": """
def rolling_max(xs, k):
    if k <= 0:
        return []
    out = []
    for i, _ in enumerate(xs):
        if i + k <= len(xs):
            out.append(max(xs[i:i+k]))
    return out
""",
        "s18_short_correct": """
def rolling_max(xs, k):
    return [] if k <= 0 else [max(xs[i:i+k]) for i in range(len(xs)-k+1)]
""",
        "s19_guarded_correct": """
def rolling_max(xs, k):
    if not xs or k <= 0 or k > len(xs):
        return []
    return [max(xs[start:start+k]) for start in range(len(xs)-k+1)]
""",
    }
    return [
        ProgramSample(sample_id=sample_id, source=source.strip() + "\n")
        for sample_id, source in sources.items()
    ]
