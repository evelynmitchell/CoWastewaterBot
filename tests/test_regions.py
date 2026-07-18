from cowastewater.regions import region_for


def test_fort_collins_is_north():
    for s in ["Fort Collins - Drake", "Fort Collins - Mulberry", "Fort Collins - Boxelder",
              "South Fort Collins", "Loveland", "Estes Park + Upper Thompson"]:
        assert region_for(s) == "North", s


def test_regions_across_the_state():
    cases = {
        "Grand Junction - Persigo": "West",     # Mesa
        "CO Springs - JD Phillips": "Central",  # El Paso
        "Aspen": "Northwest",                    # Pitkin
        "Greeley": "Northeast",                  # Weld
        "Durango": "Southwest",                  # La Plata
        "Alamosa": "San Luis Valley",
        "Pueblo": "South",
        "La Junta": "Southeast",                 # Otero
        "Aurora": "East",                        # Denver metro
    }
    for site, region in cases.items():
        assert region_for(site) == region, site


def test_case_insensitive_and_unknown():
    assert region_for("boulder") == "North"
    assert region_for("Nonexistent Plant") is None
    assert region_for(None) is None
