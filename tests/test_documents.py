"""Check the upload trust boundary without contacting Meta or AWS."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from test_main import SETTINGS, envelope

from univio.documents import DocumentIntake, InvalidDocument
from univio.events import parse_events


def test_pdf_caption_and_media_id_are_extracted():
    payload = envelope()
    message = payload["entry"][0]["changes"][0]["value"]["messages"][0]
    message.update(type="document", document={"id": "12345", "caption": "matric"})
    event = parse_events(json.dumps(payload).encode(), SETTINGS.phone_id)[0]
    assert (event.kind, event.command, event.media_id) == ("upload", "matric", "12345")


@pytest.mark.parametrize(
    ("url", "data", "valid"),
    [
        ("https://lookaside.fbsbx.com/fixture", b"%PDF-fixture", True),
        ("https://lookaside.fbsbx.com/fixture", b"bad fixture", False),
        ("https://example.invalid/fixture", b"%PDF-fixture", False),
    ],
)
def test_download_checks_host_and_file_header(url, data, valid):
    async def scenario():
        seen = []

        def respond(request):
            seen.append(request.url.host)
            return httpx.Response(200, content=data)

        wa = AsyncMock()
        wa.get_media_url.return_value = SimpleNamespace(
            url=url, mime_type="application/pdf", file_size=len(data)
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as session:
            intake = DocumentIntake(None, wa, session, None, "test", "", "test-token")
            if valid:
                assert await intake.download("12345") == (data, "application/pdf")
            else:
                with pytest.raises(InvalidDocument):
                    await intake.download("12345")
        if "example.invalid" in url:
            assert not seen

    asyncio.run(scenario())
