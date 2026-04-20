"""Denmark: CVR distribution API (Erhvervsstyrelsen, Elasticsearch).

Requires one-time email registration with Erhvervsstyrelsen to get basic-auth
credentials. Set CVR_USER and CVR_PASS in the environment (.env).
See https://datacvr.virk.dk for registration.
"""
from __future__ import annotations

import logging
import os
from typing import Iterable

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from ..models import Company
from .base import Source

log = logging.getLogger(__name__)

BASE = "http://distribution.virk.dk/cvr-permanent/virksomhed/_search"
SCROLL_BASE = "http://distribution.virk.dk/_search/scroll"
PAGE_SIZE = 1000
SCROLL_TTL = "2m"


def _to_cvr_code(dotted: str) -> str:
    """'47.41' -> '474100' (6-digit)."""
    raw = dotted.replace(".", "")
    return raw.ljust(6, "0")[:6]


class DenmarkSource(Source):
    country = "DK"

    def __init__(self, session: requests.Session | None = None) -> None:
        user = os.environ.get("CVR_USER")
        pw = os.environ.get("CVR_PASS")
        if not user or not pw:
            raise RuntimeError(
                "CVR_USER and CVR_PASS must be set (see README for registration)."
            )
        self.session = session or requests.Session()
        self.session.auth = (user, pw)
        self.session.headers.update({"Content-Type": "application/json", "Accept": "application/json"})

    @retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=2, min=2, max=16))
    def _post(self, url: str, payload: dict, params: dict | None = None) -> dict:
        r = self.session.post(url, json=payload, params=params, timeout=60)
        r.raise_for_status()
        return r.json()

    def fetch(self, nace_codes: list[str]) -> Iterable[Company]:
        cvr_codes = [_to_cvr_code(c) for c in nace_codes]
        query = {
            "size": PAGE_SIZE,
            "_source": [
                "Vrvirksomhed.cvrNummer",
                "Vrvirksomhed.virksomhedMetadata",
                "Vrvirksomhed.virksomhedsstatus",
            ],
            "query": {
                "bool": {
                    "should": [
                        {"terms": {
                            "Vrvirksomhed.virksomhedMetadata.nyesteHovedbranche.branchekode": cvr_codes
                        }},
                        {"terms": {
                            "Vrvirksomhed.virksomhedMetadata.nyesteBibranche1.branchekode": cvr_codes
                        }},
                        {"terms": {
                            "Vrvirksomhed.virksomhedMetadata.nyesteBibranche2.branchekode": cvr_codes
                        }},
                        {"terms": {
                            "Vrvirksomhed.virksomhedMetadata.nyesteBibranche3.branchekode": cvr_codes
                        }},
                    ],
                    "minimum_should_match": 1,
                }
            },
        }
        data = self._post(BASE, query, params={"scroll": SCROLL_TTL})
        scroll_id = data.get("_scroll_id")
        seen: set[str] = set()
        while True:
            hits = data.get("hits", {}).get("hits", []) or []
            if not hits:
                break
            for hit in hits:
                src = (hit.get("_source") or {}).get("Vrvirksomhed") or {}
                reg_no = str(src.get("cvrNummer", ""))
                if not reg_no or reg_no in seen:
                    continue
                seen.add(reg_no)
                yield self._to_company(src)
            if not scroll_id:
                break
            data = self._post(
                SCROLL_BASE,
                {"scroll": SCROLL_TTL, "scroll_id": scroll_id},
            )
            scroll_id = data.get("_scroll_id", scroll_id)

    @staticmethod
    def _dot(code6: str | None) -> str | None:
        if not code6 or len(code6) < 4:
            return None
        return f"{code6[:2]}.{code6[2:4]}"

    @classmethod
    def _to_company(cls, src: dict) -> Company:
        meta = src.get("virksomhedMetadata") or {}
        main = meta.get("nyesteHovedbranche") or {}
        primary = cls._dot(str(main.get("branchekode", "")))
        secondary: list[str] = []
        for key in ("nyesteBibranche1", "nyesteBibranche2", "nyesteBibranche3"):
            code = str((meta.get(key) or {}).get("branchekode", ""))
            dotted = cls._dot(code)
            if dotted:
                secondary.append(dotted)
        name = (meta.get("nyesteNavn") or {}).get("navn") or ""
        beliggenhed = meta.get("nyesteBeliggenhedsadresse") or {}
        street = beliggenhed.get("vejnavn")
        house_no = beliggenhed.get("husnummerFra")
        addr = " ".join(str(x) for x in [street, house_no] if x) or None
        postcode = beliggenhed.get("postnummer")
        city = beliggenhed.get("postdistrikt")
        reg_no = str(src.get("cvrNummer", ""))
        status_list = src.get("virksomhedsstatus") or []
        status = None
        if status_list:
            status = (status_list[-1] or {}).get("status")
        return Company(
            country="DK",
            reg_no=reg_no,
            name=name,
            nace_primary=primary,
            nace_secondary=secondary,
            address=addr,
            postcode=str(postcode) if postcode else None,
            city=city,
            website=None,
            status=status,
            source_url=f"https://datacvr.virk.dk/enhed/virksomhed/{reg_no}",
        )
