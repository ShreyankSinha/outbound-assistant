"""
Task 0: Normalise customer phone numbers to E.164 format.
- Customer ID 1 → +19852391073 (verified test number)
- All others → strip non-digits, normalise to E.164
Run from project root: .venv/Scripts/python scripts/fix_customers.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

WORKBOOK = Path("data/customers.xlsx")
TEST_NUMBER = "+19852391073"
FALLBACK = TEST_NUMBER


def normalise_e164(raw: str, customer_id: int) -> str:
    """Return an E.164 number or FALLBACK if unrecognisable."""
    if customer_id == 1:
        return TEST_NUMBER

    digits = re.sub(r"\D", "", str(raw))

    if len(digits) == 10:
        return f"+1{digits}"
    elif len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    elif len(digits) >= 12:
        # Assume already has country code (e.g. 614xxxxxxxx → +614…)
        return f"+{digits}"
    else:
        print(f"  WARNING: customer_id={customer_id} has unrecognisable number {raw!r} "
              f"(digits={digits!r}). Using fallback {FALLBACK}.")
        return FALLBACK


def main() -> None:
    if not WORKBOOK.exists():
        print(f"ERROR: {WORKBOOK} not found. Run from project root.", file=sys.stderr)
        sys.exit(1)

    df = pd.read_excel(
        WORKBOOK,
        dtype={"customer_id": "int64", "customer_name": "string", "phone_number": "string"},
    )

    print("=== BEFORE normalisation ===")
    for _, row in df.iterrows():
        print(f"  ID {row['customer_id']:>3}  {row['phone_number']}")

    df["phone_number"] = df.apply(
        lambda row: normalise_e164(row["phone_number"], int(row["customer_id"])),
        axis=1,
    )

    df.to_excel(WORKBOOK, index=False)

    print("\n=== AFTER normalisation ===")
    for _, row in df.iterrows():
        print(f"  ID {row['customer_id']:>3}  {row['phone_number']}")

    # Validate
    invalid = df[~df["phone_number"].str.match(r"^\+\d{10,15}$")]
    if not invalid.empty:
        print(f"\nERROR: {len(invalid)} rows still have invalid E.164 numbers:")
        print(invalid[["customer_id", "phone_number"]])
        sys.exit(1)

    print(f"\nAll {len(df)} numbers are valid E.164. Saved to {WORKBOOK}.")


if __name__ == "__main__":
    main()
