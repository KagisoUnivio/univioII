"""Validate signed Meta envelopes before any message is sent.

Unknown fields are tolerated for Meta compatibility. Fields used for routing
must have the expected types and bounded sizes; all messages are validated
before a batch is processed, avoiding replies from a partially invalid batch.
"""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class MetaModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")


class Text(MetaModel):
    body: str = Field(max_length=4096)


class Selection(MetaModel):
    id: str = Field(min_length=1, max_length=256)


class Interactive(MetaModel):
    type: str
    button_reply: Selection | None = None
    list_reply: Selection | None = None


class Attachment(MetaModel):
    id: str = Field(pattern=r"^[0-9]{1,32}$")
    caption: str = Field(default="", max_length=4096)


class IncomingMessage(MetaModel):
    id: str = Field(min_length=1, max_length=256)
    sender: str = Field(alias="from", pattern=r"^[0-9]{5,20}$")
    timestamp: str = Field(pattern=r"^[0-9]{1,12}$")
    type: str = Field(max_length=64)
    text: Text | None = None
    interactive: Interactive | None = None
    image: Attachment | None = None
    document: Attachment | None = None


class Metadata(MetaModel):
    phone_number_id: str = Field(pattern=r"^[0-9]+$", max_length=32)


class Value(MetaModel):
    metadata: Metadata | None = None
    messages: list[IncomingMessage] = Field(default_factory=list, max_length=20)


class Change(MetaModel):
    field: str
    value: Value


class Entry(MetaModel):
    changes: list[Change] = Field(max_length=20)


class Envelope(MetaModel):
    object: Literal["whatsapp_business_account"]
    entry: list[Entry] = Field(max_length=20)


@dataclass(frozen=True)
class Event:
    """Only the fields needed by the stateless conversation service."""

    id: str
    sender: str
    timestamp: int
    command: str | None
    kind: str
    media_id: str | None = None


def parse_events(raw: bytes, phone_id: str) -> list[Event]:
    """Reject malformed messages, ignore unrelated numbers and delivery statuses."""
    try:
        envelope = Envelope.model_validate_json(raw)
    except ValidationError:
        raise ValueError("Invalid webhook envelope") from None
    events = []
    for entry in envelope.entry:
        for change in entry.changes:
            value = change.value
            if change.field != "messages":
                continue
            if value.messages and value.metadata is None:
                raise ValueError("Missing phone-number metadata")
            if value.metadata is None or value.metadata.phone_number_id != phone_id:
                continue
            for message in value.messages:
                command, kind, media_id = None, "unsupported", None
                if message.type == "text":
                    if message.text is None:
                        raise ValueError("Missing message text")
                    command, kind = message.text.body, "text"
                elif message.type == "interactive":
                    interactive = message.interactive
                    if interactive is None:
                        raise ValueError("Missing interactive selection")
                    if interactive.type == "nfm_reply":
                        kind = "old_form"
                    elif interactive.type in ("button_reply", "list_reply"):
                        selection = getattr(interactive, interactive.type)
                        if selection is None:
                            raise ValueError("Missing selection ID")
                        command, kind = selection.id, "selection"
                elif message.type in ("image", "document"):
                    attachment = (
                        message.image if message.type == "image" else message.document
                    )
                    if attachment is not None:
                        command, kind, media_id = (
                            attachment.caption,
                            "upload",
                            attachment.id,
                        )
                events.append(
                    Event(
                        message.id,
                        message.sender,
                        int(message.timestamp),
                        command,
                        kind,
                        media_id,
                    )
                )
                if len(events) > 20:
                    raise ValueError("Too many messages in one webhook")
    return events
