"""Support for Switchbot devices."""

import logging

import switchbot
from switchbot import SwitchbotLock

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_ADDRESS,
    CONF_MAC,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_SENSOR_TYPE,
    Platform,
)
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr

from .const import (
    CONF_ENCRYPTION_KEY,
    CONF_KEY_ID,
    CONF_LOCK_LOG_MAX_ENTRIES,
    CONF_RETRY_COUNT,
    CONNECTABLE_SUPPORTED_MODEL_TYPES,
    DEFAULT_LOCK_LOG_MAX_ENTRIES,
    DEFAULT_RETRY_COUNT,
    DOMAIN,
    ENCRYPTED_MODELS,
    HASS_SENSOR_TYPE_TO_SWITCHBOT_MODEL,
    LOCK_MODELS_WITH_LOGS,
    SERVICE_DELETE_LOCK_USER_NAME,
    SERVICE_GET_LOCK_LOGS,
    SERVICE_SET_LOCK_USER_NAME,
    SupportedModels,
)
from .coordinator import SwitchbotConfigEntry, SwitchbotDataUpdateCoordinator
from .lock_log_manager import SwitchBotLockLogManager
from .storage import SwitchBotLockUserStore

PLATFORMS_BY_TYPE = {
    SupportedModels.BULB.value: [Platform.SENSOR, Platform.LIGHT],
    SupportedModels.LIGHT_STRIP.value: [Platform.SENSOR, Platform.LIGHT],
    SupportedModels.CEILING_LIGHT.value: [Platform.SENSOR, Platform.LIGHT],
    SupportedModels.BOT.value: [Platform.SWITCH, Platform.SENSOR],
    SupportedModels.PLUG.value: [Platform.SWITCH, Platform.SENSOR],
    SupportedModels.CURTAIN.value: [
        Platform.COVER,
        Platform.BINARY_SENSOR,
        Platform.SENSOR,
    ],
    SupportedModels.HYGROMETER.value: [Platform.SENSOR],
    SupportedModels.HYGROMETER_CO2.value: [Platform.SENSOR],
    SupportedModels.CONTACT.value: [Platform.BINARY_SENSOR, Platform.SENSOR],
    SupportedModels.MOTION.value: [Platform.BINARY_SENSOR, Platform.SENSOR],
    SupportedModels.PRESENCE_SENSOR.value: [Platform.BINARY_SENSOR, Platform.SENSOR],
    SupportedModels.HUMIDIFIER.value: [Platform.HUMIDIFIER, Platform.SENSOR],
    SupportedModels.LOCK.value: [
        Platform.BINARY_SENSOR,
        Platform.LOCK,
        Platform.SENSOR,
    ],
    SupportedModels.LOCK_PRO.value: [
        Platform.BINARY_SENSOR,
        Platform.LOCK,
        Platform.SENSOR,
    ],
    SupportedModels.BLIND_TILT.value: [
        Platform.COVER,
        Platform.BINARY_SENSOR,
        Platform.SENSOR,
    ],
    SupportedModels.HUB2.value: [Platform.SENSOR],
    SupportedModels.RELAY_SWITCH_1PM.value: [Platform.SWITCH, Platform.SENSOR],
    SupportedModels.RELAY_SWITCH_1.value: [Platform.SWITCH],
    SupportedModels.LEAK.value: [Platform.BINARY_SENSOR, Platform.SENSOR],
    SupportedModels.REMOTE.value: [Platform.SENSOR],
    SupportedModels.ROLLER_SHADE.value: [
        Platform.COVER,
        Platform.BINARY_SENSOR,
        Platform.SENSOR,
    ],
    SupportedModels.HUBMINI_MATTER.value: [Platform.SENSOR],
    SupportedModels.CIRCULATOR_FAN.value: [Platform.FAN, Platform.SENSOR],
    SupportedModels.S10_VACUUM.value: [Platform.VACUUM, Platform.SENSOR],
    SupportedModels.S20_VACUUM.value: [Platform.VACUUM, Platform.SENSOR],
    SupportedModels.K10_VACUUM.value: [Platform.VACUUM, Platform.SENSOR],
    SupportedModels.K10_PRO_VACUUM.value: [Platform.VACUUM, Platform.SENSOR],
    SupportedModels.K10_PRO_COMBO_VACUUM.value: [Platform.VACUUM, Platform.SENSOR],
    SupportedModels.K11_PLUS_VACUUM.value: [Platform.VACUUM, Platform.SENSOR],
    SupportedModels.K20_VACUUM.value: [Platform.VACUUM, Platform.SENSOR],
    SupportedModels.HUB3.value: [Platform.SENSOR, Platform.BINARY_SENSOR],
    SupportedModels.LOCK_LITE.value: [
        Platform.BINARY_SENSOR,
        Platform.LOCK,
        Platform.SENSOR,
    ],
    SupportedModels.LOCK_ULTRA.value: [
        Platform.BINARY_SENSOR,
        Platform.LOCK,
        Platform.SENSOR,
    ],
    SupportedModels.AIR_PURIFIER.value: [Platform.FAN, Platform.SENSOR],
    SupportedModels.AIR_PURIFIER_TABLE.value: [Platform.FAN, Platform.SENSOR],
    SupportedModels.EVAPORATIVE_HUMIDIFIER: [Platform.HUMIDIFIER, Platform.SENSOR],
    SupportedModels.FLOOR_LAMP.value: [Platform.LIGHT, Platform.SENSOR],
    SupportedModels.STRIP_LIGHT_3.value: [Platform.LIGHT, Platform.SENSOR],
    SupportedModels.RGBICWW_FLOOR_LAMP.value: [Platform.LIGHT, Platform.SENSOR],
    SupportedModels.RGBICWW_STRIP_LIGHT.value: [Platform.LIGHT, Platform.SENSOR],
    SupportedModels.PLUG_MINI_EU.value: [Platform.SWITCH, Platform.SENSOR],
    SupportedModels.RELAY_SWITCH_2PM.value: [Platform.SWITCH, Platform.SENSOR],
    SupportedModels.GARAGE_DOOR_OPENER.value: [Platform.COVER, Platform.SENSOR],
    SupportedModels.CLIMATE_PANEL.value: [Platform.SENSOR, Platform.BINARY_SENSOR],
    SupportedModels.SMART_THERMOSTAT_RADIATOR.value: [
        Platform.CLIMATE,
        Platform.SENSOR,
    ],
    SupportedModels.ART_FRAME.value: [
        Platform.SENSOR,
        Platform.BINARY_SENSOR,
        Platform.BUTTON,
    ],
}
CLASS_BY_DEVICE = {
    SupportedModels.CEILING_LIGHT.value: switchbot.SwitchbotCeilingLight,
    SupportedModels.CURTAIN.value: switchbot.SwitchbotCurtain,
    SupportedModels.BOT.value: switchbot.Switchbot,
    SupportedModels.PLUG.value: switchbot.SwitchbotPlugMini,
    SupportedModels.BULB.value: switchbot.SwitchbotBulb,
    SupportedModels.LIGHT_STRIP.value: switchbot.SwitchbotLightStrip,
    SupportedModels.HUMIDIFIER.value: switchbot.SwitchbotHumidifier,
    SupportedModels.LOCK.value: switchbot.SwitchbotLock,
    SupportedModels.LOCK_PRO.value: switchbot.SwitchbotLock,
    SupportedModels.BLIND_TILT.value: switchbot.SwitchbotBlindTilt,
    SupportedModels.RELAY_SWITCH_1PM.value: switchbot.SwitchbotRelaySwitch,
    SupportedModels.RELAY_SWITCH_1.value: switchbot.SwitchbotRelaySwitch,
    SupportedModels.ROLLER_SHADE.value: switchbot.SwitchbotRollerShade,
    SupportedModels.CIRCULATOR_FAN.value: switchbot.SwitchbotFan,
    SupportedModels.S10_VACUUM.value: switchbot.SwitchbotVacuum,
    SupportedModels.S20_VACUUM.value: switchbot.SwitchbotVacuum,
    SupportedModels.K10_VACUUM.value: switchbot.SwitchbotVacuum,
    SupportedModels.K10_PRO_VACUUM.value: switchbot.SwitchbotVacuum,
    SupportedModels.K10_PRO_COMBO_VACUUM.value: switchbot.SwitchbotVacuum,
    SupportedModels.K11_PLUS_VACUUM.value: switchbot.SwitchbotVacuum,
    SupportedModels.K20_VACUUM.value: switchbot.SwitchbotVacuum,
    SupportedModels.LOCK_LITE.value: switchbot.SwitchbotLock,
    SupportedModels.LOCK_ULTRA.value: switchbot.SwitchbotLock,
    SupportedModels.AIR_PURIFIER.value: switchbot.SwitchbotAirPurifier,
    SupportedModels.AIR_PURIFIER_TABLE.value: switchbot.SwitchbotAirPurifier,
    SupportedModels.EVAPORATIVE_HUMIDIFIER: switchbot.SwitchbotEvaporativeHumidifier,
    SupportedModels.FLOOR_LAMP.value: switchbot.SwitchbotStripLight3,
    SupportedModels.STRIP_LIGHT_3.value: switchbot.SwitchbotStripLight3,
    SupportedModels.RGBICWW_FLOOR_LAMP.value: switchbot.SwitchbotRgbicLight,
    SupportedModels.RGBICWW_STRIP_LIGHT.value: switchbot.SwitchbotRgbicLight,
    SupportedModels.PLUG_MINI_EU.value: switchbot.SwitchbotRelaySwitch,
    SupportedModels.RELAY_SWITCH_2PM.value: switchbot.SwitchbotRelaySwitch2PM,
    SupportedModels.GARAGE_DOOR_OPENER.value: switchbot.SwitchbotGarageDoorOpener,
    SupportedModels.SMART_THERMOSTAT_RADIATOR.value: switchbot.SwitchbotSmartThermostatRadiator,
    SupportedModels.ART_FRAME.value: switchbot.SwitchbotArtFrame,
}


_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the SwitchBot component."""
    # Initialize user store
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}

    if "user_store" not in hass.data[DOMAIN]:
        user_store = SwitchBotLockUserStore(hass)
        await user_store.async_load()
        hass.data[DOMAIN]["user_store"] = user_store

    # Register services
    await _async_register_lock_services(hass)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: SwitchbotConfigEntry) -> bool:
    """Set up Switchbot from a config entry."""
    assert entry.unique_id is not None
    if CONF_ADDRESS not in entry.data and CONF_MAC in entry.data:
        # Bleak uses addresses not mac addresses which are actually
        # UUIDs on some platforms (MacOS).
        mac = entry.data[CONF_MAC]
        if "-" not in mac:
            mac = dr.format_mac(mac)
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, CONF_ADDRESS: mac},
        )

    if not entry.options:
        hass.config_entries.async_update_entry(
            entry,
            options={CONF_RETRY_COUNT: DEFAULT_RETRY_COUNT},
        )

    sensor_type: str = entry.data[CONF_SENSOR_TYPE]
    switchbot_model = HASS_SENSOR_TYPE_TO_SWITCHBOT_MODEL[sensor_type]
    # connectable means we can make connections to the device
    connectable = switchbot_model in CONNECTABLE_SUPPORTED_MODEL_TYPES
    address: str = entry.data[CONF_ADDRESS]

    await switchbot.close_stale_connections_by_address(address)

    ble_device = bluetooth.async_ble_device_from_address(
        hass, address.upper(), connectable
    )
    if not ble_device:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="device_not_found_error",
            translation_placeholders={"sensor_type": sensor_type, "address": address},
        )

    cls = CLASS_BY_DEVICE.get(sensor_type, switchbot.SwitchbotDevice)
    if switchbot_model in ENCRYPTED_MODELS:
        try:
            device = cls(
                device=ble_device,
                key_id=entry.data.get(CONF_KEY_ID),
                encryption_key=entry.data.get(CONF_ENCRYPTION_KEY),
                retry_count=entry.options[CONF_RETRY_COUNT],
                model=switchbot_model,
            )
        except ValueError as error:
            raise ConfigEntryNotReady(
                translation_domain=DOMAIN,
                translation_key="value_error",
                translation_placeholders={"error": str(error)},
            ) from error
    else:
        device = cls(
            device=ble_device,
            password=entry.data.get(CONF_PASSWORD),
            retry_count=entry.options[CONF_RETRY_COUNT],
        )

    coordinator = entry.runtime_data = SwitchbotDataUpdateCoordinator(
        hass,
        _LOGGER,
        ble_device,
        device,
        entry.unique_id,
        entry.data.get(CONF_NAME, entry.title),
        connectable,
        switchbot_model,
    )
    entry.async_on_unload(coordinator.async_start())
    if not await coordinator.async_wait_ready():
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="advertising_state_error",
            translation_placeholders={"address": address},
        )

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    # Initialize log manager for lock devices
    if sensor_type in LOCK_MODELS_WITH_LOGS:
        # Ensure user store is initialized (in case async_setup wasn't called yet)
        if "user_store" not in hass.data[DOMAIN]:
            user_store = SwitchBotLockUserStore(hass)
            await user_store.async_load()
            hass.data[DOMAIN]["user_store"] = user_store
        else:
            user_store = hass.data[DOMAIN]["user_store"]

        log_manager = SwitchBotLockLogManager(
            hass,
            device,  # type: ignore[arg-type]  # device is SwitchbotLock for lock models
            address,
            user_store,
        )
        # Store log manager in entry data for access by services and sensors
        if "lock_managers" not in hass.data[DOMAIN]:
            hass.data[DOMAIN]["lock_managers"] = {}
        hass.data[DOMAIN]["lock_managers"][entry.entry_id] = log_manager

    # Set default options for lock log max entries if not set
    if sensor_type in LOCK_MODELS_WITH_LOGS and CONF_LOCK_LOG_MAX_ENTRIES not in entry.options:
        hass.config_entries.async_update_entry(
            entry,
            options={**entry.options, CONF_LOCK_LOG_MAX_ENTRIES: DEFAULT_LOCK_LOG_MAX_ENTRIES},
        )

    await hass.config_entries.async_forward_entry_setups(
        entry, PLATFORMS_BY_TYPE[sensor_type]
    )

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    sensor_type = entry.data[CONF_SENSOR_TYPE]

    # Clean up lock manager if this is a lock device
    if sensor_type in LOCK_MODELS_WITH_LOGS:
        hass.data[DOMAIN]["lock_managers"].pop(entry.entry_id, None)

    return await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS_BY_TYPE[sensor_type]
    )


async def _async_register_lock_services(hass: HomeAssistant) -> None:
    """Register lock-related services."""
    # Only register once
    if hass.services.has_service(DOMAIN, SERVICE_GET_LOCK_LOGS):
        return

    async def async_get_lock_logs(call: ServiceCall) -> ServiceResponse:
        """Get lock logs service."""
        device_id = call.data["device_id"]
        max_entries = call.data.get("max_entries", DEFAULT_LOCK_LOG_MAX_ENTRIES)
        base_time = call.data.get("base_time", 0)

        # Find the config entry for this device
        dev_reg = dr.async_get(hass)
        device = dev_reg.async_get(device_id)
        if not device:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="device_not_found",
            )

        # Find config entry from device
        entry_id = next(iter(device.config_entries), None)
        if not entry_id or entry_id not in hass.data[DOMAIN].get("lock_managers", {}):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="device_not_lock",
            )

        log_manager = hass.data[DOMAIN]["lock_managers"][entry_id]

        # Fetch logs (this will update sensors automatically)
        try:
            logs = await log_manager.async_fetch_logs(base_time, max_entries)
        except Exception as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="fetch_logs_error",
            ) from err

        return {"logs": logs}

    async def async_set_lock_user_name(call: ServiceCall) -> None:
        """Set lock user name service."""
        device_id = call.data["device_id"]
        user_id = call.data["user_id"]
        name = call.data["name"]

        # Get device MAC address
        dev_reg = dr.async_get(hass)
        device = dev_reg.async_get(device_id)
        if not device:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="device_not_found",
            )

        # Extract MAC from device connections (Bluetooth address)
        mac = None
        for connection in device.connections:
            if connection[0] == dr.CONNECTION_BLUETOOTH:
                mac = connection[1]
                break

        if not mac:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="mac_not_found",
            )

        user_store: SwitchBotLockUserStore = hass.data[DOMAIN]["user_store"]
        await user_store.async_set_user(mac, user_id, name)

    async def async_delete_lock_user_name(call: ServiceCall) -> None:
        """Delete lock user name service."""
        device_id = call.data["device_id"]
        user_id = call.data["user_id"]

        # Get device MAC address
        dev_reg = dr.async_get(hass)
        device = dev_reg.async_get(device_id)
        if not device:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="device_not_found",
            )

        # Extract MAC from device connections (Bluetooth address)
        mac = None
        for connection in device.connections:
            if connection[0] == dr.CONNECTION_BLUETOOTH:
                mac = connection[1]
                break

        if not mac:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="mac_not_found",
            )

        user_store: SwitchBotLockUserStore = hass.data[DOMAIN]["user_store"]
        await user_store.async_delete_user(mac, user_id)

    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_LOCK_LOGS,
        async_get_lock_logs,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(DOMAIN, SERVICE_SET_LOCK_USER_NAME, async_set_lock_user_name)
    hass.services.async_register(
        DOMAIN, SERVICE_DELETE_LOCK_USER_NAME, async_delete_lock_user_name
    )
