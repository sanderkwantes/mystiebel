"""Sensor platform for MyStiebel integration."""

from datetime import UTC, datetime
import logging

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DATA_TYPE_DEVICE_CLASS_MAP,
    DEVICE_CLASS_MAP,
    DOMAIN,
    ESSENTIAL_SENSORS,
    EXCLUDED_INDIVIDUAL_SENSORS,
    NUMERIC_CONTROL_TYPES,
    STATE_CLASS_MAP,
    UNIT_MAP,
)

_LOGGER = logging.getLogger(__name__)


def normalize_unit(unit):
    return UNIT_MAP.get(str(unit).lower(), unit)


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    params_to_check, alarms_map, fields_to_create = (
        coordinator.parameters,
        coordinator.alarms,
        coordinator.active_fields,
    )
    entities = []
    for idx in fields_to_create:
        if idx in EXCLUDED_INDIVIDUAL_SENSORS or idx == 87:
            continue
        param = params_to_check.get(idx)
        if not param:
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
        if not is_control_entity and param.get("choicelist_id") != "State_on_off":
            entities.append(MyStiebelSensor(coordinator, idx, param))

    if 87 in fields_to_create:
        entities.append(MyStiebelAlarmSensor(coordinator, alarms_map))

    entities.append(
        MyStiebelCombinedInfoSensor(
            coordinator,
            "controller_sw_version",
            "mdi:chip",
            {"p1": 65535, "p2": 65536, "p3": 65537, "p4": 65560},
            "{p1}.{p2}.{p3:02d}.{p4:04d}",
        )
    )
    entities.append(
        MyStiebelCombinedInfoSensor(
            coordinator,
            "wifi_adapter_sw_version",
            "mdi:wifi",
            {"p1": 65523, "p2": 65524, "p3": 65559, "p4": 65525},
            "{p1}.{p2}.{p3:02d}.{p4:04d}",
        )
    )
    entities.append(
        MyStiebelCombinedInfoSensor(
            coordinator,
            "product_pid",
            "mdi:barcode-scan",
            {"p1": 65556, "p2": 65557, "p3": 65558, "p4": 65594},
            "{p1:06d}-{p2:06d}-{p3:06d}-{p4:06d}",
        )
    )
    entities.append(
        MyStiebelCombinedInfoSensor(
            coordinator,
            "gateway_pid",
            "mdi:barcode-scan",
            {"p1": 65553, "p2": 65554, "p3": 65555, "p4": 65593},
            "{p1:06d}-{p2:06d}-{p3:06d}-{p4:06d}",
        )
    )
    entities.append(
        MyStiebelRuntimeSensor(coordinator, "runtime_compressor", 2449, 555)
    )
    entities.append(MyStiebelRuntimeSensor(coordinator, "runtime_heating", 2450, 558))
    entities.append(
        MyStiebelCalculatedSensor(
            coordinator, "available_baths", "mdi:bathtub-outline", 2395, "bath_volume"
        )
    )
    entities.append(
        MyStiebelCalculatedSensor(
            coordinator,
            "available_shower_time",
            "mdi:shower-head",
            2395,
            "shower_output",
        )
    )

    async_add_entities(entities)


class MyStiebelBaseEntity(CoordinatorEntity):
    def __init__(self, coordinator, param=None):
        super().__init__(coordinator)
        self._param = param

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.coordinator.installation_id)},
            "name": self.coordinator.device_name,
            "manufacturer": "Stiebel Eltron",
            "model": self.coordinator.model,
            "sw_version": self.coordinator.sw_version,
            "connections": {(CONNECTION_NETWORK_MAC, self.coordinator.mac_address)},
        }

    @property
    def available(self):
        return self.coordinator.last_update_success


class MyStiebelCalculatedSensor(MyStiebelBaseEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(
        self, coordinator, name_key, icon, source_register_idx, config_divisor_name
    ):
        super().__init__(coordinator)
        self._attr_unique_id = f"mystiebel_{coordinator.installation_id}_{name_key}"
        self._attr_translation_key = name_key
        self._attr_icon = icon
        self._source_register_idx = source_register_idx
        self._config_divisor_name = config_divisor_name
        if config_divisor_name == "shower_output":
            self._attr_native_unit_of_measurement = "min"
            self._attr_device_class = SensorDeviceClass.DURATION
        self._attr_entity_registry_enabled_default = True

    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> int | None:
        source_value_str = self.coordinator.data.get(self._source_register_idx)
        divisor = getattr(self.coordinator, self._config_divisor_name, 0)
        try:
            source_value, divisor_float = float(source_value_str), float(divisor)
            return None if divisor_float == 0 else round(source_value / divisor_float)
        except (ValueError, TypeError, AttributeError):
            return None


class MyStiebelRuntimeSensor(MyStiebelBaseEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, name_key, day_idx, hour_idx):
        super().__init__(coordinator)
        self.translation_key = name_key
        self._attr_unique_id = f"mystiebel_{coordinator.installation_id}_{name_key}"
        self._attr_icon = "mdi:timer-sand"
        self._day_idx = day_idx
        self._hour_idx = hour_idx
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_entity_registry_enabled_default = True

    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> str | None:
        try:
            days = int(float(self.coordinator.data.get(self._day_idx, 0)))
            hours = int(float(self.coordinator.data.get(self._hour_idx, 0)))
            return f"{days} d, {hours} u" if days > 0 else f"{hours} u"
        except (ValueError, TypeError):
            return None


class MyStiebelCombinedInfoSensor(MyStiebelBaseEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, name_key, icon, register_map, format_string):
        super().__init__(coordinator)
        self.translation_key = name_key
        self._attr_unique_id = f"mystiebel_{coordinator.installation_id}_{name_key}"
        self._attr_icon = icon
        self._register_map = register_map
        self._format_string = format_string
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_entity_registry_enabled_default = True

    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> str | None:
        try:
            values = {
                key: int(float(self.coordinator.data.get(idx, 0)))
                for key, idx in self._register_map.items()
            }
            return self._format_string.format(**values)
        except (ValueError, TypeError):
            return None


class MyStiebelAlarmSensor(MyStiebelBaseEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "alarm_description"

    def __init__(self, coordinator, alarm_map) -> None:
        super().__init__(coordinator)
        self._alarm_map = alarm_map
        self._attr_unique_id = (
            f"mystiebel_{coordinator.installation_id}_alarm_description"
        )
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_entity_registry_enabled_default = True

    @property
    def icon(self):
        return (
            "mdi:check-circle-outline"
            if self.native_value == "no_error"
            else "mdi:alert-circle"
        )

    def _handle_coordinator_update(self) -> None:
        try:
            error_code = int(float(self.coordinator.data.get(87, 0.0)))
        except (ValueError, TypeError):
            error_code = 0
        self._attr_native_value = (
            "no_error"
            if error_code == 0
            else self._alarm_map.get(error_code, f"Unknown error code: {error_code}")
        )
        self.async_write_ha_state()


class MyStiebelSensor(MyStiebelBaseEntity, SensorEntity):
    def __init__(self, coordinator, register_index, param) -> None:
        super().__init__(coordinator, param)
        self._register_index = register_index
        self._param = param
        self._attr_unique_id = f"mystiebel_{register_index}"
        self._attr_name = param.get("display_name")
        unit, data_type = normalize_unit(param.get("unit")), param.get("data_type")
        if unit is None:
            if data_type == "DurationDays":
                unit = "d"
            elif data_type == "DurationHours":
                unit = "h"
            elif data_type == "Minute":
                unit = "min"
            elif data_type == "Second":
                unit = "s"
            elif data_type in ("WWK_LuminosityLevel", "Percentage"):
                unit = "%"
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = DEVICE_CLASS_MAP.get(unit)
        if self._attr_device_class is None:
            self._attr_device_class = DATA_TYPE_DEVICE_CLASS_MAP.get(data_type)
        self._attr_state_class = STATE_CLASS_MAP.get(data_type)
        if param.get("choices"):
            self._attr_state_class = None
        if register_index not in ESSENTIAL_SENSORS:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
            self._attr_entity_registry_enabled_default = False
        else:
            self._attr_entity_category = None
            self._attr_entity_registry_enabled_default = True

    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self):
        value = self.coordinator.data.get(self._register_index)
        if value is None:
            return None
        if self.device_class == SensorDeviceClass.TIMESTAMP:
            try:
                ts = float(value)
                if ts in {0, 1451602800}:
                    return None
                return datetime.fromtimestamp(ts, tz=UTC)
            except (ValueError, TypeError, OSError):
                return None
        choices = self._param.get("choices")
        if choices:
            try:
                return choices[str(int(float(value)))]
            except (ValueError, TypeError, KeyError):
                pass
        try:
            return float(value)
        except (ValueError, TypeError):
            return value
