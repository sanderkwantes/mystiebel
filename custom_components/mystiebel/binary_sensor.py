"""Binary sensor platform for MyStiebel integration."""

import logging

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN, ESSENTIAL_SENSORS, EXCLUDED_INDIVIDUAL_SENSORS, NUMERIC_CONTROL_TYPES
from .sensor import MyStiebelBaseEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    params_to_check, fields_to_create = (
        coordinator.parameters,
        coordinator.active_fields,
    )
    entities = []
    for idx in fields_to_create:
        if idx in EXCLUDED_INDIVIDUAL_SENSORS or idx == 87:
            continue
        param = params_to_check.get(idx)
        if not param or param.get("choicelist_id") != "State_on_off":
            continue
        is_writable = "read_write" in param.get("access", [])
        is_control_entity = False
        if is_writable:
            is_time_control = param.get("data_type") == "SwitchingTime"
            has_choices = bool(param.get("choices"))
            is_numeric_with_range = (
                param.get("data_type") in NUMERIC_CONTROL_TYPES
                and param.get("min") is not None
            )
            if is_time_control or has_choices or is_numeric_with_range:
                is_control_entity = True
        if not is_control_entity:
            entities.append(MyStiebelBinarySensor(coordinator, idx, param))

    async_add_entities(entities)


class MyStiebelBinarySensor(MyStiebelBaseEntity, BinarySensorEntity):
    def __init__(self, coordinator, register_index, param) -> None:
        super().__init__(coordinator, param)
        self._register_index = register_index
        self._attr_unique_id = f"mystiebel_{register_index}"
        self._attr_name = param.get("display_name")
        if register_index not in ESSENTIAL_SENSORS:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
            self._attr_entity_registry_enabled_default = False
        else:
            self._attr_entity_category = None
            self._attr_entity_registry_enabled_default = True

    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    @property
    def is_on(self):
        try:
            return float(self.coordinator.data.get(self._register_index)) == 1.0
        except (ValueError, TypeError):
            return False
