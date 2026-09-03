"""WebSocket client for MyStiebel integration."""

import asyncio
import json
import logging
import random
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant

from .const import (
    APP_NAME,
    APP_VERSION_ANDROID,
    MSG_ID_LONG_MAX,
    MSG_ID_LONG_MIN,
    MSG_ID_MAX,
    MSG_ID_MIN,
    USER_AGENT,
    WEBSOCKET_HEARTBEAT,
    WEBSOCKET_RECONNECT_INITIAL,
    WEBSOCKET_RECONNECT_MAX,
    WS_URL,
)

_LOGGER = logging.getLogger(__name__)

# Track used message IDs to prevent collisions
_used_message_ids: set[int] = set()


def _generate_message_id(long_format: bool = False) -> int:
    """Generate a unique message ID with collision detection."""
    min_val = MSG_ID_LONG_MIN if long_format else MSG_ID_MIN
    max_val = MSG_ID_LONG_MAX if long_format else MSG_ID_MAX

    # Clear old IDs if we have too many (prevent memory growth)
    if len(_used_message_ids) > 1000:
        _used_message_ids.clear()

    attempts = 0
    while attempts < 100:
        msg_id = random.randint(min_val, max_val)
        if msg_id not in _used_message_ids:
            _used_message_ids.add(msg_id)
            return msg_id
        attempts += 1

    # Fallback: clear and try again
    _used_message_ids.clear()
    msg_id = random.randint(min_val, max_val)
    _used_message_ids.add(msg_id)
    return msg_id


class WebSocketClient:
    """WebSocket client for MyStiebel integration."""

    def __init__(
        self,
        hass: HomeAssistant,
        session: aiohttp.ClientSession,
        coordinator,
        auth,
        fields_to_monitor: list[int],
    ) -> None:
        """Initialize the WebSocket client."""
        self.hass = hass
        self.session = session
        self.coordinator = coordinator
        self.auth = auth
        self.fields_to_monitor = fields_to_monitor
        self.reconnect_delay = WEBSOCKET_RECONNECT_INITIAL
        self._running = True
        self._task = None
        self._current_ws = None

    def start(self) -> None:
        """Start the WebSocket client as a background task."""
        self._task = self.hass.async_create_background_task(
            self._run(),
            "mystiebel_websocket"
        )

    async def restart(self) -> None:
        """Restart the WebSocket client cleanly."""
        await self.stop()
        self._running = True
        self.start()

    async def stop(self) -> None:
        """Stop the WebSocket client."""
        _LOGGER.debug("Stopping WebSocket client")
        self._running = False

        # Close any active WebSocket connection first
        if self._current_ws and not self._current_ws.closed:
            try:
                await self._current_ws.close()
                _LOGGER.debug("Closed active WebSocket connection")
            except Exception as e:
                _LOGGER.warning("Error closing WebSocket: %s", e)

        # Cancel the background task
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                # Wait for task to complete with a timeout
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.CancelledError:
                _LOGGER.debug("WebSocket task cancelled")
            except asyncio.TimeoutError:
                _LOGGER.warning("WebSocket task did not stop within timeout")
            except Exception as e:
                _LOGGER.warning("Error stopping WebSocket task: %s", e)

        _LOGGER.info("WebSocket client stopped completely")

    async def _run(self) -> None:
        """Main run loop with automatic reconnection."""
        while self._running:
            try:
                if await self._connect_and_listen():
                    # Successful connection, reset delay
                    self.reconnect_delay = WEBSOCKET_RECONNECT_INITIAL
                else:
                    # Connection failed, apply backoff
                    await self._handle_reconnect()
            except asyncio.CancelledError:
                # Task was cancelled, stop immediately
                _LOGGER.debug("WebSocket task cancelled, stopping")
                break
            except Exception as e:
                _LOGGER.error("Unexpected error in WebSocket loop: %s", e, exc_info=True)
                if self._running:  # Only reconnect if we're still supposed to be running
                    await self._handle_reconnect()

    async def _connect_and_listen(self) -> bool:
        """Establish connection and listen for messages.

        Returns:
            True if connection was successful and closed cleanly.
            False if an error occurred.
        """
        try:
            # Authenticate first
            await self._authenticate()

            # Create WebSocket connection
            async with await self._create_connection() as ws:
                self._current_ws = ws
                self.coordinator.set_websocket(ws)

                # Login to WebSocket
                await self._send_login(ws)

                # Listen for messages
                await self._listen_to_messages(ws)

            return True

        except asyncio.CancelledError:
            # Re-raise cancellation to propagate it
            _LOGGER.debug("Connection cancelled")
            raise
        except aiohttp.ClientError as e:
            _LOGGER.error("WebSocket connection error: %s", e)
            return False
        except Exception as e:
            _LOGGER.error("Unexpected error during WebSocket connection: %s", e)
            return False
        finally:
            self._current_ws = None
            self.coordinator.set_websocket(None)

    async def _authenticate(self) -> None:
        """Authenticate and update token."""
        _LOGGER.debug("Authenticating for WebSocket connection if token not valid")
        await self.auth.ensure_valid_token()
        self.coordinator.set_token(self.auth.token)
        _LOGGER.debug("(Re-)authentication successful")

    async def _create_connection(self) -> aiohttp.ClientWebSocketResponse:
        """Create WebSocket connection with proper headers."""
        headers = {
            "Authorization": f"Bearer {self.coordinator.token}",
            "X-SC-ClientApp-Name": APP_NAME,
            "X-SC-ClientApp-Version": APP_VERSION_ANDROID,
            "User-Agent": USER_AGENT,
        }

        ws = await self.session.ws_connect(
            WS_URL, headers=headers, heartbeat=WEBSOCKET_HEARTBEAT
        )
        _LOGGER.debug("WebSocket connected successfully")
        return ws

    async def _send_login(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        """Send login message to WebSocket."""
        login_msg = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "Login",
            "params": {
                "clientId": self.coordinator.installation_id,
                "jwt": self.coordinator.token,
            },
        }
        await ws.send_json(login_msg)
        _LOGGER.debug("WebSocket login message sent")

    async def _listen_to_messages(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        """Listen for and handle incoming WebSocket messages."""
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                await self._handle_text_message(ws, msg.data)
            elif msg.type == aiohttp.WSMsgType.ERROR:
                _LOGGER.error("WebSocket error: %s", ws.exception())
                break
            elif msg.type == aiohttp.WSMsgType.CLOSED:
                _LOGGER.info("WebSocket connection closed")
                break

    async def _handle_text_message(
        self, ws: aiohttp.ClientWebSocketResponse, text: str
    ) -> None:
        """Parse and route text messages to appropriate handlers."""
        try:
            data = json.loads(text)
            _LOGGER.debug("[websocket] Received: %s", data)

            # Route to appropriate handler based on message type
            if self._is_login_response(data):
                await self._handle_login_response(ws)
            elif self._is_initial_data(data):
                await self._handle_initial_data(ws, data)
            elif self._is_value_update(data):
                await self._handle_value_update(data)

        except json.JSONDecodeError as e:
            _LOGGER.warning("Error parsing WebSocket message: %s", e)

    def _is_login_response(self, data: dict[str, Any]) -> bool:
        """Check if message is a login response."""
        return data.get("id") == 1 and data.get("result") is True

    def _is_initial_data(self, data: dict[str, Any]) -> bool:
        """Check if message contains initial data."""
        result = data.get("result", {})
        return (
            data.get("id") is not None
            and isinstance(result, dict)
            and "fields" in result
        )

    def _is_value_update(self, data: dict[str, Any]) -> bool:
        """Check if message is a value update."""
        return data.get("method") == "valuesChanged"

    async def _handle_login_response(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        """Handle successful login response."""
        # Request initial values
        msg = self._create_get_values_msg()
        await ws.send_json(msg)
        _LOGGER.debug("Requested initial values")

    async def _handle_initial_data(
        self, ws: aiohttp.ClientWebSocketResponse, data: dict[str, Any]
    ) -> None:
        """Handle initial data response."""
        fields = data["result"]["fields"]
        _LOGGER.debug("Initial data received with %d values", len(fields))

        # Process the data
        self.coordinator.process_data_update(fields)

        # Subscribe to updates
        msg = self._create_subscribe_msg()
        await ws.send_json(msg)
        _LOGGER.debug("Subscribed to value updates")

    async def _handle_value_update(self, data: dict[str, Any]) -> None:
        """Handle value change notification."""
        params = data.get("params", {})
        _LOGGER.debug("Raw valuesChanged params: %s", params)
        updates = self._normalize_value_updates(params)
        if not updates:
            _LOGGER.warning("Unrecognized valuesChanged payload shape: %s", params)
            return
        self.coordinator.process_data_update(updates)

    @staticmethod
    def _normalize_value_updates(params: Any) -> list[dict[str, Any]]:
        """Normalize a valuesChanged payload into a list of {registerIndex, displayValue} dicts.

        The API has been observed sending either a single flat update, or a
        batch nested under "fields" (matching the shape used by the initial
        getValues response). Handle both so a shape change doesn't silently
        drop every subsequent update until the next reconnect.
        """
        if isinstance(params, list):
            return params
        if isinstance(params, dict):
            fields = params.get("fields")
            if isinstance(fields, list):
                return fields
            if "registerIndex" in params:
                return [params]
        return []

    def _create_get_values_msg(self) -> dict[str, Any]:
        """Create a getValues message."""
        return {
            "jsonrpc": "2.0",
            "id": _generate_message_id(),
            "method": "getValues",
            "params": {
                "installationId": self.coordinator.installation_id,
                "fields": self.fields_to_monitor,
            },
        }

    def _create_subscribe_msg(self) -> dict[str, Any]:
        """Create a Subscribe message."""
        return {
            "jsonrpc": "2.0",
            "id": _generate_message_id(),
            "method": "Subscribe",
            "params": {
                "installationId": self.coordinator.installation_id,
                "registerIndexes": self.fields_to_monitor,
            },
        }

    async def _handle_reconnect(self) -> None:
        """Handle reconnection with exponential backoff."""
        if not self._running:
            return  # Don't reconnect if we're stopping

        _LOGGER.info("Reconnecting in %d seconds", self.reconnect_delay)

        # Use interruptible sleep so we can cancel quickly
        try:
            await asyncio.sleep(self.reconnect_delay)
        except asyncio.CancelledError:
            _LOGGER.debug("Reconnect sleep cancelled")
            raise

        # Exponential backoff
        self.reconnect_delay = min(
            self.reconnect_delay * 2, WEBSOCKET_RECONNECT_MAX
        )


def setup_websocket_listener(
    hass: HomeAssistant,
    session: aiohttp.ClientSession,
    coordinator,
    auth,
    fields_to_monitor: list[int],
) -> WebSocketClient:
    """Set up and start the WebSocket listener.

    Args:
        hass: Home Assistant instance
        session: aiohttp client session
        coordinator: Data coordinator
        auth: Authentication handler
        fields_to_monitor: List of parameter IDs to monitor

    Returns:
        WebSocketClient instance
    """
    client = WebSocketClient(hass, session, coordinator, auth, fields_to_monitor)
    client.start()
    return client


def SET_VALUE_MSG(
    installation_id: str, client_id: str, register_index: int, value: Any
) -> dict[str, Any]:
    """Create a setValues message.

    This is a standalone function because it's called from the coordinator.
    """
    return {
        "jsonrpc": "2.0",
        "id": _generate_message_id(long_format=True),
        "method": "setValues",
        "params": {
            "installationId": installation_id,
            "UUID": client_id,
            "listenWithValuesChanged": True,
            "fields": [{"registerIndex": register_index, "displayValue": value}],
        },
    }


def GET_VALUES_MSG(
    installation_id: str, registers: list[int] | None = None
) -> dict[str, Any]:
    """Create a getValues message.

    Requests the current values from the device. Used by the coordinator's
    periodic poll as a safety net alongside the WebSocket's push-based
    valuesChanged updates.
    """
    return {
        "jsonrpc": "2.0",
        "id": _generate_message_id(long_format=True),
        "method": "getValues",
        "params": {
            "installationId": int(installation_id),
            "fields": registers if registers else [],
        },
    }
