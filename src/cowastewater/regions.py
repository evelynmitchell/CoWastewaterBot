"""Utility -> Colorado DHSEM regional service area.

The CDPHE dashboard labels each utility with its Colorado emergency-management
region, but that label is **not** in the downloadable data (the feature layer
has no region or geometry column). So this is a curated map, keyed off the
authoritative **county -> region** grouping from the Colorado DHSEM "Regional
Service Areas" map (10 regions: North, Northwest, Northeast, East, Central,
West, Southwest, San Luis Valley, South, Southeast).

* ``_COUNTY_REGION`` — county -> region, from the DHSEM field-service-area county
  lists (authoritative; see https://dhsem.colorado.gov/fieldoperations). Every
  region below matches DHSEM's published county roster.
* ``_SITE_COUNTY`` — each monitoring utility -> the county its plant sits in.

Region is derived from the two. County assignments are authoritative; entries
marked ``# verify`` are towns that straddle a county line (the plant could sit in
the neighboring county) — check against the dashboard if in doubt.
"""

from __future__ import annotations

_COUNTY_REGION: dict[str, str] = {
    # North.
    **dict.fromkeys(
        ["larimer", "boulder", "broomfield", "clear creek", "gilpin", "jefferson", "douglas"],
        "North",
    ),
    # Northwest.
    **dict.fromkeys(
        ["moffat", "routt", "rio blanco", "jackson", "grand", "eagle", "summit"],
        "Northwest",
    ),
    # Northeast.
    **dict.fromkeys(
        ["weld", "morgan", "logan", "sedgwick", "phillips", "washington", "yuma"],
        "Northeast",
    ),
    # East (Denver core + eastern plains).
    **dict.fromkeys(
        ["denver", "adams", "arapahoe", "elbert", "lincoln", "kit carson", "cheyenne"],
        "East",
    ),
    # Central.
    **dict.fromkeys(["el paso", "teller", "park", "lake", "chaffee"], "Central"),
    # West (western slope, incl. Mesa/Grand Junction and Garfield/Pitkin).
    **dict.fromkeys(
        ["mesa", "delta", "montrose", "gunnison", "ouray", "garfield", "pitkin"], "West"
    ),
    # Southwest.
    **dict.fromkeys(
        ["montezuma", "dolores", "san juan", "la plata", "archuleta", "san miguel"], "Southwest"
    ),
    # San Luis Valley.
    **dict.fromkeys(
        ["saguache", "mineral", "rio grande", "alamosa", "conejos", "costilla"],
        "San Luis Valley",
    ),
    # South.
    **dict.fromkeys(["pueblo", "custer", "huerfano", "fremont", "las animas"], "South"),
    # Southeast.
    **dict.fromkeys(["crowley", "kiowa", "otero", "bent", "prowers", "baca"], "Southeast"),
}

# Utility (as it appears in the data) -> county. Matched case-insensitively.
_SITE_COUNTY: dict[str, str] = {
    "alamosa": "alamosa",
    "arapahoe county": "arapahoe",  # East
    "aspen": "pitkin",
    "aurora": "arapahoe",  # East
    "basalt": "eagle",  # verify: straddles Eagle (NW) / Pitkin (West)
    "berthoud": "larimer",  # verify: straddles Larimer/Weld
    "boulder": "boulder",
    "brighton": "adams",  # East
    "broomfield": "broomfield",
    "brush": "morgan",
    "castle rock": "douglas",  # North (Douglas per DHSEM)
    "cherokee metro district": "el paso",
    "co springs - jd phillips": "el paso",
    "co springs - las vegas": "el paso",
    "copper mountain": "summit",
    "cortez sanitation district": "montezuma",
    "cripple creek": "teller",
    "delta": "delta",
    "durango": "la plata",
    "eagle river sd - avon": "eagle",
    "eagle river sd - edwards": "eagle",
    "eagle river sd - vail": "eagle",
    "elizabeth": "elbert",  # East (Elbert)
    "erie": "boulder",  # verify: straddles Boulder/Weld
    "estes park + upper thompson": "larimer",
    "fort collins - boxelder": "larimer",
    "fort collins - drake": "larimer",
    "fort collins - mulberry": "larimer",
    "frisco": "summit",
    "glenwood springs": "garfield",
    "grand junction - persigo": "mesa",
    "greeley": "weld",
    "gunnison": "gunnison",
    "highlands ranch water and sanitation district": "douglas",  # North (Douglas)
    "keystone": "summit",
    "la junta": "otero",
    "lafayette": "boulder",
    "longmont": "boulder",  # verify: straddles Boulder/Weld
    "louisville": "boulder",
    "loveland": "larimer",
    "metro wastewater rwhtf - cc": "adams",  # East
    "metro wastewater rwhtf - ntp": "adams",  # East
    "metro wastewater rwhtf - prc": "denver",  # East
    "montrose": "montrose",
    "nederland": "boulder",
    "ouray": "ouray",
    "pagosa area": "archuleta",
    "pueblo": "pueblo",
    "purgatory resort": "la plata",
    "ridgway": "ouray",
    "salida": "chaffee",
    "silverthorne/dillon": "summit",
    "silverton": "san juan",
    "snowmass village": "pitkin",
    "south adams county": "adams",  # East
    "south fort collins": "larimer",
    "south platte": "denver",  # verify: ambiguous "South Platte" plant
    "steamboat springs": "routt",
    "telluride": "san miguel",  # Southwest (San Miguel per DHSEM)
    "the pinery": "douglas",  # North (Douglas)
    "tri-lakes - monument": "el paso",
    "tri-lakes - palmer lake": "el paso",
    "tri-lakes - woodmoor north": "el paso",
    "tri-lakes - woodmoor south": "el paso",
    "trinidad": "las animas",  # South (Las Animas per DHSEM)
    "upper blue sd - breckenridge": "summit",
    "walden": "jackson",  # Northwest (Jackson per DHSEM)
    "wellington": "larimer",
    "windsor": "weld",  # verify: straddles Weld/Larimer
    "woodland park": "teller",
}


def region_for(site: str | None) -> str | None:
    """Region for a utility name, or None if unmapped."""
    if not site:
        return None
    county = _SITE_COUNTY.get(site.strip().lower())
    return _COUNTY_REGION.get(county) if county else None
