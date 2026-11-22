"""Constants for InPost Air Direct."""
from datetime import timedelta

DOMAIN = "inpost_air_direct"
CONF_LOCKER_CODE = "locker_code"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_SCAN_INTERVAL = timedelta(minutes=5)
MIN_SCAN_INTERVAL_MINUTES = 1
MAX_SCAN_INTERVAL_MINUTES = 60

# Readings whose measurement window ended longer ago than this are treated as stale
# (the API keeps serving the last aggregate when a locker stops reporting).
STALE_AFTER = timedelta(hours=2)

API_URL = "https://api-pl-points.easypack24.net/v1/points/{code}/air-sensors"
REQUEST_TIMEOUT = 25
