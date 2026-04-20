from __future__ import annotations

from .models import Company, Tier


def _name_matches(name: str, keywords: list[str]) -> bool:
    haystack = name.lower()
    return any(kw.lower() in haystack for kw in keywords)


def _nace_matches(company_codes: list[str], target_codes: list[str]) -> bool:
    target = set(target_codes)
    return any(code in target for code in company_codes)


def classify(company: Company, segment_cfg: dict, country: str) -> Tier | None:
    """Classify a company into Tier 1, Tier 2, or None for the given segment.

    Tier 1: primary NACE in segment.primary_nace AND name matches a keyword.
    Tier 2: any NACE in primary∪secondary OR name matches a keyword.
    Tier 1 rows are also Tier 2 rows (callers write both files).
    """
    primary = segment_cfg.get("primary_nace", []) or []
    secondary = segment_cfg.get("secondary_nace", []) or []
    keywords = (segment_cfg.get("keywords", {}) or {}).get(country, []) or []

    primary_hit = company.nace_primary in set(primary) if company.nace_primary else False
    any_nace_hit = _nace_matches(company.all_nace(), primary + secondary)
    kw_hit = _name_matches(company.name, keywords) if keywords else False

    if primary_hit and kw_hit:
        return Tier.ONE
    if any_nace_hit or kw_hit:
        return Tier.TWO
    return None
