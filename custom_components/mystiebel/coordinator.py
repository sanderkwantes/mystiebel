"""Data update coordinator for the MyStiebel integration."""

import asyncio
import logging
from asyncio import Event, Lock
from datetime import datetime, timedelta
from typing import Any

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class MyStiebelCoordinator(DataUpdateCoordinator):
    def __init__(
        self,
        hass,
        session,
        token: str,
        installation_id: str,
        client_id: str,
        device_name: str,
        model: str,
        sw_version: str | None,
        mac_address: str | None,
        bath_volume: int,
        shower_output: int,
    ) -> None:
        """Initialize the MyStiebel coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_method=self._async_update_data,
            update_interval=timedelta(minutes=1),
        )
        self.session = session
        self.token = token
        self.installation_id = installation_id
        self.client_id = client_id
        self.device_name = device_name
        self.model = model
        self.sw_version = sw_version
        self.mac_address = mac_address
        self.bath_volume = bath_volume
        self.shower_output = shower_output
        self.entities: dict[str, Any] = {}
        self.data: dict[int, Any] = {}
        self.parameters: dict[int, Any] = {}
        self.alarms: dict[int, Any] = {}
        self.active_fields: list[int] = []
        self.ready_event = Event()
        self.ws = None
        self._data_lock = Lock()
        self._last_ha_update = datetime.now()
        self._stale_threshold = timedelta(seconds=60)  # Update HA at least every minute

    async def _async_update_data(self) -> dict[int, Any]:
        """Fetch fresh data from the MyStiebel WebSocket or return last snapshot."""
        async with self._data_lock:
            if self.ws and not self.ws.closed:
                try:
                    from .websocket_client import GET_VALUES_MSG

                    message = GET_VALUES_MSG(
                        self.installation_id,
                        list(self.active_fields) if self.active_fields else [],
                    )
                    await self.ws.send_json(message)
                    _LOGGER.debug("Sent getValues request via WebSocket")
                except Exception as err:
                    _LOGGER.error("Error sending getValues request: %s", err)
            else:
                _LOGGER.debug("WebSocket not connected during update poll")

            # Always deliver current data to HA, even if unchanged this cycle,
            # so entities never sit stale between valuesChanged pushes.
            self.async_set_updated_data(self.data.copy())
            return self.data.copy()

    def process_data_update(self, data_updates: list[dict[str, Any]]) -> None:
        """Process incoming data updates in a thread-safe manner."""
        async def _update() -> None:
            async with self._data_lock:
                changed = False
                for update in data_updates:
                    register = update.get("registerIndex")
                    value = update.get("displayValue")
                    if register is not None:
                        # Check if value actually changed
                        if self.data.get(register) != value:
                            self.data[register] = value
                            changed = True
                            _LOGGER.debug(
                                "Updated register %d: %s", register, value
                            )

                # Update HA if data changed OR if last update was too long ago
                time_since_update = datetime.now() - self._last_ha_update
                should_update = changed or time_since_update > self._stale_threshold

                if should_update:
                    self.async_set_updated_data(self.data.copy())
                    self._last_ha_update = datetime.now()

                    if not changed:
                        _LOGGER.debug(
                            "Heartbeat update sent to HA (no data changes for %s seconds)",
                            int(time_since_update.total_seconds())
                        )

        # Schedule the update in the event loop
        task = asyncio.create_task(_update())
        task.add_done_callback(self._log_task_exception)

    @staticmethod
    def _log_task_exception(task: asyncio.Task) -> None:
        """Surface exceptions from process_data_update's background task.

        Without this, a parsing error in a single update is silently
        swallowed and no further values are processed until the next
        WebSocket reconnect.
        """
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            _LOGGER.error("Error processing data update: %s", exc, exc_info=exc)

    def set_websocket(self, ws: Any) -> None:
        """Set the WebSocket connection."""
        self.ws = ws

    def set_token(self, token: str):
        """Update the authentication token."""
        self.token = token

    async def async_set_value(
        self, register_index: int, value: Any
    ) -> bool:
        """Set a value via WebSocket."""
        if self.ws and not self.ws.closed:
            from .websocket_client import SET_VALUE_MSG

            message = SET_VALUE_MSG(
                self.installation_id, self.client_id, register_index, value
            )
            _LOGGER.debug("Sending setValues message for register %d", register_index)

            try:
                await self.ws.send_json(message)
                # Optimistically update the local data
                self.process_data_update(
                    [{"registerIndex": register_index, "displayValue": value}]
                )
                return True
            except Exception as e:
                _LOGGER.error(
                    "Failed to send value to register %d: %s",
                    register_index,
                    e,
                )
                return False

        _LOGGER.error("WebSocket not available or closed. Cannot set value")
        return False
