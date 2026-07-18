from datetime import datetime, timezone

from cowastewater.config import Config, FieldMap
from cowastewater.models import Reading
from cowastewater.risk import assess_pathogen, assess_site

DAY_MS = 86_400_000
BASE = 1_600_000_000_000  # arbitrary fixed epoch ms


def _readings(pathogen, values, site="Fort Collins - Drake", start=BASE, step_days=7):
    out = []
    for i, v in enumerate(values):
        out.append(
            Reading.from_attributes(
                {
                    "utility": site,
                    "pcr_target": pathogen,
                    "measure_date": start + i * step_days * DAY_MS,
                    "viral_conc_raw_LP1": v,
                },
                FieldMap(),
            )
        )
    return out


def test_quintile_of_latest_in_distribution():
    # History 10..50, latest 30 -> 3 of 5 at-or-below -> 60th pct -> quintile 3.
    r = assess_pathogen("sars-cov-2", _readings("sars-cov-2", [10, 20, 50, 40, 30]), Config())
    assert r.quintile == 3
    assert r.latest_value == 30.0
    assert r.n_history == 5


def test_top_and_bottom_quintiles():
    hi = assess_pathogen("sars-cov-2", _readings("sars-cov-2", [10, 20, 30, 40, 50]), Config())
    assert hi.quintile == 5  # latest 50 is the max
    lo = assess_pathogen("sars-cov-2", _readings("sars-cov-2", [50, 40, 30, 20, 10]), Config())
    assert lo.quintile == 1  # latest 10 is the min


def test_trend_rising_and_falling():
    up = assess_pathogen("sars-cov-2", _readings("sars-cov-2", [100, 110, 130, 160]), Config())
    assert up.trend == "rising"
    down = assess_pathogen("sars-cov-2", _readings("sars-cov-2", [160, 130, 110, 90]), Config())
    assert down.trend == "falling"
    flat = assess_pathogen("sars-cov-2", _readings("sars-cov-2", [100, 101, 99, 100]), Config())
    assert flat.trend == "flat"


def test_verdict_follows_the_rule():
    cfg = Config()
    # Quintile 2 (latest below median) -> OK regardless of trend.
    ok = assess_pathogen("sars-cov-2", _readings("sars-cov-2", [10, 40, 50, 60, 20]), cfg)
    assert ok.quintile <= 2 and ok.level == 0

    # Elevated (top of range) and rising -> avoid (level 2).
    avoid = assess_pathogen("sars-cov-2", _readings("sars-cov-2", [10, 20, 30, 40, 100]), cfg)
    assert avoid.quintile >= cfg.caution_quintile
    assert avoid.trend == "rising" and avoid.level == 2

    # Elevated but falling -> caution (level 1). Latest 340 sits high in the
    # distribution, and the last 4 readings decline 400->340.
    caution = assess_pathogen("sars-cov-2", _readings("sars-cov-2", [10, 20, 400, 380, 360, 340]), cfg)
    assert caution.quintile >= cfg.caution_quintile
    assert caution.trend == "falling" and caution.level == 1


def _now(readings):
    latest = max(r.date for r in readings if r.date)
    return datetime.fromtimestamp(latest.timestamp(), tz=timezone.utc)


def test_site_worst_case_across_pathogens():
    cfg = Config()
    covid_low = _readings("sars-cov-2", [50, 40, 30, 20, 10])  # quintile 1
    flu_high = _readings("Influenza A", [10, 20, 30, 40, 100])  # quintile 5, rising
    readings = covid_low + flu_high
    site = assess_site("Fort Collins - Drake", readings, cfg, now=_now(readings))
    assert site.level == 2
    assert site.driver == "Influenza A"
    # Both pathogens are reported.
    assert {p.pathogen for p in site.pathogens} == {"sars-cov-2", "Influenza A"}


def test_non_respiratory_pathogens_ignored():
    cfg = Config()
    readings = _readings("Measles", [10, 20, 30, 40, 100])  # not in respiratory set
    site = assess_site("Boulder", readings, cfg, now=_now(readings))
    assert site.level == 0 and site.driver is None


def test_lookback_limits_history():
    # 400 days of weekly data; a 90-day lookback keeps only recent readings.
    cfg = Config(quintile_lookback_days=90)
    values = list(range(1, 60))  # rising series
    readings = _readings("sars-cov-2", values, step_days=7)
    now = datetime.fromtimestamp(readings[-1].date.timestamp(), tz=timezone.utc)
    r = assess_site("Fort Collins - Drake", readings, cfg, now=now)
    covid = next(p for p in r.pathogens if p.pathogen == "sars-cov-2")
    # ~13 weekly points fit in 90 days, far fewer than all 59.
    assert covid.n_history < 20
