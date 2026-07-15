from datetime import datetime, timezone

from cowastewater.config import FieldMap
from cowastewater.models import Reading


def test_parses_esri_epoch_millis():
    attrs = {
        "utility": "Metro Denver",
        "pcr_target": "SARS-CoV-2",
        "measure_date": 1718755200000,
        "viral_conc_raw_LP1": "250.0",
    }
    r = Reading.from_attributes(attrs, FieldMap())
    assert r.site == "Metro Denver"
    assert r.pathogen == "SARS-CoV-2"
    assert r.value == 250.0
    assert r.date == datetime(2024, 6, 19, tzinfo=timezone.utc)


def test_parses_iso_string_dates():
    r = Reading.from_attributes({"measure_date": "2024-06-19"}, FieldMap())
    assert r.date is not None
    assert r.date.year == 2024 and r.date.month == 6


def test_key_is_case_insensitive_and_date_only():
    a = Reading.from_attributes(
        {"utility": "Metro Denver", "pcr_target": "SARS-CoV-2", "measure_date": 1718755200000},
        FieldMap(),
    )
    b = Reading.from_attributes(
        {"utility": "metro denver", "pcr_target": "sars-cov-2", "measure_date": 1718755200000},
        FieldMap(),
    )
    assert a.key == b.key


def test_bad_values_become_none():
    r = Reading.from_attributes({"viral_conc_raw_LP1": "not-a-number", "measure_date": ""}, FieldMap())
    assert r.value is None
    assert r.date is None


def test_value_coalesces_across_lab_phase_columns():
    # A row populates whichever lab-phase column matches its phase; the others
    # are null. Reading.value picks the first non-null in order.
    r = Reading.from_attributes(
        {"viral_conc_raw_LP1": None, "viral_conc_raw_LP2": 42.0, "viral_conc_raw_LP3": None},
        FieldMap(),
    )
    assert r.value == 42.0


def test_absent_optional_columns_are_none():
    # trend/county/unit have empty default names on the live layer.
    r = Reading.from_attributes({"utility": "Metro Denver"}, FieldMap())
    assert r.trend is None and r.county is None and r.unit is None
