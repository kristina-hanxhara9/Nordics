"""Sweden: read Bolagsverket + SCB bulk txt files (free, no auth).

Files to download (once, free, weekly refresh):
  https://bolagsverket.se/apierochoppnadata/nedladdningsbarafiler.2517.html
    - scb_bulkfil.zip         (SNI codes, address — primary source for NACE)
    - bolagsverket_bulkfil.zip (legal form, verksamhetsbeskrivning)

Unzip each into ./data/ (or anywhere — pass --sweden-files). Forward
discovery: fast raw-text scan for the 5-digit SNI codes we want, then
parse only matching lines with pandas, optionally merge by org number.
"""
from __future__ import annotations

import io
import logging
import re
from pathlib import Path
from typing import Iterable

import pandas as pd

from ..models import Company
from .base import Source

log = logging.getLogger(__name__)


# Column name → canonical field. Covers both bulk formats.
_COL_MAP: dict[str, str] = {
    # name
    "namn": "name",
    "organisationsnamn": "name",
    "företagsnamn": "name",
    "foretagsnamn": "name",
    # org number
    "peorgnr": "org_number",
    "organisationsidentitet": "org_number",
    "organisationsnummer": "org_number",
    "orgnr": "org_number",
    "org_nr": "org_number",
    # legal form
    "juridiskform": "legal_form",
    "organisationsform": "legal_form",
    "bolagsform": "legal_form",
    # primary SNI
    "ng1": "ng1",
    "sni": "ng1",
    "sni_kod": "ng1",
    "branschkod": "ng1",
    # secondary SNIs
    "ng2": "ng2",
    "ng3": "ng3",
    "ng4": "ng4",
    "ng5": "ng5",
    # industry description
    "verksamhetsbeskrivning": "industry_desc",
    "bransch": "industry_desc",
    # address
    "gatuadress": "address",
    "utdelningsadress": "address",
    "postadress": "address",
    "adress": "address",
    # postcode + city
    "postnr": "postcode",
    "postnummer": "postcode",
    "postort": "city",
    "ort": "city",
    # status / dates
    "status": "status",
    "avregistreringsdatum": "deregistration_date",
    "registreringsdatum": "registration_date",
}

SNI_COLS = ["ng1", "ng2", "ng3", "ng4", "ng5"]


def _strip_bom(s: str) -> str:
    return s.lstrip("﻿￾\xef\xbb\xbf").replace("​", "").strip()


def _to_sni_code(dotted: str) -> str:
    """'47.78' -> '47780' (5-digit, no dot)."""
    raw = dotted.replace(".", "")
    return raw.ljust(5, "0")[:5]


def _from_sni_code(sni: str) -> str | None:
    """'47780' -> '47.78'. None if not 4-5 digit numeric."""
    if not sni:
        return None
    s = str(sni).strip()
    if not s.isdigit() or len(s) < 4:
        return None
    s = s.zfill(5)
    return f"{s[:2]}.{s[2:4]}"


def _detect_format(path: Path) -> tuple[str, str]:
    """Return (separator, encoding). Sniff by trying combinations."""
    if path.suffix.lower() in (".xlsx", ".xls"):
        return ("excel", "")
    for enc in ["utf-8-sig", "utf-8", "latin-1", "cp1252"]:
        for sep in [";", "\t", ",", "|"]:
            try:
                df = pd.read_csv(path, sep=sep, dtype=str, encoding=enc,
                                 on_bad_lines="skip", nrows=5)
                if len(df.columns) > 1:
                    return (sep, enc)
            except Exception:
                continue
    return (",", "latin-1")


def _map_columns(columns: list[str]) -> dict[str, str]:
    """canonical → actual column name. Exact match first, then substring."""
    mapping: dict[str, str] = {}
    for col in columns:
        key = _strip_bom(col).lower().replace(" ", "_")
        if key in _COL_MAP:
            canonical = _COL_MAP[key]
            mapping.setdefault(canonical, col)
    for col in columns:
        key = _strip_bom(col).lower().replace(" ", "_")
        for map_key, canonical in _COL_MAP.items():
            if map_key in key:
                mapping.setdefault(canonical, col)
    return mapping


def _sniff_header(path: Path) -> tuple[str, str, list[str]]:
    """Return (separator, encoding, header_columns) by reading only row 0."""
    sep, enc = _detect_format(path)
    if sep == "excel":
        df = pd.read_excel(path, dtype=str, nrows=0)
        return ("excel", "", [_strip_bom(c) for c in df.columns])
    df = pd.read_csv(path, sep=sep, dtype=str, encoding=enc, nrows=0)
    return (sep, enc, [_strip_bom(c) for c in df.columns])


def _has_sni_column(path: Path) -> bool:
    _, _, cols = _sniff_header(path)
    cmap = _map_columns(cols)
    return any(k in cmap for k in SNI_COLS)


def _parse_matching_lines(path: Path, sep: str, enc: str,
                          header_line: str, matching: list[str]) -> pd.DataFrame:
    if not matching:
        return pd.DataFrame()
    df = pd.read_csv(io.StringIO(header_line + "".join(matching)),
                     sep=sep, dtype=str, on_bad_lines="skip")
    df.columns = [_strip_bom(c) for c in df.columns]
    return df


def _load_by_sni(path: Path, sni_codes: list[str]) -> pd.DataFrame:
    """Scan path for lines containing any SNI code, post-filter by column."""
    sep, enc = _detect_format(path)
    if sep == "excel":
        df = pd.read_excel(path, dtype=str)
        df.columns = [_strip_bom(c) for c in df.columns]
        return _post_filter(df, sni_codes)

    log.info("  %s: sep=%r encoding=%s", path.name, sep, enc)
    header_line: str | None = None
    matching: list[str] = []
    total = 0
    with open(path, encoding=enc, errors="replace") as fh:
        for i, line in enumerate(fh):
            total = i
            if i == 0:
                header_line = line
                continue
            if any(code in line for code in sni_codes):
                matching.append(line)
    log.info("  %s: scanned %d lines, %d SNI candidates", path.name, total, len(matching))
    if not header_line:
        return pd.DataFrame()
    df = _parse_matching_lines(path, sep, enc, header_line, matching)
    return _post_filter(df, sni_codes) if not df.empty else df


def _load_by_orgnr(path: Path, orgnrs: set[str]) -> pd.DataFrame:
    """Scan path for lines containing any of orgnrs (10-digit SE numbers)."""
    sep, enc = _detect_format(path)
    if sep == "excel":
        df = pd.read_excel(path, dtype=str)
        df.columns = [_strip_bom(c) for c in df.columns]
        col_map = _map_columns(list(df.columns))
        oc = col_map.get("org_number")
        if oc is None:
            return pd.DataFrame()
        keys = df[oc].astype(str).str.replace(r"\D", "", regex=True)
        return df[keys.isin(orgnrs)].reset_index(drop=True)

    log.info("  %s: sep=%r encoding=%s (enrich by %d org numbers)",
             path.name, sep, enc, len(orgnrs))
    header_line: str | None = None
    matching: list[str] = []
    total = 0
    with open(path, encoding=enc, errors="replace") as fh:
        for i, line in enumerate(fh):
            total = i
            if i == 0:
                header_line = line
                continue
            if any(o in line for o in orgnrs):
                matching.append(line)
    log.info("  %s: scanned %d lines, %d orgnr candidates", path.name, total, len(matching))
    if not header_line:
        return pd.DataFrame()
    df = _parse_matching_lines(path, sep, enc, header_line, matching)
    if df.empty:
        return df
    col_map = _map_columns(list(df.columns))
    oc = col_map.get("org_number")
    if oc is None:
        return pd.DataFrame()
    keys = df[oc].astype(str).str.replace(r"\D", "", regex=True)
    return df[keys.isin(orgnrs)].reset_index(drop=True)


def _post_filter(df: pd.DataFrame, sni_codes: list[str]) -> pd.DataFrame:
    """Drop rows where no SNI column actually contains a target code
    (text pre-scan can produce false positives on other numeric fields)."""
    if df.empty:
        return df
    col_map = _map_columns(list(df.columns))
    sni_cols = [col_map[c] for c in SNI_COLS if c in col_map]
    if not sni_cols:
        return df  # nothing to check against; trust the scan
    targets = set(sni_codes)
    mask = pd.Series(False, index=df.index)
    for c in sni_cols:
        col_vals = df[c].astype(str).str.strip().str.zfill(5)
        mask = mask | col_vals.isin(targets)
    return df[mask].reset_index(drop=True)


def _merge_by_orgnr(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Outer-merge frames on org number; prefer left values, fill from right."""
    def _orgnr_col(df: pd.DataFrame) -> str | None:
        return _map_columns(list(df.columns)).get("org_number")

    merged = frames[0].copy()
    left_col = _orgnr_col(merged)
    if left_col is None:
        return merged
    merged["_key"] = merged[left_col].astype(str).str.replace(r"\D", "", regex=True)

    for other in frames[1:]:
        right_col = _orgnr_col(other)
        if right_col is None:
            merged = pd.concat([merged, other], ignore_index=True, sort=False)
            continue
        other = other.copy()
        other["_key"] = other[right_col].astype(str).str.replace(r"\D", "", regex=True)
        combined = merged.merge(other, on="_key", how="outer", suffixes=("", "_r"))
        for col in list(combined.columns):
            if col.endswith("_r"):
                base = col[:-2]
                if base in combined.columns:
                    combined[base] = combined[base].fillna(combined[col])
                    combined.drop(columns=[col], inplace=True)
        merged = combined

    merged.drop(columns=["_key"], errors="ignore", inplace=True)
    return merged


class SwedenSource(Source):
    country = "SE"

    def __init__(self, files: list[Path]) -> None:
        self.files = [Path(p) for p in files]
        missing = [p for p in self.files if not p.exists()]
        if missing:
            raise FileNotFoundError(f"Swedish bulk file(s) not found: {missing}")

    def fetch(self, nace_codes: list[str]) -> Iterable[Company]:
        sni_codes = [_to_sni_code(c) for c in nace_codes]
        log.info("SE: loading %d file(s), SNI filter %s", len(self.files), sni_codes)

        sni_files = [p for p in self.files if _has_sni_column(p)]
        other_files = [p for p in self.files if p not in sni_files]
        if not sni_files:
            log.error("SE: no file has an SNI column (Ng1/sni_kod/branschkod). "
                      "Include scb_bulkfil.txt.")
            return

        primary_frames = [_load_by_sni(p, sni_codes) for p in sni_files]
        primary_frames = [df for df in primary_frames if not df.empty]
        if not primary_frames:
            log.warning("SE: no matching rows by SNI")
            return
        primary = primary_frames[0] if len(primary_frames) == 1 else _merge_by_orgnr(primary_frames)

        primary_map = _map_columns(list(primary.columns))
        oc = primary_map.get("org_number")
        if oc is None:
            log.warning("SE: primary frame has no org_number column; skipping enrichment")
            merged = primary
        else:
            orgnrs = set(
                primary[oc].astype(str).str.replace(r"\D", "", regex=True)
            )
            orgnrs.discard("")
            enrich_frames = [primary]
            for path in other_files:
                df = _load_by_orgnr(path, orgnrs)
                if not df.empty:
                    enrich_frames.append(df)
            merged = enrich_frames[0] if len(enrich_frames) == 1 else _merge_by_orgnr(enrich_frames)

        col_map = _map_columns(list(merged.columns))
        log.info("SE: merged %d rows, column map: %s", len(merged), col_map)

        seen: set[str] = set()
        for _, row in merged.iterrows():
            company = _to_company(row, col_map)
            if not company or not company.reg_no or company.reg_no in seen:
                continue
            seen.add(company.reg_no)
            yield company


def _g(row: pd.Series, col_map: dict[str, str], canonical: str) -> str | None:
    col = col_map.get(canonical)
    if col is None:
        return None
    val = row.get(col)
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip()
    return s or None


def _to_company(row: pd.Series, col_map: dict[str, str]) -> Company | None:
    reg_no = _g(row, col_map, "org_number") or ""
    reg_no_digits = re.sub(r"\D", "", reg_no)
    if not reg_no_digits:
        return None
    primary_sni = _g(row, col_map, "ng1")
    primary = _from_sni_code(primary_sni) if primary_sni else None
    secondary: list[str] = []
    for c in ("ng2", "ng3", "ng4", "ng5"):
        sni = _g(row, col_map, c)
        dotted = _from_sni_code(sni) if sni else None
        if dotted:
            secondary.append(dotted)
    status_raw = _g(row, col_map, "status")
    dereg = _g(row, col_map, "deregistration_date")
    if dereg:
        status = "dissolved"
    elif status_raw:
        status = status_raw
    else:
        status = "active"
    return Company(
        country="SE",
        reg_no=reg_no_digits,
        name=_g(row, col_map, "name") or "",
        nace_primary=primary,
        nace_secondary=secondary,
        address=_g(row, col_map, "address"),
        postcode=_g(row, col_map, "postcode"),
        city=_g(row, col_map, "city"),
        website=None,
        status=status,
        source_url=f"https://www.allabolag.se/{reg_no_digits}",
    )
