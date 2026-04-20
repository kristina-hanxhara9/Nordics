from __future__ import annotations

import csv
from pathlib import Path

from .models import Company

CSV_COLUMNS = [
    "country",
    "reg_no",
    "name",
    "nace_primary",
    "nace_secondary",
    "address",
    "postcode",
    "city",
    "website",
    "status",
    "source_url",
]


def write_csv(path: Path, companies: list[Company]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_COLUMNS)
        for c in companies:
            writer.writerow([
                c.country,
                c.reg_no,
                c.name,
                c.nace_primary or "",
                ";".join(c.nace_secondary),
                c.address or "",
                c.postcode or "",
                c.city or "",
                c.website or "",
                c.status or "",
                c.source_url or "",
            ])
