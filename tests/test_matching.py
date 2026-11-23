import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from psycopg.conninfo import conninfo_to_dict

from univio.config import DatabaseConfig
from univio.inbox import Inbox
from univio.matching import canonical_marks, programme_fit, scores
from univio.migrate import migrate
from univio.onboarding import Onboarding
from univio.runtime import run_async

MARKS = "marks eng=72 maths=68 science=66 life=75 history=70 afr=65"


def test_marks_and_explainable_screening():
    marks = canonical_marks(MARKS + " lo=100")
    aps, values = scores(marks)
    assert aps == 33
    assert (
        programme_fit(aps, values, {"min_aps": 30, "subjects": {"maths": 60}})[0] == 0
    )
    assert (
        programme_fit(aps, values, {"min_aps": 35, "subjects": {"maths": 70}})[0] == 1
    )
    assert (
        programme_fit(aps, values, {"min_aps": 30, "subjects": {"accounting": 60}})[0]
        == 2
    )
    assert (
        programme_fit(aps, values, {"min_aps": 30, "subjects": {"maths": 80}}) is None
    )
    assert canonical_marks(MARKS.replace("afr=65", "maths=50")) is None
    assert canonical_marks(MARKS.replace("afr=65", "afr=150")) is None
    assert canonical_marks(MARKS + " name=Jane") is None


@pytest.mark.postgres
def test_student_resumes_and_sees_reviewed_matches_and_funding():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is unset")
    assert conninfo_to_dict(url)["dbname"].endswith("_test")

    async def scenario():
        config = DatabaseConfig(url)
        await migrate(config)
        inbox = Inbox(config)
        try:
            await inbox.open()
            async with inbox.pool.connection() as conn:
                for name in ("002_demo_catalog.sql", "003_demo_matching.sql"):
                    await conn.execute(
                        (
                            Path(__file__).resolve().parents[1] / "seeds" / name
                        ).read_text(encoding="utf-8")
                    )
            profile = Onboarding(inbox.pool, "test" * 8)
            job = {"phone_id": "123", "recipient": "27829987654", "kind": "text"}
            now = datetime.now(UTC)

            async def send(command, offset):
                return await profile.respond(
                    {
                        **job,
                        "command": command,
                        "created_at": now + timedelta(seconds=offset),
                    }
                )

            await send("grade12", 0)
            await send(canonical_marks(MARKS), 1)
            await send(canonical_marks(MARKS.replace("maths=68", "maths=30")), -1)
            result = await send("match-science", 2)
            assert "Example Computing" in result.text
            assert "provisional" in result.text
            assert "thresholds met" in result.text
            assert "Example bursary" in (await send("funding", 3)).text
            assert "Example Computing" in (await send("matches", 4)).text
            save = next(
                option.command
                for option in result.options
                if option.command.startswith("save-")
            )
            assert "Programme saved" in (await send(save, 5)).text
            assert "already saved" in (await send(save, 6)).text
            assert "Application checklist" in (await send("checklist", 7)).text
            assert "check the university" in (await send("checklist", 8)).text
            assert (
                "cart is empty"
                in (await send(save.replace("save-", "remove-"), 9)).text
            )
        finally:
            await inbox.close()

    run_async(scenario())
