import hashlib
import hmac
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from univio.app import MAX_WEBHOOK_BYTES, create_app
from univio.config import Settings

SETTINGS = Settings("v" * 32, "s" * 32, "a" * 32, "123456789", "t" * 32)
PAYLOAD = json.dumps({"object": "whatsapp_business_account", "entry": []}).encode()


@pytest.fixture
def client():
    with TestClient(
        create_app(
            SETTINGS,
            transport=httpx.MockTransport(
                lambda request: pytest.fail("Unexpected outbound request")
            ),
        )
    ) as client:
        yield client


def signed_headers(body):
    signature = hmac.new(SETTINGS.app_secret.encode(), body, hashlib.sha256).hexdigest()
    return {
        "Content-Type": "application/json",
        "X-Hub-Signature-256": "sha256=" + signature,
    }


def test_health_and_disabled_docs(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_api_requires_valid_bearer(client):
    for headers in ({}, {"Authorization": "Bearer wrong"}):
        assert client.get("/api/v1/status", headers=headers).status_code == 401
    response = client.get(
        "/api/v1/status", headers={"Authorization": "Bearer " + SETTINGS.api_token}
    )
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"


def test_meta_verification(client):
    params = {
        "hub.mode": "subscribe",
        "hub.verify_token": SETTINGS.verify_token,
        "hub.challenge": "12345",
    }
    response = client.get("/webhook", params=params)
    assert response.status_code == 200
    assert response.text == "12345"
    params["hub.verify_token"] = "incorrect"
    assert client.get("/webhook", params=params).status_code == 403


def test_signed_webhook(client):
    assert (
        client.post(
            "/webhook", content=PAYLOAD, headers=signed_headers(PAYLOAD)
        ).status_code
        == 200
    )


def test_missing_or_forged_signature(client):
    assert (
        client.post(
            "/webhook", content=PAYLOAD, headers={"Content-Type": "application/json"}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/webhook", content=PAYLOAD + b" ", headers=signed_headers(PAYLOAD)
        ).status_code
        == 401
    )


@pytest.mark.parametrize("body", [b"broken-json", b"[]", b"{}"])
def test_invalid_signed_payload(client, body):
    assert (
        client.post("/webhook", content=body, headers=signed_headers(body)).status_code
        == 400
    )


def test_webhook_limits(client):
    assert client.post("/webhook", content=PAYLOAD).status_code == 415
    assert (
        client.post(
            "/webhook",
            content=b"x" * (MAX_WEBHOOK_BYTES + 1),
            headers={"Content-Type": "application/json"},
        ).status_code
        == 413
    )


def test_configuration_fails_closed(monkeypatch):
    for name in ("WHATSAPP_VERIFY_TOKEN", "WHATSAPP_APP_SECRET", "API_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ValueError, match="Missing required configuration"):
        create_app()
    with pytest.raises(ValueError, match="at least 32"):
        Settings("short", "s" * 32, "a" * 32, "123456789", "t" * 32)


def envelope(
    command="menu",
    *,
    message_id="wamid.inbound",
    phone_id=SETTINGS.phone_id,
    age=0,
    interactive=None,
):
    """Construct a representative Meta event, not an internal service object."""
    message = {
        "id": message_id,
        "from": "27821234567",
        "timestamp": str(int(time.time()) - age),
        "type": "text",
        "text": {"body": command},
    }
    if interactive is not None:
        message.pop("text")
        message.update(type="interactive", interactive=interactive)
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {"phone_number_id": phone_id},
                            "messages": [message],
                        },
                    }
                ]
            }
        ],
    }


def post_event(client, payload):
    body = json.dumps(payload).encode()
    return client.post("/webhook", content=body, headers=signed_headers(body))


@pytest.fixture
def meta():
    """Exercise the real PyWa request builder, replacing only HTTP transport."""
    requests = []
    failures = []

    def handle(request):
        requests.append(request)
        if failures:
            failures.pop()
            raise httpx.ReadTimeout("Synthetic timeout", request=request)
        return httpx.Response(
            200,
            json={
                "messaging_product": "whatsapp",
                "contacts": [{"input": "27821234567", "wa_id": "27821234567"}],
                "messages": [{"id": "wamid.outbound"}],
            },
        )

    with TestClient(
        create_app(SETTINGS, transport=httpx.MockTransport(handle))
    ) as client:
        yield client, requests, failures


def test_pywa_sends_menu_and_suppresses_replay(meta):
    client, requests, _ = meta
    payload = envelope("hi")
    assert post_event(client, payload).status_code == 200
    assert post_event(client, payload).status_code == 200
    assert len(requests) == 1
    outgoing = json.loads(requests[0].content)
    assert requests[0].url.path.endswith(f"/{SETTINGS.phone_id}/messages")
    assert outgoing["to"] == "27821234567"
    assert outgoing["type"] == "interactive"
    assert len(outgoing["interactive"]["action"]["buttons"]) == 3


def test_repeated_text_with_different_id_is_not_a_duplicate(meta):
    client, requests, _ = meta
    for message_id in ("wamid.one", "wamid.two"):
        assert post_event(client, envelope(message_id=message_id)).status_code == 200
    assert len(requests) == 2


@pytest.mark.parametrize("selection_type", ["button_reply", "list_reply"])
def test_interactive_navigation(meta, selection_type):
    client, requests, _ = meta
    event = envelope(
        interactive={
            "type": selection_type,
            selection_type: {"id": "explore", "title": "Explore"},
        }
    )
    assert post_event(client, event).status_code == 200
    assert (
        "Which area interests you?"
        in json.loads(requests[0].content)["interactive"]["body"]["text"]
    )


def test_old_form_gets_chat_recovery(meta):
    client, requests, _ = meta
    assert (
        post_event(
            client,
            envelope(
                interactive={
                    "type": "nfm_reply",
                    "nfm_reply": {"response_json": "sensitive-form-data"},
                }
            ),
        ).status_code
        == 200
    )
    text = json.loads(requests[0].content)["interactive"]["body"]["text"]
    assert "replaced forms" in text
    assert "sensitive-form-data" not in text


def test_outbound_failure_is_retryable_and_does_not_poison_dedup(meta):
    client, requests, failures = meta
    failures.append(True)
    response = post_event(client, envelope())
    assert response.status_code == 503
    assert "Synthetic timeout" not in response.text
    assert post_event(client, envelope()).status_code == 200
    assert post_event(client, envelope()).status_code == 200
    assert len(requests) == 2


@pytest.mark.parametrize(
    "kwargs", [{"phone_id": "999999999"}, {"age": 24 * 3600}, {"age": -3600}]
)
def test_unrelated_or_expired_messages_do_not_send(meta, kwargs):
    client, requests, _ = meta
    assert post_event(client, envelope(**kwargs)).status_code == 200
    assert not requests


def test_invalid_batch_does_not_partially_send(meta):
    client, requests, _ = meta
    payload = envelope()
    messages = payload["entry"][0]["changes"][0]["value"]["messages"]
    messages.append({"type": "text", "from": "wrong"})
    assert post_event(client, payload).status_code == 400
    assert not requests


def test_delivery_status_does_not_generate_a_reply(meta):
    client, requests, _ = meta
    payload = envelope()
    value = payload["entry"][0]["changes"][0]["value"]
    value.pop("messages")
    value["statuses"] = [{"id": "wamid.outbound", "status": "delivered"}]
    assert post_event(client, payload).status_code == 200
    assert not requests


def test_forged_signature_cannot_trigger_outbound_send(meta):
    client, requests, _ = meta
    response = client.post(
        "/webhook",
        content=json.dumps(envelope()).encode(),
        headers=signed_headers(b"different bytes"),
    )
    assert response.status_code == 401
    assert not requests


def test_oversized_stream_without_content_length_is_rejected(client):
    def chunks():
        yield b"x" * (MAX_WEBHOOK_BYTES // 2)
        yield b"x" * (MAX_WEBHOOK_BYTES // 2 + 1)

    request = client.build_request(
        "POST",
        "/webhook",
        content=chunks(),
        headers={"Content-Type": "application/json"},
    )
    assert "content-length" not in request.headers
    assert client.send(request).status_code == 413


def test_batched_messages_are_all_replied_to(meta):
    client, requests, _ = meta
    payload = envelope("explore", message_id="one")
    second = envelope("help", message_id="two")["entry"][0]["changes"][0]["value"][
        "messages"
    ][0]
    payload["entry"][0]["changes"][0]["value"]["messages"].append(second)
    assert post_event(client, payload).status_code == 200
    assert len(requests) == 2


def test_invalid_credentials_from_meta_return_safe_retryable_error():
    def reject(request):
        return httpx.Response(
            401,
            json={
                "error": {
                    "message": "Sensitive provider detail",
                    "type": "OAuthException",
                    "code": 190,
                }
            },
        )

    with TestClient(
        create_app(SETTINGS, transport=httpx.MockTransport(reject))
    ) as client:
        response = post_event(client, envelope())
        assert response.status_code == 503
        assert "Sensitive provider detail" not in response.text
