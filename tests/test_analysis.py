from cowastewater.analysis import find_notable, summarize
from cowastewater.config import Config, FieldMap
from cowastewater.models import Reading


def _reading(site, pathogen, date_ms, value, trend=None):
    # Use a FieldMap that also maps the (normally absent) trend/county columns so
    # these tests can exercise trend-based detection and the county in summaries.
    fields = FieldMap(trend="trend", county="county")
    return Reading.from_attributes(
        {
            "utility": site,
            "pcr_target": pathogen,
            "measure_date": date_ms,
            "viral_conc_raw_LP1": value,
            "trend": trend,
            "county": "Denver",
        },
        fields,
    )


def test_spike_detected_across_consecutive_readings():
    config = Config(spike_pct=50)
    readings = [
        _reading("Metro Denver", "SARS-CoV-2", 1718150400000, 100.0),
        _reading("Metro Denver", "SARS-CoV-2", 1718755200000, 250.0),  # +150%
    ]
    notable = find_notable(readings, config)
    assert len(notable) == 1
    assert "up 150%" in notable[0].reason
    assert notable[0].previous is not None


def test_small_rise_below_threshold_ignored():
    config = Config(spike_pct=50)
    readings = [
        _reading("Metro Denver", "SARS-CoV-2", 1718150400000, 100.0),
        _reading("Metro Denver", "SARS-CoV-2", 1718755200000, 120.0),  # +20%
    ]
    assert find_notable(readings, config) == []


def test_increasing_trend_flagged_without_prior():
    config = Config()  # default notable_trends includes "increasing"
    readings = [_reading("Boulder", "Influenza", 1718755200000, 40.0, trend="Increasing")]
    notable = find_notable(readings, config)
    assert len(notable) == 1
    assert "increasing" in notable[0].reason.lower()


def test_series_are_isolated_by_site_and_pathogen():
    config = Config(spike_pct=50)
    # A jump only appears if the two Denver readings are compared to each other,
    # not to Boulder's unrelated series.
    readings = [
        _reading("Boulder", "SARS-CoV-2", 1718150400000, 1000.0),
        _reading("Metro Denver", "SARS-CoV-2", 1718150400000, 100.0),
        _reading("Metro Denver", "SARS-CoV-2", 1718755200000, 300.0),
    ]
    notable = find_notable(readings, config)
    assert len(notable) == 1
    assert notable[0].reading.site == "Metro Denver"


def test_summarize_is_human_readable():
    config = Config(spike_pct=50)
    readings = [
        _reading("Metro Denver", "SARS-CoV-2", 1718150400000, 100.0),
        _reading("Metro Denver", "SARS-CoV-2", 1718755200000, 250.0),
    ]
    line = summarize(find_notable(readings, config)[0])
    assert "SARS-CoV-2" in line and "Metro Denver" in line and "Denver" in line
