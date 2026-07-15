from datetime import datetime, timezone

from cowastewater.config import FieldMap
from cowastewater.models import Reading


def test_parses_esri_epoch_millis():
    attrs = {
        "Utility": "Metro Denver",
        "Pathogen": "SARS-CoV-2",
        "Date": 1718755200000,
        "Concentration": "250.0",
    }
    r = Reading.from_attributes(attrs, FieldMap())
    assert r.site == "Metro Denver"
    assert r.pathogen == "SARS-CoV-2"
    assert r.value == 250.0
    assert r.date == datetime(2024, 6, 19, tzinfo=timezone.utc)


def test_parses_iso_string_dates():
    r = Reading.from_attributes({"Date": "2024-06-19"}, FieldMap())
    assert r.date is not None
    assert r.date.year == 2024 and r.date.month == 6


def test_key_is_case_insensitive_and_date_only():
    a = Reading.from_attributes(
        {"Utility": "Metro Denver", "Pathogen": "SARS-CoV-2", "Date": 1718755200000}, FieldMap()
    )
    b = Reading.from_attributes(
        {"Utility": "metro denver", "Pathogen": "sars-cov-2", "Date": 1718755200000}, FieldMap()
    )
    assert a.key == b.key


def test_bad_values_become_none():
    r = Reading.from_attributes({"Concentration": "not-a-number", "Date": ""}, FieldMap())
    assert r.value is None
    assert r.date is None
