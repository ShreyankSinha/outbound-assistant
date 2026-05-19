from app.services.customer_lookup import ExcelCustomerDataSource, get_phone_by_id


def test_get_phone_by_id_found():
    assert get_phone_by_id(1) == "+61413727809"


def test_excel_customer_data_source_missing_id_raises_descriptive_error():
    source = ExcelCustomerDataSource()

    try:
        source.get_phone_by_id(999999)
    except LookupError as exc:
        assert "customer_id=999999" in str(exc)
    else:
        raise AssertionError("Expected a missing customer lookup to raise LookupError.")
