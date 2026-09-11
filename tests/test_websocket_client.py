"""Tests for WebSocketClient._normalize_value_updates.

Regression coverage for the valuesChanged parsing fix: the API has been
observed (and is suspected, see issues #5/#6) to send updates in more than
one shape. If a shape isn't recognized, updates must be dropped loudly
(logged) rather than silently, per the fix in websocket_client.py.
"""

from custom_components.mystiebel.mystiebel_auth import MyStiebelAuth
from custom_components.mystiebel.websocket_client import GET_VALUES_MSG, WebSocketClient


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


class FakeCoordinator:
    def __init__(self):
        self.updates = []
        self.installation_id = "123456"

    def process_data_update(self, updates):
        self.updates.append(updates)


class FakeWebSocket:
    def __init__(self):
        self.sent = []

    async def send_json(self, message):
        self.sent.append(message)


async def test_values_response_subscribes_only_once_per_connection():
    coordinator = FakeCoordinator()
    ws = FakeWebSocket()
    client = WebSocketClient.__new__(WebSocketClient)
    client.coordinator = coordinator
    client.fields_to_monitor = [15, 16]
    client._subscribed = False

    await client._handle_values_response(
        ws,
        {
            "jsonrpc": "2.0",
            "id": 123,
            "result": {"fields": [{"registerIndex": 15, "displayValue": "20.5"}]},
        },
    )
    await client._handle_values_response(
        ws,
        {
            "jsonrpc": "2.0",
            "id": 456,
            "result": {"fields": [{"registerIndex": 16, "displayValue": "1"}]},
        },
    )

    subscribe_messages = [
        message for message in ws.sent if message["method"] == "Subscribe"
    ]
    assert len(subscribe_messages) == 1
    assert len(coordinator.updates) == 2


def test_get_values_msg_preserves_installation_id_type():
    message = GET_VALUES_MSG("248758", [15])

    assert message["params"]["installationId"] == "248758"


class FakeAuth:
    def __init__(self):
        self.token = "valid_token"
        self.token_expiry = 123456


class FakeClosingWebSocket(FakeWebSocket):
    def __init__(self):
        super().__init__()
        self.closed = False

    async def close(self):
        self.closed = True


async def test_handle_text_message_login_failure_invalidates_token_and_closes_ws():
    client = WebSocketClient.__new__(WebSocketClient)
    client.auth = FakeAuth()
    ws = FakeClosingWebSocket()

    await client._handle_text_message(
        ws, '{"jsonrpc": "2.0", "id": 1, "result": false, "error": {"code": -32000}}'
    )

    assert client.auth.token is None
    assert client.auth.token_expiry is None
    assert ws.closed is True


def test_auth_extract_token_expiry():
    import base64
    import json
    import time

    exp_timestamp = int(time.time()) + 3600
    payload = {"exp": exp_timestamp, "sub": "test"}
    p_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    fake_jwt = f"eyJhbGciOiJIUzI1NiJ9.{p_b64}.signature"

    expiry = MyStiebelAuth._extract_token_expiry(fake_jwt)
    assert expiry is not None
    assert int(expiry.timestamp()) == exp_timestamp

