"""Support for SwitchBot lock platform."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import switchbot
from switchbot.const import LockStatus

from homeassistant.components.lock import LockEntity, LockEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_LOCK_NIGHTLATCH, DEFAULT_LOCK_NIGHTLATCH, DOMAIN
from .coordinator import SwitchbotConfigEntry, SwitchbotDataUpdateCoordinator
from .entity import SwitchbotEntity, exception_handler

if TYPE_CHECKING:
    from .lock_log_manager import SwitchBotLockLogManager

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SwitchbotConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Switchbot lock based on a config entry."""
    force_nightlatch = entry.options.get(CONF_LOCK_NIGHTLATCH, DEFAULT_LOCK_NIGHTLATCH)

    # Get log manager if available
    log_manager = hass.data[DOMAIN].get("lock_managers", {}).get(entry.entry_id)

    async_add_entities([SwitchBotLock(entry.runtime_data, force_nightlatch, log_manager)])


# noinspection PyAbstractClass
class SwitchBotLock(SwitchbotEntity, LockEntity):
    """Representation of a Switchbot lock."""

    _attr_translation_key = "lock"
    _attr_name = None
    _device: switchbot.SwitchbotLock

    def __init__(
        self,
        coordinator: SwitchbotDataUpdateCoordinator,
        force_nightlatch: bool,
        log_manager: SwitchBotLockLogManager | None = None,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._log_manager = log_manager
        self._previous_status: LockStatus | None = None
        self._async_update_attrs()
        if self._device.is_night_latch_enabled() or force_nightlatch:
            self._attr_supported_features = LockEntityFeature.OPEN

    def _async_update_attrs(self) -> None:
        """Update the entity attributes."""
        status = self._device.get_lock_status()
        self._attr_is_locked = status is LockStatus.LOCKED
        self._attr_is_locking = status is LockStatus.LOCKING
        self._attr_is_unlocking = status is LockStatus.UNLOCKING
        self._attr_is_jammed = status in {
            LockStatus.LOCKING_STOP,
            LockStatus.UNLOCKING_STOP,
        }

        # Auto-fetch logs whenever lock state changes
        if self._log_manager and self._previous_status is not None and status != self._previous_status:
            _LOGGER.debug(
                "Lock state changed from %s to %s, auto-fetching logs",
                self._previous_status,
                status,
            )
            self.hass.async_create_task(self._log_manager.async_fetch_logs())

        self._previous_status = status

    @exception_handler
    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the lock."""
        self._last_run_success = await self._device.lock()
        self.async_write_ha_state()

    @exception_handler
    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the lock."""
        if self._attr_supported_features & (LockEntityFeature.OPEN):
            self._last_run_success = await self._device.unlock_without_unlatch()
        else:
            self._last_run_success = await self._device.unlock()
        self.async_write_ha_state()

    @exception_handler
    async def async_open(self, **kwargs: Any) -> None:
        """Open the lock."""
        self._last_run_success = await self._device.unlock()
        self.async_write_ha_state()
