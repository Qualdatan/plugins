# SPDX-License-Identifier: AGPL-3.0-only
"""Qualdatan plugin manager.

Manages community bundles (YAML data packs that define facets, codebooks,
methods and folder layouts for concrete analysis domains). Phase C fills in
the modules listed below.

Planned modules
---------------
- ``manager``        install / enable / disable / update bundles
- ``registry``       index of installed bundles
- ``loader``         YAML bundle -> facets/presets loader
- ``verify``         schema + hash + signature verification
- ``cache``          local bundle cache under platform-appropriate app data
- ``server_client``  HTTP client for the (later) Qualdatan/plugin-server
- ``bundle``         bundle manifest data types

See the umbrella repo for the overall plan:
https://github.com/GeneralPawz/Qualdatan
"""

__version__ = "0.1.0"
