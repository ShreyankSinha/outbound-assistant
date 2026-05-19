from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

import pandas as pd

CUSTOMER_DATA_SOURCE_KIND = os.getenv("CUSTOMER_DATA_SOURCE", "excel").strip().lower()
CUSTOMER_WORKBOOK_PATH = Path(os.getenv("CUSTOMER_WORKBOOK_PATH", "data/customers.xlsx"))


class CustomerDataSource(Protocol):
    def get_phone_by_id(self, customer_id: int) -> str:
        ...


class ExcelCustomerDataSource:
    def __init__(self, workbook_path: str | Path = CUSTOMER_WORKBOOK_PATH) -> None:
        self.workbook_path = Path(workbook_path)

    def get_phone_by_id(self, customer_id: int) -> str:
        if not self.workbook_path.exists():
            raise FileNotFoundError(f"Customer workbook not found at '{self.workbook_path}'.")

        frame = pd.read_excel(self.workbook_path, dtype={"customer_id": "int64", "phone_number": "string"})
        required_columns = {"customer_id", "phone_number"}
        missing_columns = required_columns.difference(frame.columns)
        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise ValueError(f"Customer workbook is missing required columns: {missing}.")

        matches = frame.loc[frame["customer_id"] == customer_id]
        if matches.empty:
            raise LookupError(f"No phone number found for customer_id={customer_id}.")

        phone_number = str(matches.iloc[0]["phone_number"]).strip()
        if not phone_number:
            raise LookupError(f"Customer {customer_id} exists but has no phone number recorded.")
        return phone_number


def _build_default_data_source() -> CustomerDataSource:
    if CUSTOMER_DATA_SOURCE_KIND == "excel":
        return ExcelCustomerDataSource()
    raise ValueError(f"Unsupported customer data source '{CUSTOMER_DATA_SOURCE_KIND}'.")


def get_phone_by_id(customer_id: int, data_source: CustomerDataSource | None = None) -> str:
    source = data_source or _build_default_data_source()
    return source.get_phone_by_id(customer_id)
