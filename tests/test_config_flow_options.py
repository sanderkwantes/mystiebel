"""Regression test for issue #13 (options flow 500 error).

MyStiebelOptionsFlowHandler used to override __init__ and assign
self.config_entry directly. On Home Assistant 2024.11+, config_entry is a
property supplied by the base OptionsFlow class, and the manual assignment
raises -- surfacing to the user as "500 Internal Server Error" when opening
the integration's configure dialog.

First attempt at this fix only removed the __init__ override and missed
that MyStiebelConfigFlow.async_get_options_flow still called
MyStiebelOptionsFlowHandler(config_entry), which then raised
"TypeError: takes no arguments" -- caught live on ha.furfurfurley.org, not
by the first version of this test, which only checked the __init__
override was gone and never called the actual factory function that broke.
Calling async_get_options_flow() end-to-end here so that gap can't recur.
"""

from unittest.mock import MagicMock

from homeassistant.config_entries import OptionsFlow

from custom_components.mystiebel.config_flow import (
    MyStiebelConfigFlow,
    MyStiebelOptionsFlowHandler,
)


def test_options_flow_does_not_override_init():
    assert "__init__" not in MyStiebelOptionsFlowHandler.__dict__
    assert MyStiebelOptionsFlowHandler.__init__ is OptionsFlow.__init__


def test_async_get_options_flow_constructs_without_error():
    fake_entry = MagicMock()
    flow = MyStiebelConfigFlow.async_get_options_flow(fake_entry)
    assert isinstance(flow, MyStiebelOptionsFlowHandler)
