"""Support for SwitchBot sensors."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import switchbot
from switchbot import HumidifierWaterLevel
from switchbot.const.air_purifier import AirQualityLevel

from homeassistant.components.bluetooth import async_last_service_info
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    CONCENTRATION_PARTS_PER_MILLION,
    CONF_SENSOR_TYPE,
    LIGHT_LUX,
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN, LOCK_MODELS_WITH_LOGS
from .coordinator import SwitchbotConfigEntry, SwitchbotDataUpdateCoordinator
from .entity import SwitchbotEntity
from .lock_log_manager import SwitchBotLockLogManager

PARALLEL_UPDATES = 0

SENSOR_TYPES: dict[str, SensorEntityDescription] = {
    "rssi": SensorEntityDescription(
        key="rssi",
        translation_key="bluetooth_signal",
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "wifi_rssi": SensorEntityDescription(
        key="wifi_rssi",
        translation_key="wifi_signal",
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "battery": SensorEntityDescription(
        key="battery",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "co2": SensorEntityDescription(
        key="co2",
        native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.CO2,
    ),
    "lightLevel": SensorEntityDescription(
        key="lightLevel",
        translation_key="light_level",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "humidity": SensorEntityDescription(
        key="humidity",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.HUMIDITY,
    ),
    "illuminance": SensorEntityDescription(
        key="illuminance",
        native_unit_of_measurement=LIGHT_LUX,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.ILLUMINANCE,
    ),
    "temperature": SensorEntityDescription(
        key="temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    "power": SensorEntityDescription(
        key="power",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
    ),
    "current": SensorEntityDescription(
        key="current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.CURRENT,
    ),
    "voltage": SensorEntityDescription(
        key="voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.VOLTAGE,
    ),
    "aqi_level": SensorEntityDescription(
        key="aqi_level",
        translation_key="aqi_quality_level",
        device_class=SensorDeviceClass.ENUM,
        options=[member.name.lower() for member in AirQualityLevel],
    ),
    "energy": SensorEntityDescription(
        key="energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        device_class=SensorDeviceClass.ENERGY,
    ),
    "water_level": SensorEntityDescription(
        key="water_level",
        translation_key="water_level",
        device_class=SensorDeviceClass.ENUM,
        options=HumidifierWaterLevel.get_levels(),
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SwitchbotConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Switchbot sensor based on a config entry."""
    coordinator = entry.runtime_data
    sensor_entities: list[SensorEntity] = []
    if isinstance(coordinator.device, switchbot.SwitchbotRelaySwitch2PM):
        sensor_entities.extend(
            SwitchBotSensor(coordinator, sensor, channel)
            for channel in range(1, coordinator.device.channel + 1)
            for sensor in coordinator.device.get_parsed_data(channel)
            if sensor in SENSOR_TYPES
        )
    else:
        sensor_entities.extend(
            SwitchBotSensor(coordinator, sensor)
            for sensor in coordinator.device.parsed_data
            if sensor in SENSOR_TYPES
        )
    sensor_entities.append(SwitchbotRSSISensor(coordinator, "rssi"))

    # Add lock log sensors for lock devices
    sensor_type = entry.data.get(CONF_SENSOR_TYPE, "")
    if sensor_type in LOCK_MODELS_WITH_LOGS:
        lock_managers = hass.data[DOMAIN].get("lock_managers", {})
        if entry.entry_id in lock_managers:
            log_manager = lock_managers[entry.entry_id]
            sensor_entities.extend(
                [
                    SwitchBotLockLastActivitySensor(coordinator, log_manager),
                    SwitchBotLockLastUserSensor(coordinator, log_manager),
                ]
            )

    async_add_entities(sensor_entities)


class SwitchBotSensor(SwitchbotEntity, SensorEntity):
    """Representation of a Switchbot sensor."""

    def __init__(
        self,
        coordinator: SwitchbotDataUpdateCoordinator,
        sensor: str,
        channel: int | None = None,
    ) -> None:
        """Initialize the Switchbot sensor."""
        super().__init__(coordinator)
        self._sensor = sensor
        self._channel = channel
        self.entity_description = SENSOR_TYPES[sensor]

        if channel:
            self._attr_unique_id = f"{coordinator.base_unique_id}-{sensor}-{channel}"
            self._attr_device_info = DeviceInfo(
                identifiers={
                    (DOMAIN, f"{coordinator.base_unique_id}-channel-{channel}")
                },
                manufacturer="SwitchBot",
                model_id="RelaySwitch2PM",
                name=f"{coordinator.device_name} Channel {channel}",
            )
        else:
            self._attr_unique_id = f"{coordinator.base_unique_id}-{sensor}"

    @property
    def native_value(self) -> str | int | None:
        """Return the state of the sensor."""
        return self.parsed_data[self._sensor]


class SwitchbotRSSISensor(SwitchBotSensor):
    """Representation of a Switchbot RSSI sensor."""

    @property
    def native_value(self) -> str | int | None:
        """Return the state of the sensor."""
        # Switchbot supports both connectable and non-connectable devices
        # so we need to request the rssi value based on the connectable instead
        # of the nearest scanner since that is the RSSI that matters for controlling
        # the device.
        if service_info := async_last_service_info(
            self.hass, self._address, self.coordinator.connectable
        ):
            return service_info.rssi
        return None


class SwitchBotLockLastActivitySensor(SwitchbotEntity, SensorEntity):
    """Sensor showing last lock activity timestamp."""

    _attr_has_entity_name = True
    _attr_translation_key = "last_activity"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: SwitchbotDataUpdateCoordinator,
        log_manager: SwitchBotLockLogManager,
    ) -> None:
        """Initialize sensor."""
        super().__init__(coordinator)
        self._log_manager = log_manager
        self._attr_unique_id = f"{coordinator.base_unique_id}-last_activity"

    async def async_added_to_hass(self) -> None:
        """Register for log updates."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self._log_manager.async_add_listener(self._handle_log_update)
        )

    @callback
    def _handle_log_update(self) -> None:
        """Handle log update notification."""
        self.async_write_ha_state()

    @property
    def native_value(self):
        """Return timestamp of last activity."""
        if latest := self._log_manager.latest_log:
            return datetime.fromtimestamp(latest["timestamp"], tz=UTC)
        return None

    @property
    def extra_state_attributes(self):
        """Return additional attributes."""
        if not (latest := self._log_manager.latest_log):
            return {}

        return {
            "user_name": latest.get("user_name", "Unknown"),
            "action": latest.get("action_name", "unknown"),
            "source": latest.get("source", "unknown"),
            "user_id": latest.get("user_id"),
        }


class SwitchBotLockLastUserSensor(SwitchbotEntity, SensorEntity):
    """Sensor showing who last used the lock."""

    _attr_has_entity_name = True
    _attr_translation_key = "last_user"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:account"
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: SwitchbotDataUpdateCoordinator,
        log_manager: SwitchBotLockLogManager,
    ) -> None:
        """Initialize sensor."""
        super().__init__(coordinator)
        self._log_manager = log_manager
        self._attr_unique_id = f"{coordinator.base_unique_id}-last_user"
        self._last_processed_timestamp: int = 0
        self._current_log: dict[str, Any] | None = None

    async def async_added_to_hass(self) -> None:
        """Register for log updates."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self._log_manager.async_add_listener(self._handle_log_update)
        )

    @callback
    def _handle_log_update(self) -> None:
        """Handle log update notification.

        Filters logs to find the newest entry that:
        - Is newer than the last processed timestamp
        - Has a non-zero payload (indicating a real user action)
        """
        new_log = self._get_newest_valid_log()
        if new_log:
            self._current_log = new_log
            self._last_processed_timestamp = new_log.get("timestamp", 0)
        self.async_write_ha_state()

    def _get_newest_valid_log(self) -> dict[str, Any] | None:
        """Get the newest log that is valid and newer than last processed."""
        for log in self._log_manager.latest_logs:
            timestamp = log.get("timestamp", 0)
            if timestamp > self._last_processed_timestamp and self._is_valid_payload(
                log.get("payload", "")
            ):
                return log
        return None

    @staticmethod
    def _is_valid_payload(payload: str) -> bool:
        """Check if payload is valid (non-zero).

        A valid payload indicates a real user action rather than a system event.
        """
        if not payload or len(payload) < 6:
            return False
        return payload != "000000000000"

    @property
    def native_value(self) -> str | None:
        """Return name of last user (only if mapped, otherwise None)."""
        if self._current_log:
            return self._current_log.get("user_name")
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        if not self._current_log:
            return {}

        attributes: dict[str, Any] = {
            "last_activity": self._current_log.get("source_display", "Unknown"),
            "last_activity_timestamp": self._current_log.get("timestamp"),
            "last_activity_action": self._current_log.get("action_name", "unknown"),
            "source": self._current_log.get("source"),
            "payload": self._current_log.get("payload"),
        }

        # Add user_id only if present
        if self._current_log.get("user_id") is not None:
            attributes["user_id"] = self._current_log["user_id"]

        return attributes
