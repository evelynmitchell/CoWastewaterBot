"""CoWastewaterBot: an easier interface to Colorado wastewater surveillance data.

The dataset behind CDPHE's wastewater dashboard is a plain ArcGIS Open Data
feature service. This package wraps that service's REST query API in a small,
typed core (:mod:`cowastewater.client`) and layers channels on top of it:

* :mod:`cowastewater.server` — an MCP server exposing the data as tools for LLMs.
* (planned) RSS/Atom and ATProto feeds driven by :mod:`cowastewater.analysis`.
"""

__version__ = "0.1.0"
