# Decision log

Every non-trivial design choice: what we considered, what we picked, and why. Newest at the bottom of each milestone. Status is **Accepted** unless marked **Open** (needs the owner's call).

---

## M1: Exploration, scope, schema (2026-10-20)

### D-001 Data slice: FSG 59 (electrical & electronic components), DoD-awarding, FY2019 to present
- **Options (measured live, FY19 to present, DoD):**

  | Slice | Awards | $ | PSCs |
  |---|---|---|---|
  | FSG 59 electronics | ~478k (DLA alone) | $24.7B | 26 |
  | FSG 13 ammunition | ~6.2k | $59.9B | 31 |
  | FSG 20 ship/marine | ~29k | $5.4B | 7 |

- **Picked:** FSG 59.
- **Why:** It has the most small suppliers, which is where fragility signals (lapsed SAM registration, exclusions) mean something. Microelectronics is a recognized chokepoint (CHIPS Act, DMSMS obsolescence). DLA descriptions give a sub-PSC item class (D-004). FSG 13 is dominated by a handful of primes and government-owned plants whose concentration is already well known. FSG 20 has only 7 PSCs, too few categories to rank.
- **Cost accepted:** higher volume (needs async file downloads, D-002) and distributor noise (D-005).

### D-002 Ingestion route: `download/transactions`, one file per fiscal year
- **Options:** (a) paginate `search/spending_by_award` at 100 rows/page, about 5k calls; (b) `bulk_download/awards`; (c) `download/transactions` (the Advanced Search download).
- **Picked:** (c).
- **Why:** (b)'s documented filters have **no PSC filter**, so it would pull every DoD contract. (a) hammers the API and returns award summaries, not transactions. (c) accepts the same filters as search, including `psc_codes`, and returns a zipped CSV asynchronously. It caps each file at about 500k rows, so we request **one file per fiscal year** (~65k rows each). Per-FY files also make caching natural: past FYs are cached permanently, and only the current FY is refreshed.
- **Source:** [download/transactions contract](https://github.com/fedspendingtransparency/usaspending-api/blob/master/usaspending_api/api_contracts/contracts/v2/download/transactions.md)

### D-003 Grain: ingest transactions, derive awards
- **Why:** HHI "over FY2019 to present" must count dollars obligated *in the window*. An award's current total includes years outside it. 23% of transactions are ≤ $0 (de-obligations), so every dollar figure is a **net sum of transactions**. Filtering out negatives would overstate exposure.

### D-004 Add ItemClass below PSC
- **Problem:** PSC-level concentration hides chokepoints. 5962 "Microcircuits" has many vendors in total even if particular item types have one.
- **Found:** 85% of DLA descriptions look like `8511444589!MICROCIRCUIT,HYBRID` (purchase-request number, `!`, DLA item name truncated at a fixed 19 characters).
- **Picked:** `ItemClass = (psc, item_name)`, with analytics at both levels.
- **Alternative rejected:** LLM classification of free text. It's unnecessary when 85% is structured, and it adds unmeasured error into the core metric. The remaining 15% stays "unclassified" rather than guessed.
- **Limitation:** an item name is not an NSN; many distinct parts share `CONNECTOR,PLUG,ELEC`.

### D-005 Vendor identity: UEI, with parent rollup for concentration (Open: review)
- **Why parent:** two subsidiaries of one parent are not independent sources. If the parent fails, both go. In the sample, 494 UEIs collapse to 467 parents.
- **Data quality issue found:** parent data is self-reported and sometimes wrong. In the sample, a RAYTHEON COMPANY UEI lists ROCKWELL COLLINS AUSTRALIA PTY LIMITED as its parent.
- **Picked:** compute concentration at **both** UEI and parent level, show the parent-level number by default, and surface a sensitivity flag when they disagree materially.

### D-006 Competition: map FPDS extent-competed codes into three buckets
- **Source:** [FPDS Extent Competed](https://fpds.gov/help/Extent_Competed.htm)
- **Competed:** A (full & open), D (full & open after exclusion of sources, e.g. set-asides), F (competed under simplified acquisition), CDO (competitive delivery order).
- **Not competed:** B (not available for competition), C (not competed), G (not competed under simplified acquisition), NDO (non-competitive delivery order).
- **Ambiguous:** E (follow-on to a competed action). Reported separately, never silently merged.
- **Note:** "without full and open competition" in the strict FAR sense means everything except A. We report the operationally meaningful "not competed" bucket and keep the strict version available.

### D-007 Add single-offer share as a risk signal
- **Found:** 28% of sample transactions received exactly one offer, though most are coded "competed."
- **Why it matters:** "competed, one bidder" means the market has no alternative in practice. This is often a better chokepoint signal than the competition code itself (single-bid competition is a recurring DoD IG finding).

### D-008 Which transaction defines an award's attributes
- PSC, description, office, and competition can change across modifications. **Picked:** the earliest in-window transaction (the base award when it is in the window). Award-level dollars are still the net of all in-window transactions.
- **Limitation:** an award whose PSC was later re-coded out of FSG 59 is only partly visible.

### D-009 NAICS as an attribute, not an object
- It's useful as a filter, but nothing operational hangs off a NAICS code in this app. Promote it only if an analysis needs it (no premature abstraction).

### D-010 SAM enrichment via extracts, not per-vendor lookups
- **Constraint:** a non-federal SAM key without a role is limited to **10 requests/day**, and `ueiSAM` accepts at most 100 values per request. Thousands of vendors would take days.
- **Picked:** the Entity API with `format=csv` (an asynchronous extract file) and the same for Exclusions. Fallback: batch 100 UEIs per call, prioritized by dollar exposure.
- **Sources:** [Entity API](https://open.gsa.gov/api/entity-api/), [Exclusions API](https://open.gsa.gov/api/exclusions-api/)

### D-011 Tooling: Python 3.12 via uv, DuckDB, `# %%` notebooks
- **3.12, not the local 3.14:** matches Streamlit Community Cloud and has stable wheels for DuckDB and pandas.
- **DuckDB over SQLite:** columnar storage, fast group-bys for HHI, reads CSV directly, and a single file for the deploy snapshot.
- **`# %%` scripts over .ipynb:** clean git diffs and no stale hidden outputs. VS Code still runs them cell by cell.

---

## M2: Ingestion (in progress)

### D-012 Window: FY2019–FY2026, complete fiscal years only; recent years refresh until settled
- **Why complete years:** year-over-year comparisons are only fair between full years. FY2027 began 2026-10-01 and is excluded.
- **Why "settling":** DoD contract data appears in FPDS with a **90-day delay** ([FPDS](https://www.fpds.gov/common/html/dodDataAvailability.html)), so FY2026 is still filling in. A fiscal year counts as *final* 120 days after it ends (90 days plus margin). Until then its cache is refreshed when it is more than 7 days old. A file cached while settling is re-fetched once after the year becomes final, then never again.

### D-013 Request 33 of 297 columns
- **Verified** that `download/transactions` accepts the CSV column names in `columns` (live test, 2026-10-22). This cuts file size by roughly 10x. The list lives in `config.TRANSACTION_COLUMNS`; adding a column means re-downloading with `--force`.

### D-014 Cache design: zip plus manifest, atomic writes, injectable clock
- **Manifest** (`fy{N}.manifest.json`): the exact request, row count, download date, and sha256. Any number in the app can be traced to the file and request it came from.
- **Atomic write:** download to `.part`, then rename, so a crash never leaves a half-file that looks cached.
- **Injectable `today`, `sleep` and HTTP client:** the cache rules and the polling loop are tested against a fake USAspending with no network access, so CI is deterministic and fast.
- **Tolerant polling:** the live status endpoint once returned a body without `status`. That is treated as "still running," not a crash, with a hard timeout.
