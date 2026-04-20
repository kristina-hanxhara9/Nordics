# Nordic Business Register Scraper

Pulls company lists from the four Nordic national business registers and
emits filtered CSVs for four target market segments:

- IT mail orders
- Opticians
- Computer specialists
- Kitchen specialists

Iceland is out of scope.

## Sources

| Country | Register | API |
|---------|----------|-----|
| DK | CVR (Erhvervsstyrelsen) | `distribution.virk.dk` Elasticsearch (free; identify in User-Agent) |
| SE | allabolag.se | HTML scrape, 1 req/s |
| NO | Brønnøysundregistrene | `data.brreg.no` open JSON |
| FI | PRH Avoindata (YTJ) | `avoindata.prh.fi` open JSON |

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env: set CVR_APP_NAME and CVR_CONTACT_EMAIL (Denmark only)
```

Denmark's CVR distribution endpoint is free but Erhvervsstyrelsen asks
every client to identify itself in the `User-Agent` header. Register your
app name + contact email once by email to `datacvr@erst.dk` (no password
is issued), then put both values in `.env`. NO, FI, and SE need no
registration at all.

## Usage

```bash
# Everything (4 countries x 4 segments = 32 CSVs, ~30 min dominated by SE)
python -m src.main

# Single country
python -m src.main --country NO

# Single segment across all countries
python -m src.main --segment opticians

# One-off
python -m src.main --country FI --segment kitchen_specialists --out ./output
```

Each run writes two files per country+segment:

```
output/<country>_<segment>_tier1.csv   # high-confidence: primary NACE AND keyword match
output/<country>_<segment>_tier2.csv   # broader: any NACE match OR keyword match (superset of tier1)
```

## Tiering

- **Tier 1** — primary business code matches the segment's primary NACE **and** the registered name contains at least one segment keyword. Small, high-precision.
- **Tier 2** — either the primary or secondary business code overlaps the segment (primary ∪ secondary NACE set) **or** the name matches a keyword. Larger, for manual review.

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
