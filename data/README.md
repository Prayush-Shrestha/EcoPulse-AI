# Data

This directory holds local datasets and derived files. No dataset files are
committed to Git, and Phase 1 ships the folders only.

## Directory contract

| Directory | Purpose | Committed |
| --- | --- | --- |
| `raw/` | Immutable downloads from the original source | No |
| `processed/` | Reproducible outputs derived from raw data | No |
| `external/` | Third-party reference data (for example holiday calendars) | No |

## Rules

1. Keep raw files exactly as downloaded. Never hand-edit them.
2. Every processed file must be reproducible from a documented pipeline step.
3. Each ingested source needs a manifest entry with URL, retrieval date,
   licence/attribution, and checksum.
4. Do not commit datasets, database dumps, or generated plots.
5. Do not introduce synthetic "production" data to make a chart look complete.

## Candidate sources

Dataset selection is part of Phase 2. The shortlist is documented on the
product page and in [the architecture notes](../docs/architecture.md):

- [UCI: Individual household electric power consumption](https://archive.ics.uci.edu/dataset/235/individual+household+electric+power+consumption)
- [ENTSO-E Transparency Platform](https://transparency.entsoe.eu/)
- [U.S. EIA Open Data](https://www.eia.gov/opendata/)

Phase 2 will add download tooling and the manifest format. Until then this
directory remains intentionally empty.
