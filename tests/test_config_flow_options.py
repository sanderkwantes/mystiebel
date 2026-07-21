"""Regression test for issue #13 (options flow 500 error).

MyStiebelOptionsFlowHandler used to override __init__ and assign
self.config_entry directly. On Home Assistant 2024.11+, config_entry is a
property supplied by the base OptionsFlow class, and the manual assignment
raises -- surfacing to the user as "500 Internal Server Error" when opening
the integration's configure dialog. Guard against this coming back.
"""

from homeassistant.config_entries import OptionsFlow

from custom_components.mystiebel.config_flow import MyStiebelOptionsFlowHandler


def test_options_flow_does_not_override_init():
    assert "__init__" not in MyStiebelOptionsFlowHandler.__dict__
    assert MyStiebelOptionsFlowHandler.__init__ is OptionsFlow.__init__
