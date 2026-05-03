from __future__ import annotations

from dpa.invariants import Invariant
from dpa.task.smoke import ProgramSample


def filter_samples(
    samples: list[ProgramSample],
    inferred: dict[str, set[Invariant]],
    posterior: dict[Invariant, float],
    threshold: float,
) -> list[ProgramSample]:
    required = {
        invariant
        for invariant, survival in posterior.items()
        if survival >= threshold
    }
    survivors = [
        sample
        for sample in samples
        if required.issubset(inferred.get(sample.sample_id, set()))
    ]
    return survivors or samples
