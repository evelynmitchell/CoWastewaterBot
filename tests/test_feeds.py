from cowastewater.analysis import NotableChange
from cowastewater.config import Config, FieldMap
from cowastewater.feeds import FeedStore, item_from_change, render_atom
from cowastewater.models import Reading


def _change(value=250.0, date_ms=1718755200000, reason="concentration up 150% vs. prior reading"):
    reading = Reading.from_attributes(
        {
            "utility": "Metro Denver",
            "pcr_target": "SARS-CoV-2",
            "measure_date": date_ms,
            "viral_conc_raw_LP1": value,
        },
        FieldMap(),
    )
    return NotableChange(reading=reading, reason=reason)


def test_item_from_change_shape():
    item = item_from_change(_change())
    assert item["site"] == "Metro Denver"
    assert item["pathogen"] == "SARS-CoV-2"
    assert item["value"] == 250.0
    assert item["id"] == "metro denver|sars-cov-2|2024-06-19"
    assert "SARS-CoV-2" in item["title"]


def test_feedstore_dedups_and_caps(tmp_path):
    store = FeedStore(path=tmp_path / "feed.json", max_items=2)
    a = item_from_change(_change(date_ms=1718150400000))
    b = item_from_change(_change(date_ms=1718755200000))

    assert store.add(a) is True
    assert store.add(a) is False  # same id -> not re-added
    assert store.add(b) is True
    # Newest is inserted at the front.
    assert store.items[0]["id"] == b["id"]

    # Cap enforced.
    c = item_from_change(_change(date_ms=1719360000000))
    store.add(c)
    assert len(store.items) == 2
    assert store.items[0]["id"] == c["id"]


def test_feedstore_roundtrip(tmp_path):
    path = tmp_path / "feed.json"
    store = FeedStore.load(path)
    store.add(item_from_change(_change()))
    store.save()

    reloaded = FeedStore.load(path)
    assert len(reloaded.items) == 1
    assert reloaded.items[0]["pathogen"] == "SARS-CoV-2"


def test_render_atom_writes_valid_feed(tmp_path):
    config = Config(feed_path=str(tmp_path / "feed.xml"), feed_data_path=str(tmp_path / "feed.json"))
    store = FeedStore(path=tmp_path / "feed.json")
    store.add(item_from_change(_change()))

    xml = render_atom(store, config)
    assert xml.startswith("<?xml")
    assert "<feed" in xml and "<entry>" in xml
    assert "SARS-CoV-2" in xml
    # File was written too.
    assert (tmp_path / "feed.xml").read_text().count("<entry>") == 1
