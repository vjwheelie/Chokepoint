# %% [markdown]
# # 01 — API exploration & scope decision
#
# Reproduces the M1 findings behind the scope and schema decisions (DECISIONS.md D-001..D-011).
# Run cell-by-cell in VS Code ("Run Cell") — this is a `# %%` script rather than an .ipynb so it
# diffs cleanly in git and can't hide stale outputs.
#
# Official API contracts used (verified 2026-10-20):
# - spending_by_award_count: https://github.com/fedspendingtransparency/usaspending-api/blob/master/usaspending_api/api_contracts/contracts/v2/search/spending_by_award_count.md
# - spending_by_category/psc: https://github.com/fedspendingtransparency/usaspending-api/blob/master/usaspending_api/api_contracts/contracts/v2/search/spending_by_category/psc.md
# - download/transactions: https://github.com/fedspendingtransparency/usaspending-api/blob/master/usaspending_api/api_contracts/contracts/v2/download/transactions.md
# - download/status: https://github.com/fedspendingtransparency/usaspending-api/blob/master/usaspending_api/api_contracts/contracts/v2/download/status.md
# - bulk_download/awards (NOT used: no PSC filter): https://github.com/fedspendingtransparency/usaspending-api/blob/master/usaspending_api/api_contracts/contracts/v2/bulk_download/awards.md
# - FPDS Extent Competed codes: https://fpds.gov/help/Extent_Competed.htm

# %%
import io
import time
import zipfile

import httpx
import pandas as pd

API = "https://api.usaspending.gov/api/v2"
DOD = {"type": "awarding", "tier": "toptier", "name": "Department of Defense"}
CONTRACTS = ["A", "B", "C", "D"]  # BPA call, purchase order, delivery order, definitive contract
FY19_ON = [{"start_date": "2018-10-01", "end_date": "2026-09-30"}]


def award_count(psc_paths: list[list[str]], agency: dict = DOD) -> int:
    body = {
        "filters": {
            "award_type_codes": CONTRACTS,
            "time_period": FY19_ON,
            "agencies": [agency],
            "psc_codes": {"require": psc_paths},
        }
    }
    r = httpx.post(f"{API}/search/spending_by_award_count/", json=body, timeout=60)
    r.raise_for_status()
    return r.json()["results"]["contracts"]


def psc_dollars(psc_paths: list[list[str]]) -> pd.DataFrame:
    body = {
        "filters": {
            "award_type_codes": CONTRACTS,
            "time_period": FY19_ON,
            "agencies": [DOD],
            "psc_codes": {"require": psc_paths},
        },
        "limit": 100,
    }
    r = httpx.post(f"{API}/search/spending_by_category/psc/", json=body, timeout=60)
    r.raise_for_status()
    return pd.DataFrame(r.json()["results"])[["code", "name", "amount"]]


# %% [markdown]
# ## Candidate slices — volume and dollars

# %%
candidates = {
    "FSG 59 electrical/electronic components": [["Product", "59"]],
    "FSG 13 ammunition & explosives": [["Product", "13"]],
    "FSG 20 ship & marine equipment": [["Product", "20"]],
}
rows = []
for label, paths in candidates.items():
    dollars = psc_dollars(paths)
    rows.append(
        {
            "slice": label,
            "awards": award_count(paths),
            "dollars_B": round(dollars.amount.sum() / 1e9, 2),
            "pscs": len(dollars),
        }
    )
pd.DataFrame(rows)

# %% [markdown]
# ## Sample download — real column names, not guessed ones
# One week of FSG 59 DoD transactions. The download is async: request -> poll status -> fetch zip.

# %%
body = {
    "filters": {
        "agencies": [DOD],
        "psc_codes": {"require": [["Product", "59"]]},
        "time_period": [{"start_date": "2025-09-01", "end_date": "2025-09-07"}],
        "award_type_codes": CONTRACTS,
    },
    "file_format": "csv",
}
req = httpx.post(f"{API}/download/transactions/", json=body, timeout=60).json()
while True:
    status = httpx.get(f"{API}/download/status", params={"file_name": req["file_name"]}).json()
    print(status["status"], status["total_rows"], status["seconds_elapsed"])
    if status["status"] in ("finished", "failed"):
        break
    time.sleep(10)

blob = httpx.get(status["file_url"], timeout=120).content
with zipfile.ZipFile(io.BytesIO(blob)) as z:
    name = next(n for n in z.namelist() if "PrimeTransactions" in n)
    df = pd.read_csv(z.open(name), dtype=str, low_memory=False)
print(len(df), "rows,", len(df.columns), "columns")

# %% [markdown]
# ## Findings that shaped the schema

# %%
desc = df.transaction_description.fillna("")
has_bang = desc.str.contains("!", regex=False)
item = desc[has_bang].str.split("!", n=1).str[1].str.strip()
print(f"'PR#!ITEM NAME' format: {has_bang.mean():.0%} of rows")
print(f"max item-name length: {item.str.len().max()}  (DLA truncates at 19)")
print(item.value_counts().head(10))

# %%
obl = pd.to_numeric(df.federal_action_obligation)
print(f"rows with obligation <= 0: {(obl <= 0).mean():.0%}  (de-obligations: net, don't drop)")
print(df.groupby(["extent_competed_code", "extent_competed"]).size())
print(f"single-offer share: {(df.number_of_offers_received == '1').mean():.0%}")
print(df.awarding_sub_agency_name.value_counts())
