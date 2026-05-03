from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from dpa.invariants import Invariant


def survival_rates(
    invariant_sets: Iterable[set[Invariant]],
    denominator: int | None = None,
) -> dict[Invariant, float]:
    sets = list(invariant_sets)
    total = denominator if denominator is not None else len(sets)
    if total <= 0:
        return {}

    counts: Counter[Invariant] = Counter()
    for invariants in sets:
        counts.update(invariants)
    return {
        invariant: round(count / total, 6)
        for invariant, count in counts.items()
    }
