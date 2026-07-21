"""Number platform for MyStiebel integration."""

import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory

from .const import (
    DOMAIN,
    ESSENTIAL_CONTROLS,
    EXCLUDED_INDIVIDUAL_SENSORS,
    NUMERIC_CONTROL_TYPES,
)
from .sensor import MyStiebelBaseEntity, normalize_unit

_LOGGER = logging.getLogger(__name__)


def _setup_number_entities(coordinator):
    params_to_check, fields_to_create = (
        coordinator.parameters,
        coordinator.active_fields,
    )
    numbers = []
    for idx in fields_to_create:
        # Skip excluded sensors (e.g., those combined into other entities)
        if idx in EXCLUDED_INDIVIDUAL_SENSORS:
            continue

        param = params_to_check.get(idx)
        group_id = (param.get("group_id") or "") if param else ""
        if (
            param
            and "read_write" in param.get("access", [])
            and param.get("data_type") in NUMERIC_CONTROL_TYPES
            and not bool(param.get("choices"))
            and "RUNNING_TIMES" not in group_id
        ):
            min_val, max_val = param.get("min"), param.get("max")
            if isinstance(min_val, (int, float)) and isinstance(max_val, (int, float)):
                numbers.append(MyStiebelNumber(coordinator, idx, param))
    return numbers


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    numbers = await hass.async_add_executor_job(_setup_number_entities, coordinator)
    async_add_entities(numbers, True)


class MyStiebelNumber(MyStiebelBaseEntity, NumberEntity):
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator, register_index, param) -> None:
        super().__init__(coordinator, param)
        self._register_index = register_index
        self._param = param
        self._attr_unique_id = f"mystiebel_{register_index}_number"
        self._attr_name = param.get("display_name")
        self._attr_mode = NumberMode.BOX
        self._attr_native_min_value, self._attr_native_max_value = (
            param.get("min"),
            param.get("max"),
        )
        scale = int(param.get("scale", 0))
        self._attr_native_step = 10**scale if scale < 0 else 1
        unit, data_type = normalize_unit(param.get("unit")), param.get("data_type")
        self._attr_device_class = None
        if unit is None:
            if data_type in ("DurationDays", "DurationHours", "Minute", "Second"):
                unit = {
                    "DurationDays": "d",
                    "DurationHours": "h",
                    "Minute": "min",
                    "Second": "s",
                }[data_type]
            elif data_type in ("WWK_LuminosityLevel", "Percentage"):
                unit = "%"
        if unit == "%" and data_type not in ["WWK_LuminosityLevel", "Percentage"]:
            self._attr_device_class = SensorDeviceClass.HUMIDITY
        self._attr_native_unit_of_measurement = unit
        self._attr_entity_category = EntityCategory.CONFIG
        if register_index in ESSENTIAL_CONTROLS:
            self._attr_entity_registry_enabled_default = True

    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        value = self.coordinator.data.get(self._register_index)
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_value(self._register_index, value)
