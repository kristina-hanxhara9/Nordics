from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Tier(Enum):
    ONE = 1
    TWO = 2


@dataclass
class Company:
    country: str
    reg_no: str
    name: str
    nace_primary: str | None = None
    nace_secondary: list[str] = field(default_factory=list)
    address: str | None = None
    postcode: str | None = None
    city: str | None = None
    website: str | None = None
    status: str | None = None
    source_url: str | None = None

    def all_nace(self) -> list[str]:
        codes = []
        if self.nace_primary:
            codes.append(self.nace_primary)
        codes.extend(self.nace_secondary)
        return codes
