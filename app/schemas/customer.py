from __future__ import annotations

from pydantic import BaseModel


class CustomerRecord(BaseModel):
    customer_id: int
    customer_name: str
    phone_number: str
