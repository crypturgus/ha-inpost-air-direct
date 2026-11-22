"""Constants for InPost Air Direct."""
from datetime import timedelta

DOMAIN = "inpost_air_direct"

CONF_LOCKER_CODE = "locker_code"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_CITY = "city"
CONF_ADDRESS = "address"

DEFAULT_SCAN_INTERVAL = timedelta(minutes=5)
MIN_SCAN_INTERVAL_MINUTES = 1
MAX_SCAN_INTERVAL_MINUTES = 60

# Readings whose measurement window ended longer ago than this are treated as stale
# (the API keeps serving the last aggregate when a locker stops reporting).
STALE_AFTER = timedelta(hours=2)

AIR_SENSORS_URL = "https://api-pl-points.easypack24.net/v1/points/{code}/air-sensors"
POINTS_URL = "https://api-shipx-pl.easypack24.net/v1/points"
REQUEST_TIMEOUT = 25
RETRY_BACKOFF = 1.0  # seconds, doubled per attempt
MAX_RETRY_DELAY = 30.0

# Catalog of lockers with air sensors: downloaded only while adding a locker.
CATALOG_FIELDS = "name,location,address_details,location_description,air_index_level"
CATALOG_PAGE_SIZE = 5000
CATALOG_MAX_PAGES = 20
CATALOG_TTL = timedelta(days=7)

# Discovery
DEFAULT_SEARCH_RADIUS_M = 5000
NEARBY_PROBE_LIMIT = 12  # nearest lockers checked live for a working temperature
NEARBY_PROBE_CONCURRENCY = 4
CITY_RESULTS_LIMIT = 200
