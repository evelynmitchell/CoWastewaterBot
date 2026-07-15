from cowastewater.config import FieldMap
from cowastewater.models import Reading
from cowastewater.state import State


def _reading(value, date_ms=1718755200000):
    return Reading.from_attributes(
        {
            "utility": "Metro Denver",
            "pcr_target": "SARS-CoV-2",
            "measure_date": date_ms,
            "viral_conc_raw_LP1": value,
        },
        FieldMap(),
    )


def test_dedup_roundtrip(tmp_path):
    path = tmp_path / "state.json"
    state = State.load(path)
    r = _reading(250.0)

    assert state.is_new(r)
    state.mark(r)
    state.save()

    reloaded = State.load(path)
    assert not reloaded.is_new(r)
    assert reloaded.latest_date == r.date.isoformat()


def test_filter_new_only_returns_unseen(tmp_path):
    state = State.load(tmp_path / "state.json")
    seen = _reading(100.0, date_ms=1718150400000)
    state.mark(seen)

    unseen = _reading(250.0, date_ms=1718755200000)
    result = state.filter_new([seen, unseen])
    assert result == [unseen]


def test_latest_date_tracks_maximum(tmp_path):
    state = State.load(tmp_path / "state.json")
    older = _reading(100.0, date_ms=1718150400000)
    newer = _reading(250.0, date_ms=1718755200000)
    state.mark(newer)
    state.mark(older)  # marking an older one must not move latest_date backward
    assert state.latest_date == newer.date.isoformat()
