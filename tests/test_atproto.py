from cowastewater.analysis import NotableChange
from cowastewater.atproto_bot import format_post, post_change
from cowastewater.config import Config, FieldMap
from cowastewater.models import Reading


def _change(reason="concentration up 150% vs. prior reading"):
    reading = Reading.from_attributes(
        {
            "utility": "Metro Denver",
            "pcr_target": "SARS-CoV-2",
            "measure_date": 1718755200000,
            "viral_conc_raw_LP1": 250.0,
        },
        FieldMap(),
    )
    return NotableChange(reading=reading, reason=reason)


def test_format_post_includes_summary():
    text = format_post(_change())
    assert "SARS-CoV-2" in text and "Metro Denver" in text


def test_format_post_truncates_to_limit():
    text = format_post(_change(reason="x" * 500))
    assert len(text) <= 300
    assert text.endswith("…")


def test_post_change_is_dry_run_without_credentials():
    # Default config has no handle/password -> composes but does not publish.
    result = post_change(_change(), Config())
    assert result.dry_run is True
    assert result.posted is False
    assert "SARS-CoV-2" in result.text
