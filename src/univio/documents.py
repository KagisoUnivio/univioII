"""Bounded WhatsApp media intake into a private S3 quarantine prefix."""

import asyncio
import hashlib
import hmac
from urllib.parse import urlsplit

from botocore.exceptions import ClientError

from univio.conversation import DOCUMENT_TYPES, SCREENS, Screen

MAX_BYTES = 10 * 1024 * 1024
SIGNATURES = {
    "application/pdf": b"%PDF-",
    "image/jpeg": b"\xff\xd8\xff",
    "image/png": b"\x89PNG\r\n\x1a\n",
}


class InvalidDocument(Exception):
    """The applicant can correct the attachment and try again."""


class DocumentIntake:
    def __init__(self, inbox, wa, session, s3, bucket, owner_secret, access_token):
        self.inbox = inbox
        self.wa = wa
        self.session = session
        self.s3 = s3
        self.bucket = bucket
        self.owner_secret = owner_secret
        self.access_token = access_token

    async def download(self, media_id):
        media = await self.wa.get_media_url(media_id)
        signature = SIGNATURES.get(media.mime_type)
        if signature is None or not 0 < media.file_size <= MAX_BYTES:
            raise InvalidDocument
        url = urlsplit(media.url)
        if url.scheme != "https" or url.netloc != "lookaside.fbsbx.com":
            raise InvalidDocument
        data = bytearray()
        async with self.session.stream(
            "GET",
            media.url,
            headers={"Authorization": f"Bearer {self.access_token}"},
            follow_redirects=False,
        ) as response:
            response.raise_for_status()
            async for chunk in response.aiter_bytes(chunk_size=65536):
                if len(data) + len(chunk) > MAX_BYTES:
                    raise InvalidDocument
                data.extend(chunk)
        if len(data) != media.file_size or not data.startswith(signature):
            raise InvalidDocument
        return bytes(data), media.mime_type

    def put(self, key, body, mime_type):
        # A retry cannot replace bytes already submitted to malware scanning.
        try:
            self.s3.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=body,
                ContentType=mime_type,
                IfNoneMatch="*",
                ChecksumAlgorithm="SHA256",
            )
        except ClientError as exc:
            if exc.response["ResponseMetadata"]["HTTPStatusCode"] != 412:
                raise

    async def receive(self, job):
        options = SCREENS["upload"].options
        category = job["command"]
        if category not in DOCUMENT_TYPES or not job["media_id"]:
            return SCREENS["upload"]
        key = f"quarantine/{job['event_key']}"
        async with self.inbox.pool.connection() as conn:
            existing = await (
                await conn.execute(
                    "SELECT 1 FROM document_intake WHERE event_key = %s",
                    (job["event_key"],),
                )
            ).fetchone()
        if not existing:
            try:
                body, mime_type = await self.download(job["media_id"])
            except InvalidDocument:
                return Screen(
                    "I couldn't accept that file. Try a clear PDF, JPG or PNG up to 10 MB.",
                    options,
                )
            await asyncio.to_thread(self.put, key, body, mime_type)
            identity = f"{job['phone_id']}:{job['recipient']}".encode()
            owner = hmac.digest(
                self.owner_secret.encode(), identity, hashlib.sha256
            ).hex()
            async with self.inbox.pool.connection() as conn:
                await conn.execute(
                    """INSERT INTO document_intake
                       (event_key, applicant_key, document_type, object_key, content_type, byte_count)
                       VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (event_key) DO NOTHING""",
                    (job["event_key"], owner, category, key, mime_type, len(body)),
                )
        return Screen(
            f"*File received*\nWe received your {DOCUMENT_TYPES[category]}. It is awaiting safety checks. No university application has been submitted.",
            options,
        )
