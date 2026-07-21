"""Regression test for the binary_sensor/sensor/switch/select/number split.

MyStiebelBinarySensor used to be built inside sensor.py's async_setup_entry
and therefore registered under the wrong HA domain (see commit
"fix(binary_sensor): register State_on_off sensors under correct HA domain").
This test locks in that each register index ends up claimed by exactly one
platform, and by the *correct* one, so a future refactor can't silently
reintroduce the domain mismatch or double-register an entity.
"""

from custom_components.mystiebel import binary_sensor, number, select, sensor, switch
from custom_components.mystiebel.const import DOMAIN, EXCLUDED_INDIVIDUAL_SENSORS

PARAMETERS = {
    # read-only on/off -> binary_sensor only
    100: {
        "display_name": "Compressor",
        "data_type": "State",
        "unit": "none",
        "access": ["read"],
        "choicelist_id": "State_on_off",
        "choices": {"0": "Off", "1": "On"},
        "min": None,
        "max": None,
        "group_id": None,
    },
    # writable on/off -> switch only
    200: {
        "display_name": "Hot Water Plus requested",
        "data_type": "State",
        "unit": "none",
        "access": ["read_write"],
        "choicelist_id": "State_on_off",
        "choices": {"0": "Off", "1": "On"},
        "min": None,
        "max": None,
        "group_id": None,
    },
    # plain read-only sensor
    300: {
        "display_name": "Dome temperature",
        "data_type": "Temperature",
        "unit": "degree_celsius",
        "access": ["read"],
        "choicelist_id": None,
        "choices": {},
        "min": None,
        "max": None,
        "group_id": None,
    },
    # writable numeric with a range -> number only
    400: {
        "display_name": "Comfort temperature",
        "data_type": "Temperature",
        "unit": "degree_celsius",
        "access": ["read_write"],
        "choicelist_id": None,
        "choices": {},
        "min": 30,
        "max": 60,
        "group_id": None,
    },
    # writable with choices (not on/off) -> select only
    500: {
        "display_name": "Eco heating mode",
        "data_type": "WWK_HeatingType",
        "unit": "none",
        "access": ["read_write"],
        "choicelist_id": "WWK_HeatingType",
        "choices": {"0": "Efficient", "1": "Balanced", "2": "Fast"},
        "min": None,
        "max": None,
        "group_id": None,
    },
}


class FakeCoordinator:
    def __init__(self, parameters):
        self.parameters = parameters
        self.active_fields = list(parameters.keys()) + [next(iter(EXCLUDED_INDIVIDUAL_SENSORS))]
        self.alarms = {}
        self.installation_id = "test-install"
        self.device_name = "Test device"
        self.model = "Test model"
        self.sw_version = None
        self.mac_address = None
        self.data = {}
        self.last_update_success = True


class FakeEntry:
    entry_id = "test-entry"


class FakeHass:
    def __init__(self, coordinator):
        self.data = {DOMAIN: {FakeEntry.entry_id: coordinator}}


async def _collect(platform_module, hass):
    captured = []

    def add_entities(entities, *_args, **_kwargs):
        captured.extend(entities)

    await platform_module.async_setup_entry(hass, FakeEntry(), add_entities)
    return captured


async def test_each_register_claimed_by_exactly_one_platform():
    coordinator = FakeCoordinator(PARAMETERS)
    hass = FakeHass(coordinator)

    binary_sensors = await _collect(binary_sensor, hass)
    sensors = await _collect(sensor, hass)
    switches = switch._setup_switch_entities(coordinator)
    selects = select._setup_select_entities(coordinator)
    numbers = number._setup_number_entities(coordinator)

    by_idx = {}
    for platform_name, entities in (
        ("binary_sensor", binary_sensors),
        ("sensor", sensors),
        ("switch", switches),
        ("select", selects),
        ("number", numbers),
    ):
        for entity in entities:
            # sensor.py also always emits a handful of fixed combined/runtime
            # sensors that aren't tied to a single register in PARAMETERS.
            if not hasattr(entity, "_register_index"):
                continue
            idx = entity._register_index
            assert idx not in by_idx, (
                f"register {idx} claimed by both {by_idx[idx]!r} and {platform_name!r}"
            )
            by_idx[idx] = platform_name

    assert by_idx[100] == "binary_sensor"
    assert by_idx[200] == "switch"
    assert by_idx[300] == "sensor"
    assert by_idx[400] == "number"
    assert by_idx[500] == "select"


async def test_excluded_register_claimed_by_nobody():
    coordinator = FakeCoordinator(PARAMETERS)
    hass = FakeHass(coordinator)
    excluded_idx = coordinator.active_fields[-1]

    binary_sensors = await _collect(binary_sensor, hass)
    sensors = await _collect(sensor, hass)

    claimed_indexes = {
        e._register_index for e in binary_sensors + sensors if hasattr(e, "_register_index")
    }
    assert excluded_idx not in claimed_indexes
