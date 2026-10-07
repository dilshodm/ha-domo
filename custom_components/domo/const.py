"""Constants for DOMO."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import Platform, UnitOfEnergy, UnitOfVolume

DOMAIN = "domo"
PLATFORMS = [Platform.BUTTON, Platform.SENSOR]

# Polling interval option, in hours.
CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_SCAN_INTERVAL = 3
MIN_SCAN_INTERVAL = 1
MAX_SCAN_INTERVAL = 24

# Language for DOMO replies and device names.
CONF_LANGUAGE = "language"
LANGUAGES = ["ru", "uz", "en"]
FALLBACK_LANGUAGE = "ru"

# Minimum time between two manual refreshes, in seconds.
PULL_COOLDOWN = 60

CONF_PHONE = "phone"
CONF_DEVICE_ID = "device_id"
CONF_CLIENT_SECRET = "client_secret"
CONF_ACCESS = "access"
CONF_REFRESH = "refresh"
CONF_USER_ID = "user_id"

CURRENCY = "UZS"

# Service key in HomeList -> device name per language.
# Services not listed here still get a balance sensor under their raw key.
SERVICE_NAMES: dict[str, dict[str, str]] = {
    "natural_gas": {"ru": "Газ", "uz": "Gaz", "en": "Gas"},
    "liquefied_gas": {"ru": "Сжиженный газ", "uz": "Suyultirilgan gaz", "en": "Liquefied gas"},
    "electricity": {"ru": "Электричество", "uz": "Elektr energiyasi", "en": "Electricity"},
    "cold_water": {"ru": "Холодная вода", "uz": "Sovuq suv", "en": "Cold water"},
    "hot_water": {"ru": "Горячая вода", "uz": "Issiq suv", "en": "Hot water"},
    "garbage": {"ru": "Вывоз мусора", "uz": "Chiqindi olib ketish", "en": "Garbage collection"},
    "meninguyim": {"ru": "Mening uyim", "uz": "Mening uyim", "en": "Mening uyim"},
    "internet": {"ru": "Интернет", "uz": "Internet", "en": "Internet"},
    "tv": {"ru": "Телевидение", "uz": "Televideniye", "en": "TV"},
    "telephony": {"ru": "Телефония", "uz": "Telefoniya", "en": "Telephony"},
    "ev_account": {"ru": "Электрозарядка", "uz": "Elektromobil quvvatlash", "en": "EV charging"},
}

# Metered services: unit and device class of their readings.
METERS: dict[str, tuple[str, SensorDeviceClass]] = {
    "natural_gas": (UnitOfVolume.CUBIC_METERS, SensorDeviceClass.GAS),
    "electricity": (UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY),
    "cold_water": (UnitOfVolume.CUBIC_METERS, SensorDeviceClass.WATER),
    "hot_water": (UnitOfVolume.CUBIC_METERS, SensorDeviceClass.WATER),
}

# Services whose `{service}/DailyUsageStats` endpoint returns data.
DAILY_USAGE_SERVICES = ("natural_gas", "electricity")


def service_name(service: str, language: str) -> str:
    names = SERVICE_NAMES.get(service)
    return names.get(language, names[FALLBACK_LANGUAGE]) if names else service
