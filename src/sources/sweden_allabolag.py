"""Sweden: allabolag.se scraper (no official free bulk API).

Polite scrape: 1 req/s, custom User-Agent, respects robots.txt (allabolag.se
permits /lista/). Page structure can change; selectors may need updating.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Iterable

import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

from ..models import Company
from .base import Source

log = logging.getLogger(__name__)

BASE = "https://www.allabolag.se"
LIST_PATH = "/lista/_/_/sni-{code}"
USER_AGENT = (
    "NordicMarketResearchBot/0.1 (contact: research@example.com; "
    "purpose: one-shot market-segment list build)"
)
REQUEST_DELAY_S = 1.0


def _to_sni_code(dotted: str) -> str:
    """'47.41' -> '4741'."""
    return dotted.replace(".", "")


class SwedenSource(Source):
    country = "SE"

    def __init__(self, session: requests.Session | None = None) -> None:
        self.session = session or requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8",
        })
        self._last_request = 0.0

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < REQUEST_DELAY_S:
            time.sleep(REQUEST_DELAY_S - elapsed)
        self._last_request = time.monotonic()

    @retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=2, min=2, max=16))
    def _get(self, url: str) -> str:
        self._throttle()
        r = self.session.get(url, timeout=30)
        r.raise_for_status()
        return r.text

    def fetch(self, nace_codes: list[str]) -> Iterable[Company]:
        seen: set[str] = set()
        for code in nace_codes:
            sni = _to_sni_code(code)
            page = 1
            while True:
                url = f"{BASE}{LIST_PATH.format(code=sni)}?page={page}"
                try:
                    html = self._get(url)
                except requests.HTTPError as e:
                    log.warning("SE %s page=%d HTTP %s", sni, page, e)
                    break
                rows = list(self._parse_list(html, queried_nace=code))
                if not rows:
                    break
                for c in rows:
                    if c.reg_no in seen:
                        continue
                    seen.add(c.reg_no)
                    yield c
                page += 1

    @staticmethod
    def _parse_list(html: str, queried_nace: str) -> Iterable[Company]:
        soup = BeautifulSoup(html, "lxml")
        # Layout: each company is in <article> or a result row with a company
        # link like /foretag/<slug>/<orgnr>. Be defensive — site HTML changes.
        for link in soup.select("a[href*='/foretag/']"):
            href = link.get("href", "")
            m = re.search(r"/foretag/[^/]+/(\d{10})", href)
            if not m:
                continue
            reg_no = m.group(1)
            name = link.get_text(strip=True)
            if not name:
                continue
            row = link.find_parent(["article", "li", "div"])
            city = None
            if row:
                city_el = row.find(attrs={"class": re.compile(r"(city|ort|location)", re.I)})
                if city_el:
                    city = city_el.get_text(strip=True) or None
            yield Company(
                country="SE",
                reg_no=reg_no,
                name=name,
                nace_primary=queried_nace,
                nace_secondary=[],
                city=city,
                source_url=f"{BASE}{href}" if href.startswith("/") else href,
                status="active",
            )
