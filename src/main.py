from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from .filters import classify
from .models import Company, Tier
from .sources.base import Source
from .sources.finland_prh import FinlandSource
from .sources.norway_brreg import NorwaySource
from .sources.sweden_allabolag import SwedenSource
from .writers import write_csv

COUNTRIES = ["DK", "SE", "NO", "FI"]
ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "segments.yaml"


def load_config() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_source(country: str) -> Source:
    if country == "NO":
        return NorwaySource()
    if country == "FI":
        return FinlandSource()
    if country == "SE":
        return SwedenSource()
    if country == "DK":
        # Imported lazily so missing CVR creds don't block other countries.
        from .sources.denmark_cvr import DenmarkSource
        return DenmarkSource()
    raise ValueError(f"Unknown country: {country}")


def run_one(country: str, segment: str, seg_cfg: dict, out_dir: Path) -> None:
    log = logging.getLogger("main")
    log.info("=== %s / %s ===", country, segment)
    try:
        source = build_source(country)
    except RuntimeError as e:
        log.error("Skipping %s: %s", country, e)
        return

    nace_codes = list(seg_cfg.get("primary_nace", []) or []) + list(
        seg_cfg.get("secondary_nace", []) or []
    )
    tier1: list[Company] = []
    tier2: list[Company] = []
    total = 0
    for company in source.fetch(nace_codes):
        total += 1
        tier = classify(company, seg_cfg, country)
        if tier is Tier.ONE:
            tier1.append(company)
            tier2.append(company)
        elif tier is Tier.TWO:
            tier2.append(company)

    write_csv(out_dir / f"{country}_{segment}_tier1.csv", tier1)
    write_csv(out_dir / f"{country}_{segment}_tier2.csv", tier2)
    log.info("%s/%s fetched=%d tier1=%d tier2=%d", country, segment, total, len(tier1), len(tier2))


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Nordic business register scraper")
    parser.add_argument("--country", choices=COUNTRIES, help="Only this country (default: all)")
    parser.add_argument("--segment", help="Only this segment (default: all)")
    parser.add_argument("--out", default=str(ROOT / "output"), help="Output directory")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    cfg = load_config()
    segments = cfg.get("segments", {}) or {}
    if args.segment and args.segment not in segments:
        parser.error(f"Unknown segment: {args.segment}. Available: {sorted(segments)}")

    countries = [args.country] if args.country else COUNTRIES
    segment_names = [args.segment] if args.segment else list(segments.keys())
    out_dir = Path(args.out)

    for country in countries:
        for segment in segment_names:
            run_one(country, segment, segments[segment], out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
