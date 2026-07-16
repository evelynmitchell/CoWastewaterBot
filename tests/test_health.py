from datetime import datetime, timezone

from cowastewater.health import HealthStore, days_since_update


def _dt(y, m, d):
    return datetime(y, m, d, tzinfo=timezone.utc)


def test_days_since_update():
    assert days_since_update(_dt(2026, 7, 1), _dt(2026, 7, 9)) == 8
    assert days_since_update(None, _dt(2026, 7, 9)) is None


def test_fresh_data_is_ok_and_no_outage(tmp_path):
    store = HealthStore(path=tmp_path / "health.json")
    snap = store.record(_dt(2026, 7, 8), _dt(2026, 7, 9), freshness_days=10)
    assert snap["status"] == "ok"
    assert snap["days_since_update"] == 1
    assert snap["days_since_last_outage"] is None  # never had one
    assert store.outage_events == 0


def test_stale_data_marks_outage(tmp_path):
    store = HealthStore(path=tmp_path / "health.json")
    # Newest reading is 20 days old, threshold 10 -> outage.
    snap = store.record(_dt(2026, 6, 19), _dt(2026, 7, 9), freshness_days=10)
    assert snap["status"] == "outage"
    assert snap["days_since_update"] == 20
    assert snap["days_since_last_outage"] == 0  # in outage right now
    assert store.outage_events == 1


def test_outage_then_recovery_streak_counts_up(tmp_path):
    path = tmp_path / "health.json"
    store = HealthStore(path=path)
    # Day 1: outage observed.
    store.record(_dt(2026, 6, 19), _dt(2026, 7, 1), freshness_days=10)
    assert store.in_outage is True
    store.save()

    # Day 2: data recovered (fresh). Reload to prove persistence.
    store = HealthStore.load(path)
    snap = store.record(_dt(2026, 7, 4), _dt(2026, 7, 5), freshness_days=10)
    assert snap["status"] == "ok"
    # last_outage_date was 2026-07-01; now 2026-07-05 -> 4 days since.
    assert snap["days_since_last_outage"] == 4
    assert store.outage_events == 1  # still one episode

    # A later, separate outage bumps the episode counter.
    snap = store.record(_dt(2026, 6, 1), _dt(2026, 7, 20), freshness_days=10)
    assert snap["status"] == "outage"
    assert store.outage_events == 2


def test_snapshot_is_read_only(tmp_path):
    store = HealthStore(path=tmp_path / "health.json")
    store.record(_dt(2026, 6, 19), _dt(2026, 7, 9), freshness_days=10)
    before = store.outage_events
    store.snapshot(_dt(2026, 7, 15))
    assert store.outage_events == before  # snapshot must not mutate
