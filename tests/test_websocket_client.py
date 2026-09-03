"""Tests for WebSocketClient._normalize_value_updates.

Regression coverage for the valuesChanged parsing fix: the API has been
observed (and is suspected, see issues #5/#6) to send updates in more than
one shape. If a shape isn't recognized, updates must be dropped loudly
(logged) rather than silently, per the fix in websocket_client.py.
"""

from custom_components.mystiebel.websocket_client import WebSocketClient


def test_flat_dict_update():
    params = {"registerIndex": 15, "displayValue": "20.5"}
    assert WebSocketClient._normalize_value_updates(params) == [params]


def test_nested_fields_update():
    fields = [
        {"registerIndex": 15, "displayValue": "20.5"},
        {"registerIndex": 16, "displayValue": "1"},
    ]
    params = {"fields": fields}
    assert WebSocketClient._normalize_value_updates(params) == fields


def test_bare_list_update():
    fields = [{"registerIndex": 15, "displayValue": "20.5"}]
    assert WebSocketClient._normalize_value_updates(fields) == fields


def test_unrecognized_shape_returns_empty():
    assert WebSocketClient._normalize_value_updates({"somethingElse": 1}) == []
    assert WebSocketClient._normalize_value_updates(None) == []
    assert WebSocketClient._normalize_value_updates("garbage") == []
