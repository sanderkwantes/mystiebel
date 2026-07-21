"""Integration for MyStiebel devices."""

import logging
import uuid

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client

from .const import DOMAIN
from .coordinator import MyStiebelCoordinator
from .mystiebel_auth import MyStiebelAuth
from .parameters import load_parameters
from .storage import CredentialStore
from .websocket_client import setup_websocket_listener

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["binary_sensor", "number", "select", "sensor", "switch", "time"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up MyStiebel from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    session = aiohttp_client.async_get_clientsession(hass)

    # Load credential store
    credential_store = CredentialStore(hass)
    await credential_store.async_load()

    # Check if this is an old entry with plain text credentials
    if "username" in entry.data:
        _LOGGER.info("Migrating plain text credentials to encrypted storage")

        # Save current credentials before removing them
        username = entry.data["username"]
        password = entry.data["password"]
        client_id = entry.data["client_id"]

        # Generate new credential ID
        credential_id = str(uuid.uuid4())

        # Save credentials to encrypted storage
        await credential_store.async_save(
            entry_id=credential_id,
            username=username,
            password=password,
            client_id=client_id,
        )

        # Update config entry to remove plain text credentials
        new_data = {
            "credential_id": credential_id,
            "installation_id": entry.data["installation_id"],
        }
        hass.config_entries.async_update_entry(entry, data=new_data)

        _LOGGER.info("Migration complete - credentials are now encrypted")
    else:
        # New entry or already migrated - get credentials from encrypted storage
        credential_id = entry.data.get("credential_id")
        if not credential_id:
            _LOGGER.error("No credential_id found in config entry")
            return False

        credentials = await credential_store.async_get(credential_id)
        if not credentials:
            _LOGGER.error("Credentials not found in encrypted storage for ID %s", credential_id)
            return False

        username = credentials["username"]
        password = credentials["password"]
        client_id = credentials["client_id"]

    installation_id = str(entry.data["installation_id"])

    auth = MyStiebelAuth(session, username, password, client_id)
    await auth.authenticate()
    token = auth.token

    installations = await auth.get_installations()
    device_data = next(
        (item for item in installations["items"] if str(item["id"]) == installation_id),
        None,
    )
    if not device_data:
        _LOGGER.error("Could not find installation with ID {installation_id}")
        return False

    device_name = f"{device_data.get('profile', {}).get('name', 'Unknown')} in {device_data.get('location', {}).get('city', 'Unknown')}"
    model = device_data.get("profile", {}).get("name", "Unknown")
    sw_version = device_data.get("firmware", {}).get("firmwareVersion")
    mac_address = device_data.get("macAddress")

    options = entry.options
    bath_volume = options.get("bath_volume", 180)
    shower_output = options.get("shower_output", 12)

    coordinator = MyStiebelCoordinator(
        hass,
        session,
        token,
        installation_id,
        client_id,
        device_name,
        model,
        sw_version,
        mac_address,
        bath_volume,
        shower_output,
    )
    hass.data[DOMAIN][entry.entry_id] = coordinator

    language = hass.config.language
    loaded_data = await hass.async_add_executor_job(load_parameters, language)

    coordinator.parameters = loaded_data.get("parameters", {})
    coordinator.alarms = loaded_data.get("alarms", {})
    coordinator.active_fields = list(coordinator.parameters.keys())

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Start WebSocket listener and store reference for cleanup
    websocket_client = setup_websocket_listener(
        hass, session, coordinator, auth, coordinator.active_fields
    )
    coordinator.websocket_client = websocket_client

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle unloading of an entry (disable or remove)."""
    # Stop WebSocket client if it exists
    if entry.entry_id in hass.data.get(DOMAIN, {}):
        coordinator = hass.data[DOMAIN][entry.entry_id]
        if hasattr(coordinator, 'websocket_client'):
            await coordinator.websocket_client.stop()
            _LOGGER.debug("WebSocket client stopped for entry %s", entry.entry_id)

    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Clean up data
    if unload_ok:
        # Remove coordinator data
        if entry.entry_id in hass.data.get(DOMAIN, {}):
            hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle removal of an entry (only when actually deleted)."""
    # Clean up encrypted credentials only when entry is removed
    if "credential_id" in entry.data:
        credential_store = CredentialStore(hass)
        await credential_store.async_load()
        await credential_store.async_remove(entry.data["credential_id"])
        _LOGGER.debug("Removed encrypted credentials for entry %s", entry.entry_id)


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
