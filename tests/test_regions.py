from cowastewater.regions import region_for


def test_fort_collins_is_north():
    for s in ["Fort Collins - Drake", "Fort Collins - Mulberry", "Fort Collins - Boxelder",
              "South Fort Collins", "Loveland", "Estes Park + Upper Thompson"]:
        assert region_for(s) == "North", s


def test_regions_across_the_state():
    # Assignments match the DHSEM field-service-area county rosters.
    cases = {
        "Grand Junction - Persigo": "West",     # Mesa
        "CO Springs - JD Phillips": "Central",  # El Paso
        "Aspen": "West",                         # Pitkin -> West
        "Glenwood Springs": "West",              # Garfield -> West
        "Greeley": "Northeast",                  # Weld
        "Durango": "Southwest",                  # La Plata
        "Telluride": "Southwest",                # San Miguel -> Southwest
        "Alamosa": "San Luis Valley",
        "Pueblo": "South",
        "La Junta": "Southeast",                 # Otero
        "Aurora": "East",                        # Adams/Arapahoe metro core
        "Castle Rock": "North",                  # Douglas -> North
        "Highlands Ranch Water and Sanitation District": "North",  # Douglas
        "Walden": "Northwest",                   # Jackson -> Northwest
    }
    for site, region in cases.items():
        assert region_for(site) == region, site


def test_case_insensitive_and_unknown():
    assert region_for("boulder") == "North"
    assert region_for("Nonexistent Plant") is None
    assert region_for(None) is None
