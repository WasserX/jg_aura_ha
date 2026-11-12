"""Constants for JGAura integration."""

from datetime import timedelta

DOMAIN = "jg_aura"
CONF_REFRESH_RATE = "refresh_rate"
CONF_ENABLE_HOT_WATER = "hot_water"
CONF_CONNECTION = "connection"

# Entries created before local support have no CONF_CONNECTION: they are cloud.
CONNECTION_CLOUD = "cloud"
CONNECTION_LOCAL = "local"

DEFAULT_REFRESH_RATE = 60
DEFAULT_API_HOST = "https://emea-salprod02-api.arrayent.com:8081/zdk/services/zamapi"

SCAN_INTERVAL = timedelta(minutes=1)
