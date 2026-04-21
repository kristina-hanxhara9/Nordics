# Nordic Business Register Scraper

Pulls company lists from the four Nordic national business registers and
emits filtered CSVs for four target market segments:

- IT mail orders
- Opticians
- Computer specialists
- Kitchen specialists

Iceland is out of scope.

## Sources

| Country | Register | Access |
|---------|----------|--------|
| DK | CVR (Erhvervsstyrelsen) | `distribution.virk.dk` Elasticsearch — **requires email approval**; free, identify in User-Agent |
| SE | Bolagsverket + SCB bulk files | Local `.txt` download (free, no account) |
| NO | Brønnøysundregistrene | `data.brreg.no` open JSON (no auth) |
| FI | PRH Avoindata (YTJ) | `avoindata.prh.fi` open JSON (no auth) |

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env: set CVR_APP_NAME and CVR_CONTACT_EMAIL (Denmark only)
```

### Denmark — one-time email approval

Erhvervsstyrelsen requires a short email to `datacvr@erst.dk` before
granting access to the distribution endpoint. Template:

> Subject: Anmodning om adgang til CVR's systemgrænseflade
>
> Hej,
>
> Jeg ønsker adgang til distribution.virk.dk til et internt markedsanalyseprojekt.
> App-navn: NordicMarketResearch. Kontakt: <din email>.
> Anvendelse: engangsudtræk af virksomheder under udvalgte branchekoder — ingen videredistribution.
>
> Mvh, <dit navn>

Turnaround is usually 1–2 days. Once approved, fill `CVR_APP_NAME` and
`CVR_CONTACT_EMAIL` in `.env`. No password is issued — every request
identifies you in the `User-Agent` header.

### Sweden — bulk files (free, no account)

Download both once from
<https://bolagsverket.se/apierochoppnadata/nedladdningsbarafiler.2517.html>:

- `scb_bulkfil.zip` — SNI codes + address (primary source for industry filter)
- `bolagsverket_bulkfil.zip` — legal form + `verksamhetsbeskrivning` (description)

Unzip both and drop the resulting `.txt` files into `./data/`:

```
data/scb_bulkfil.txt
data/bolagsverket_bulkfil.txt
```

Files refresh weekly; re-download when you need fresh data. The scraper
scans the SCB file for SNI-code matches, then enriches each match from
Bolagsverket by org number.

### Norway, Finland

No setup — both registers are fully open.

## Usage

```bash
# Everything (4 countries × 4 segments = 32 CSVs)
python -m src.main

# Single country
python -m src.main --country NO

# Single segment across all countries
python -m src.main --segment opticians

# One country + one segment, custom output directory
python -m src.main --country FI --segment kitchen_specialists --out ./output

# Override Swedish file locations
python -m src.main --country SE --sweden-files /path/to/scb.txt /path/to/bolagsverket.txt
```

Each run writes two files per country+segment:

```
output/<country>_<segment>_tier1.csv   # primary NACE AND keyword match
output/<country>_<segment>_tier2.csv   # any NACE overlap OR keyword match (superset of tier1)
```

## Tiering

- **Tier 1** — primary business code matches the segment's `primary_nace` **and** the registered name contains at least one segment keyword. Small, high-precision.
- **Tier 2** — the primary or secondary business code overlaps the segment's NACE set **or** the name matches a keyword. Larger, for manual review.

Tier 1 rows are always included in Tier 2.

## Configuration

All NACE codes and keyword lists live in
[`config/segments.yaml`](config/segments.yaml). Edit that file to tune
the filters — no code change needed.

## Out of scope

- Iceland (no free bulk register API).
- Turnover / B2B vs B2C distinction — not in any of these registers.
- Cross-border deduplication.
- Scheduled re-runs.
