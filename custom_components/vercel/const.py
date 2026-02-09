"""Constants for the Vercel integration."""

from __future__ import annotations

import logging

DOMAIN = "vercel"
LOGGER = logging.getLogger(__package__)

CONF_TEAM_ID = "team_id"
CONF_TEAM_NAME = "team_name"

VERCEL_API_BASE = "https://api.vercel.com"

DEFAULT_DEPLOYMENT_SCAN_INTERVAL = 60  # seconds
DEFAULT_PROJECT_SCAN_INTERVAL = 900  # 15 minutes

ATTRIBUTION = "Data provided by Vercel"
