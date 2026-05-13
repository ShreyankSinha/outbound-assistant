from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.schemas.customer import CustomerRecord


class CustomerDirectory:
    def __init__(self, workbook_path: str | Path = "data/customers.xlsx") -> None:
        self.workbook_path = Path(workbook_path)

    def get_customer_by_id(self, customer_id: int) -> CustomerRecord | None:
        if not self.workbook_path.exists():
            return None
        frame = pd.read_excel(
            self.workbook_path,
            dtype={"customer_id": "int64", "customer_name": "string", "phone_number": "string"},
        )
        matches = frame.loc[frame["customer_id"] == customer_id]
        if matches.empty:
            return None
        row = matches.iloc[0].to_dict()
        return CustomerRecord.model_validate(row)
