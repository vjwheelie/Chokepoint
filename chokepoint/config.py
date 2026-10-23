"""Project-wide constants: the data slice (D-001), window (D-012) and paths."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
DB_PATH = DATA_DIR / "chokepoint.duckdb"

USASPENDING_API = "https://api.usaspending.gov/api/v2"

# D-001: FSG 59, DoD-awarding, prime contracts only.
AWARDING_AGENCY = {"type": "awarding", "tier": "toptier", "name": "Department of Defense"}
PSC_FILTER = [["Product", "59"]]
CONTRACT_AWARD_TYPES = ["A", "B", "C", "D"]  # BPA call, purchase order, delivery order, definitive

# D-012: complete fiscal years only. FY2027 began 2026-10-01 and is excluded.
FIRST_FY = 2019
LAST_FY = 2026

# Column names verified against a real download/transactions file (see notebooks/01).
# Requesting only these cuts each file from 297 columns to 33.
TRANSACTION_COLUMNS = [
    "contract_transaction_unique_key",
    "contract_award_unique_key",
    "award_id_piid",
    "modification_number",
    "parent_award_id_piid",
    "federal_action_obligation",
    "action_date",
    "action_date_fiscal_year",
    "awarding_sub_agency_code",
    "awarding_sub_agency_name",
    "awarding_office_code",
    "awarding_office_name",
    "recipient_uei",
    "recipient_name",
    "recipient_parent_uei",
    "recipient_parent_name",
    "prime_award_transaction_recipient_county_fips_code",
    "recipient_state_code",
    "recipient_county_name",
    "prime_award_transaction_place_of_performance_county_fips_code",
    "primary_place_of_performance_state_code",
    "primary_place_of_performance_county_name",
    "award_type_code",
    "transaction_description",
    "product_or_service_code",
    "product_or_service_code_description",
    "naics_code",
    "naics_description",
    "extent_competed_code",
    "other_than_full_and_open_competition_code",
    "number_of_offers_received",
    "contracting_officers_determination_of_business_size",
    "usaspending_permalink",
]
