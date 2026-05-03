from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class Invariant:
    kind: str
    content: str

    def canonical(self) -> str:
        return f"{self.kind}:{' '.join(self.content.split())}"

    def __str__(self) -> str:
        return self.canonical()
