# Data licenses & provenance

ACDE is a research replication. It ships **no third-party data** in the repository; datasets are
generated or fetched on demand by `make seed`. This file records the provenance and licensing of the
two data sources the pipelines use. (Code-level design rationales live in `DEVIATIONS.md`.)

## TPC-DS (batch source)

- **What we use.** A **synthetic, downscaled, schema-faithful** `store_sales` fact + `item` dimension
  produced by a seeded NumPy generator (`src/acde/dataplane/datasets/tpcds_gen.py`). Same seed ⇒
  byte-identical CSVs.
- **Not `dsdgen`.** We do **not** ship or run the official TPC `dsdgen` toolkit, and we do **not**
  distribute any TPC-provided data (see `DEVIATIONS.md` D-009).
- **Trademark.** "TPC" and "TPC-DS" are trademarks of the
  [Transaction Processing Performance Council](https://www.tpc.org/). ACDE is not affiliated with or
  endorsed by the TPC; the name is used only to describe the schema our generator imitates. The
  official specification and its licensing terms are published by the TPC.

## NYC TLC trip data (streaming replay source, optional)

- **What we use.** By default the streaming source is the **seeded synthetic bursty producer**
  (offline, deterministic). A real NYC Taxi & Limousine Commission Yellow-Taxi month can optionally be
  downloaded for replay via `USE_REAL_TLC=1` (`src/acde/dataplane/datasets/nyc_tlc_fetch.py`), which
  fetches Parquet from the official TLC CloudFront host (see `DEVIATIONS.md` D-012).
- **Source & terms.** The data is the NYC TLC
  [Trip Record Data](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page), published by the
  City of New York. It is used here under the TLC's published terms of use; ACDE redistributes none of
  it — each user fetches it directly from the official host.

## Code

No open-source `LICENSE` is provided for the ACDE source at this time (all rights reserved by the
repository owner). See `DEVIATIONS.md` D-054.
