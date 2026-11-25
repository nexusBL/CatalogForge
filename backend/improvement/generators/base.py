from __future__ import annotations

from typing import Protocol

from backend.improvement.contract import GeneratorCandidate, TrustedItemContext


class ImprovementGenerator(Protocol):
    def generate(self, context: TrustedItemContext, *, why: str) -> GeneratorCandidate:
        """Return a structured candidate. Must not mutate catalogue state."""
