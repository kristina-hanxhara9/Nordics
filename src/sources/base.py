from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

from ..models import Company


class Source(ABC):
    country: str = ""

    @abstractmethod
    def fetch(self, nace_codes: list[str]) -> Iterable[Company]:
        """Yield Company records whose primary or secondary NACE overlaps nace_codes."""
        raise NotImplementedError
