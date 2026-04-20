"""Norway: Brønnøysundregistrene open API (no auth)."""
from __future__ import annotations

import logging
from typing import Iterable

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from ..models import Company
from .base import Source

log = logging.getLogger(__name__)

API = "https://data.brreg.no/enhetsregisteret/api/enheter"
PAGE_SIZE = 1000
HEADERS = {"Accept": "application/json"}


class NorwaySource(Source):
    country = "NO"

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
        # brreg supports naeringskode filter which matches primary or secondary.
        for code in nace_codes:
            page = 0
            while True:
                params = {"naeringskode": code, "size": PAGE_SIZE, "page": page}
                data = self._get(params)
                embedded = data.get("_embedded", {}).get("enheter", [])
                if not embedded:
                    break
                for item in embedded:
                    reg_no = str(item.get("organisasjonsnummer", ""))
                    if not reg_no or reg_no in seen:
                        continue
                    seen.add(reg_no)
                    yield self._to_company(item)
                total_pages = data.get("page", {}).get("totalPages", 0)
                page += 1
                if page >= total_pages:
                    break
                log.debug("NO %s page=%d", code, page)

    @staticmethod
    def _to_company(item: dict) -> Company:
        reg_no = str(item.get("organisasjonsnummer", ""))
        addr = item.get("forretningsadresse") or {}
        primary = (item.get("naeringskode1") or {}).get("kode")
        secondary: list[str] = []
        for key in ("naeringskode2", "naeringskode3"):
            code = (item.get(key) or {}).get("kode")
            if code:
                secondary.append(code)
        return Company(
            country="NO",
            reg_no=reg_no,
            name=item.get("navn", ""),
            nace_primary=primary,
            nace_secondary=secondary,
            address=", ".join(addr.get("adresse", []) or []) or None,
            postcode=addr.get("postnummer"),
            city=addr.get("poststed"),
            website=item.get("hjemmeside"),
            status="dissolved" if item.get("slettedato") else "active",
            source_url=f"https://virksomhet.brreg.no/nb/oppslag/enheter/{reg_no}",
        )
