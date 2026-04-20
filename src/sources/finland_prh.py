"""Finland: PRH Avoindata (YTJ) open API (no auth)."""
from __future__ import annotations

import logging
from typing import Iterable

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from ..models import Company
from .base import Source

log = logging.getLogger(__name__)

API = "https://avoindata.prh.fi/bis/v1"
PAGE_SIZE = 1000
HEADERS = {"Accept": "application/json"}


def _to_prh_code(dotted: str) -> str:
    """'47.41' -> '47410' (5-digit, no dot)."""
    raw = dotted.replace(".", "")
    return raw.ljust(5, "0")[:5]


class FinlandSource(Source):
    country = "FI"

    def __init__(self, session: requests.Session | None = None) -> None:
        self.session = session or requests.Session()
        self.session.headers.update(HEADERS)

    @retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=2, min=2, max=16))
    def _get(self, params: dict) -> dict:
        r = self.session.get(API, params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    def fetch(self, nace_codes: list[str]) -> Iterable[Company]:
        seen: set[str] = set()
        for code in nace_codes:
            prh_code = _to_prh_code(code)
            results_from = 0
            while True:
                params = {
                    "businessLine": prh_code,
                    "maxResults": PAGE_SIZE,
                    "resultsFrom": results_from,
                }
                data = self._get(params)
                results = data.get("results", []) or []
                if not results:
                    break
                for item in results:
                    reg_no = str(item.get("businessId", ""))
                    if not reg_no or reg_no in seen:
                        continue
                    seen.add(reg_no)
                    yield self._to_company(item, prh_code)
                if len(results) < PAGE_SIZE:
                    break
                results_from += PAGE_SIZE
                log.debug("FI %s from=%d", prh_code, results_from)

    @staticmethod
    def _to_company(item: dict, queried_code: str) -> Company:
        reg_no = str(item.get("businessId", ""))
        name = item.get("name", "")
        lines = item.get("businessLines", []) or []
        primary = None
        secondary: list[str] = []
        for bl in lines:
            code5 = str(bl.get("code", ""))
            if not code5 or len(code5) < 4:
                continue
            dotted = f"{code5[:2]}.{code5[2:4]}"
            if bl.get("endDate"):
                continue
            if primary is None:
                primary = dotted
            else:
                secondary.append(dotted)
        addresses = item.get("addresses", []) or []
        visiting = next(
            (a for a in addresses if not a.get("endDate") and a.get("type") == 1),
            addresses[0] if addresses else None,
        )
        addr = visiting.get("street") if visiting else None
        postcode = visiting.get("postCode") if visiting else None
        city = visiting.get("city") if visiting else None
        return Company(
            country="FI",
            reg_no=reg_no,
            name=name,
            nace_primary=primary,
            nace_secondary=secondary,
            address=addr,
            postcode=postcode,
            city=city,
            website=None,
            status="dissolved" if item.get("endDate") else "active",
            source_url=f"https://tietopalvelu.ytj.fi/yritystiedot.aspx?yavain=&ytunnus={reg_no}",
        )
